"""End-to-end PoC: OAuth handshake + MCP tool call against Vardenlab's GolfBox MCP.

Validates assumptions before pivoting Lambda to MCP:
- Dynamic client registration works (no pre-issued client secret needed)
- PKCE auth-code flow with loopback redirect succeeds
- MCP streamable-HTTP transport: initialize -> notifications/initialized -> tools/call
- Bearer token from token endpoint works against /api/mcp/golfbox
- search_tee_times for Onsoy 2026-05-25 returns 845,- (member view)

Run locally:
    uv run python scripts/golfbox_mcp_poc.py
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

ISSUER = "https://mcp.vardenlab.com"
MCP_URL = "https://mcp.vardenlab.com/api/mcp/golfbox"
REGISTER_URL = f"{ISSUER}/api/oauth/register"
AUTHORIZE_URL = f"{ISSUER}/api/oauth/authorize"
TOKEN_URL = f"{ISSUER}/api/oauth/token"
# Vardenlab rejects http loopback redirects in production ("redirect_uri must
# use https://"), so the local callback server must speak TLS. See
# _make_tls_callback_server for the self-signed-cert workaround.
REDIRECT_URI = "https://127.0.0.1:8765/callback"
SCOPE = "read write"

_callback_code = {"value": None, "state": None}


def _make_tls_callback_server(handler):
    """Build an https loopback callback server with an ephemeral self-signed cert.

    Vardenlab's OAuth server only string-matches redirect_uri; it never connects
    to the loopback address itself — the browser performs the redirect. So a
    throwaway self-signed cert (which the user click-throughs in the browser) is
    sufficient and safe for this one-shot local handshake.
    """
    server = http.server.HTTPServer(("127.0.0.1", 8765), handler)
    certdir = tempfile.mkdtemp(prefix="golfbox_mcp_tls_")
    cert_path = os.path.join(certdir, "cert.pem")
    key_path = os.path.join(certdir, "key.pem")
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", key_path, "-out", cert_path, "-days", "1",
            "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    return server


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _callback_code["value"] = params.get("code", [None])[0]
        _callback_code["state"] = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>OK - lukk dette vinduet</h1>")

    def log_message(self, *args, **kwargs):
        pass


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _http_post_json(url, payload, headers=None):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, dict(resp.headers), resp.read()


def _http_post_form(url, form, headers=None):
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def register_client():
    print("[1/5] Registrerer dynamisk OAuth-klient...")
    status, _, body = _http_post_json(REGISTER_URL, {
        "client_name": "tennis-bot-golf-scraper",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    })
    if status not in (200, 201):
        raise RuntimeError(f"Register failed: {status}")
    data = json.loads(body)
    print(f"      client_id = {data['client_id']}")
    return data["client_id"]


def authorize(client_id):
    print("[2/5] Starter PKCE auth-code flow...")
    code_verifier = _b64url(secrets.token_bytes(32))
    code_challenge = _b64url(hashlib.sha256(code_verifier.encode()).digest())
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        # RFC 8707 resource indicator — Vardenlab's authorize endpoint requires
        # it ("invalid_target: At least one resource ... is required").
        "resource": MCP_URL,
    }
    url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    server = _make_tls_callback_server(CallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"      Åpner nettleser. Godkjenn så lukker scriptet seg.")
    print(f"      Hvis nettleseren ikke åpner: gå til {url}")
    print()
    print("      VIKTIG: callback-serveren bruker et selvsignert TLS-sertifikat.")
    print("      Nettleseren vil vise en sikkerhetsadvarsel på slutten —")
    print("      klikk 'Avansert' → 'Fortsett til 127.0.0.1' (Chrome: skriv")
    print("      'thisisunsafe' på siden). Dette er trygt for dette engangsoppsettet.")
    webbrowser.open(url)

    for _ in range(600):
        if _callback_code["value"]:
            break
        time.sleep(1)
    server.shutdown()

    if not _callback_code["value"]:
        raise RuntimeError("Ingen callback innen 10 min")
    if _callback_code["state"] != state:
        raise RuntimeError(f"State mismatch: {_callback_code['state']} != {state}")
    print(f"      Mottok code (len={len(_callback_code['value'])})")
    return _callback_code["value"], code_verifier


def exchange_code(client_id, code, verifier):
    print("[3/5] Bytter auth-code mot access+refresh token...")
    tokens = _http_post_form(TOKEN_URL, {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
        "resource": MCP_URL,
    })
    if "access_token" not in tokens:
        raise RuntimeError(f"Token exchange failed: {tokens}")
    print(f"      access_token (preview): {tokens['access_token'][:20]}...")
    print(f"      refresh_token (preview): {tokens.get('refresh_token','<none>')[:20]}...")
    print(f"      expires_in: {tokens.get('expires_in')}")
    return tokens


def mcp_call(access_token, method, params=None, request_id=1, session_id=None):
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    headers = {"Authorization": f"Bearer {access_token}"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    status, resp_headers, raw = _http_post_json(MCP_URL, body, headers=headers)
    # Streamable-HTTP can return either application/json or event-stream
    ctype = resp_headers.get("content-type", resp_headers.get("Content-Type", ""))
    new_session = resp_headers.get("mcp-session-id", resp_headers.get("Mcp-Session-Id"))
    if "event-stream" in ctype:
        # Parse SSE: lines starting with "data: " followed by JSON
        text = raw.decode()
        for line in text.split("\n"):
            if line.startswith("data:"):
                payload = json.loads(line[5:].strip())
                return status, new_session, payload
        raise RuntimeError(f"SSE response with no data line: {text[:300]}")
    return status, new_session, json.loads(raw)


def mcp_notify(access_token, method, params=None, session_id=None):
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    headers = {"Authorization": f"Bearer {access_token}"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    status, _, _ = _http_post_json(MCP_URL, body, headers=headers)
    return status


def initialize_mcp(access_token):
    print("[4/5] MCP initialize...")
    status, session_id, resp = mcp_call(
        access_token,
        "initialize",
        params={
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "tennis-bot-poc", "version": "0.1.0"},
        },
        request_id=1,
    )
    print(f"      status={status}, session_id={session_id}")
    if "error" in resp:
        raise RuntimeError(f"Initialize failed: {resp}")
    server_info = resp.get("result", {}).get("serverInfo", {})
    print(f"      server: {server_info}")
    print("      Sender notifications/initialized...")
    mcp_notify(access_token, "notifications/initialized", session_id=session_id)
    return session_id


def search_onsoy(access_token, session_id):
    print("[5/5] Kaller search_tee_times for Onsoy 2026-05-25...")
    status, _, resp = mcp_call(
        access_token,
        "tools/call",
        params={
            "name": "search_tee_times",
            "arguments": {"club": "onsoy", "date": "2026-05-25", "only_free": True},
        },
        request_id=2,
        session_id=session_id,
    )
    if "error" in resp:
        raise RuntimeError(f"Tool call failed: {resp}")
    content = resp.get("result", {}).get("content", [])
    if not content:
        raise RuntimeError(f"Empty content in response: {resp}")
    text_payload = content[0].get("text", "")
    slots = json.loads(text_payload)
    print(f"      Antall slots: {len(slots)}")
    prices = [s["raw_label"][-6:] for s in slots if s.get("raw_label")]
    has_845 = any("845" in p for p in prices)
    has_795 = any("795" in p for p in prices)
    print(f"      Inneholder 845,-: {has_845}")
    print(f"      Inneholder 795,-: {has_795}  (skal vaere False for member view)")
    return slots


def main():
    client_id = register_client()
    code, verifier = authorize(client_id)
    tokens = exchange_code(client_id, code, verifier)
    session_id = initialize_mcp(tokens["access_token"])
    slots = search_onsoy(tokens["access_token"], session_id)

    print()
    print("=" * 60)
    print("POC SUKSESS - lagrer refresh_token + client_id til /tmp/golfbox_mcp_tokens.json")
    print("=" * 60)
    with open("/tmp/golfbox_mcp_tokens.json", "w") as f:
        json.dump({
            "client_id": client_id,
            "refresh_token": tokens.get("refresh_token"),
            "access_token_preview": tokens["access_token"][:30],
            "scope": tokens.get("scope"),
            "saved_at": int(time.time()),
        }, f, indent=2)
    print()
    print("MERK: dette var KUN validering — ingenting ble skrevet til AWS.")
    print("For å gi Lambdaen en token, kjør provisjonerings-scriptet:")
    print("  AWS_PROFILE=tennis-bot uv run python scripts/golfbox_mcp_oauth_setup.py")


if __name__ == "__main__":
    main()
