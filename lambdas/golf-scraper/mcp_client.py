"""Vardenlab MCP HTTP client for Lambda — token refresh + tools/call.

Architecture:
- Long-lived state (client_id, client_secret, refresh_token) lives in AWS
  Secrets Manager under the secret name in MCP_TOKEN_SECRET env var. The
  initial OAuth handshake (PKCE auth-code flow) is a one-time interactive
  step done from a workstation — see scripts/golfbox_mcp_oauth_setup.py.
- Short-lived state (access_token, mcp_session_id) lives in this module's
  module-level cache, so it survives across invocations within a single
  warm Lambda container but is rebuilt on cold start (or 401 retry).
- A 401 on a tool call triggers exactly one refresh + retry. If refresh
  fails too, we surface MCPAuthError so the handler can fall back to the
  legacy scrape path (GOLF_DATA_SOURCE fallback semantics).

This module ONLY talks HTTP to https://mcp.vardenlab.com — it does not
import boto3 at the top level so unit tests can stub the secret loader.
"""

import json
import logging
import os
import time
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

MCP_BASE_URL = "https://mcp.vardenlab.com"
MCP_TOOL_URL = f"{MCP_BASE_URL}/api/mcp/golfbox"
TOKEN_URL = f"{MCP_BASE_URL}/api/oauth/token"
MCP_PROTOCOL_VERSION = "2025-03-26"

# Module-level caches for warm-container reuse. Reset on cold start.
_access_token = None
_access_expires_at = 0
_session_id = None
_initialized = False
_creds_cache = None


class MCPAuthError(Exception):
    """Raised when OAuth refresh fails — caller should fall back to scrape."""


class MCPError(Exception):
    """Raised for non-auth MCP failures (transport, invalid response)."""


def _load_credentials():
    """Load client_id, client_secret (optional), refresh_token from Secrets Manager.

    The secret JSON shape (as written by scripts/golfbox_mcp_oauth_setup.py):
        {
          "client_id": "mcp_...",
          "client_secret": "..."  // optional, only for confidential clients
          "refresh_token": "rt_..."
        }
    """
    global _creds_cache
    if _creds_cache is not None:
        return _creds_cache

    import boto3  # imported lazily so tests/local PoC don't require it

    secret_name = os.environ.get("MCP_TOKEN_SECRET", "golfbox-mcp-tokens")
    region = os.environ.get("AWS_REGION", "eu-north-1")
    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=secret_name)
    creds = json.loads(resp["SecretString"])

    if not creds.get("client_id") or not creds.get("refresh_token"):
        raise MCPAuthError(
            f"Secret {secret_name} missing client_id or refresh_token — "
            "run scripts/golfbox_mcp_oauth_setup.py first"
        )
    _creds_cache = creds
    return creds


def _persist_refresh_token(new_refresh_token):
    """Write a rotated refresh_token back to Secrets Manager.

    Vardenlab may issue a new refresh_token on each /token call (refresh
    rotation). We persist only when it actually changes to keep
    Secrets-Manager write volume low.
    """
    global _creds_cache
    if not _creds_cache or _creds_cache.get("refresh_token") == new_refresh_token:
        return
    import boto3
    secret_name = os.environ.get("MCP_TOKEN_SECRET", "golfbox-mcp-tokens")
    region = os.environ.get("AWS_REGION", "eu-north-1")
    client = boto3.client("secretsmanager", region_name=region)
    _creds_cache["refresh_token"] = new_refresh_token
    client.update_secret(
        SecretId=secret_name,
        SecretString=json.dumps(_creds_cache),
    )
    logger.info("Rotated MCP refresh_token persisted")


def _refresh_access_token():
    """Trade refresh_token for a fresh access_token."""
    global _access_token, _access_expires_at, _session_id, _initialized
    creds = _load_credentials()

    form = {
        "grant_type": "refresh_token",
        "refresh_token": creds["refresh_token"],
        "client_id": creds["client_id"],
        # RFC 8707 resource indicator — Vardenlab's token endpoint requires it
        # ("invalid_target" otherwise), including on refresh_token grants.
        "resource": MCP_TOOL_URL,
    }
    if creds.get("client_secret"):
        form["client_secret"] = creds["client_secret"]

    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise MCPAuthError(f"Token refresh HTTP {e.code}: {e.read()[:200]}") from e
    except urllib.error.URLError as e:
        raise MCPAuthError(f"Token refresh URL error: {e.reason}") from e

    if "access_token" not in data:
        raise MCPAuthError(f"Token refresh returned no access_token: {data}")

    _access_token = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    _access_expires_at = int(time.time()) + expires_in - 60  # 60s safety margin
    # Refresh invalidates any prior MCP session — force re-initialize
    _session_id = None
    _initialized = False

    if data.get("refresh_token") and data["refresh_token"] != creds["refresh_token"]:
        _persist_refresh_token(data["refresh_token"])

    logger.info("MCP access token refreshed, expires_in=%d", expires_in)


def _ensure_access_token():
    if _access_token and time.time() < _access_expires_at:
        return _access_token
    _refresh_access_token()
    return _access_token


def _post_jsonrpc(payload, expect_response=True):
    """Send a JSON-RPC envelope to the MCP endpoint. Returns parsed response.

    Handles both application/json and text/event-stream responses since
    Vercel-hosted MCP servers may emit either format.
    """
    global _session_id
    access = _ensure_access_token()
    body = json.dumps(payload).encode()
    req = urllib.request.Request(MCP_TOOL_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("Authorization", f"Bearer {access}")
    if _session_id:
        req.add_header("Mcp-Session-Id", _session_id)

    try:
        resp = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise MCPAuthError(f"MCP returned 401: {e.read()[:200]}") from e
        raise MCPError(f"MCP HTTP {e.code}: {e.read()[:200]}") from e
    except urllib.error.URLError as e:
        raise MCPError(f"MCP URL error: {e.reason}") from e

    new_session = resp.headers.get("Mcp-Session-Id")
    if new_session:
        _session_id = new_session

    raw = resp.read()
    if not expect_response:
        return None

    ctype = resp.headers.get("Content-Type", "")
    if "event-stream" in ctype:
        text = raw.decode()
        for line in text.split("\n"):
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise MCPError(f"SSE response with no data: {text[:200]}")
    return json.loads(raw)


def _initialize_session():
    """MCP streamable-HTTP handshake: initialize → notifications/initialized."""
    global _initialized
    resp = _post_jsonrpc({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "tennis-bot-golf-scraper", "version": "1.0.0"},
        },
    })
    if "error" in resp:
        raise MCPError(f"initialize failed: {resp['error']}")
    _post_jsonrpc(
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        expect_response=False,
    )
    _initialized = True
    logger.info("MCP session initialized, session_id=%s", _session_id)


def _call_tool(name, arguments, request_id):
    if not _initialized:
        _initialize_session()
    resp = _post_jsonrpc({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    if "error" in resp:
        raise MCPError(f"tool {name} failed: {resp['error']}")
    content = resp.get("result", {}).get("content", [])
    if not content:
        return []
    # MCP tool responses wrap structured data as JSON text in content[0].text
    text_payload = content[0].get("text", "")
    try:
        return json.loads(text_payload)
    except json.JSONDecodeError:
        return text_payload


def search_tee_times(club, date, only_free=True):
    """Call MCP search_tee_times. Returns list of slot dicts.

    Raises MCPAuthError if OAuth flow is broken (caller should fall back to
    scrape path); MCPError for transport/parsing failures.
    """
    args = {"club": club, "date": date, "only_free": only_free}

    # Single retry on 401 — token may have just expired between cache check
    # and request, or session_id may have been invalidated server-side.
    try:
        return _call_tool("search_tee_times", args, request_id=int(time.time()))
    except MCPAuthError:
        global _initialized, _session_id, _access_token, _access_expires_at
        _initialized = False
        _session_id = None
        _access_token = None
        _access_expires_at = 0
        _refresh_access_token()
        return _call_tool("search_tee_times", args, request_id=int(time.time()))


def reset_for_tests():
    """Test helper: wipe all module-level cache."""
    global _access_token, _access_expires_at, _session_id, _initialized, _creds_cache
    _access_token = None
    _access_expires_at = 0
    _session_id = None
    _initialized = False
    _creds_cache = None
