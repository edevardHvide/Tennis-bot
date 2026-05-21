"""One-time interactive OAuth setup for the golf-scraper Lambda's MCP path.

Run this ONCE from a workstation (anywhere with a browser). It:
1. Dynamically registers an OAuth client with Vardenlab MCP
2. Walks the PKCE auth-code flow (opens browser, captures callback on 127.0.0.1)
3. Trades the code for access + refresh tokens
4. Writes {client_id, client_secret?, refresh_token} to AWS Secrets Manager
   under the secret name passed via --secret (default: golfbox-mcp-tokens).

After this runs successfully:
- Set GOLF_DATA_SOURCE=mcp on the golf-scraper Lambda
- Ensure the Lambda execution role has secretsmanager:GetSecretValue and
  secretsmanager:UpdateSecret on the secret ARN

Usage:
    AWS_PROFILE=tennis-bot uv run python scripts/golfbox_mcp_oauth_setup.py
"""

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

ISSUER = "https://mcp.vardenlab.com"
REGISTER_URL = f"{ISSUER}/api/oauth/register"
AUTHORIZE_URL = f"{ISSUER}/api/oauth/authorize"
TOKEN_URL = f"{ISSUER}/api/oauth/token"
# RFC 8707 resource indicator — the canonical MCP resource URI. Vardenlab's
# authorize + token endpoints require it ("invalid_target" otherwise). Value
# comes from /.well-known/oauth-protected-resource/api/mcp/golfbox.
RESOURCE = f"{ISSUER}/api/mcp/golfbox"
# Vardenlab rejects http loopback redirects in production ("redirect_uri must
# use https://"), so the local callback server must speak TLS. See
# _make_tls_callback_server for the self-signed-cert workaround.
REDIRECT_URI = "https://127.0.0.1:8765/callback"
SCOPE = "read write"

_callback = {"code": None, "state": None, "error": None}


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
        _callback["code"] = params.get("code", [None])[0]
        _callback["state"] = params.get("state", [None])[0]
        _callback["error"] = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if _callback["error"]:
            self.wfile.write(f"<h1>Feil: {_callback['error']}</h1>".encode())
        else:
            self.wfile.write(b"<h1>OK - lukk dette vinduet</h1>")

    def log_message(self, *args, **kwargs):
        pass


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def register_client():
    print("[1/4] Registrerer ny OAuth-klient hos Vardenlab...")
    body = json.dumps({
        "client_name": "tennis-bot-golf-scraper",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }).encode()
    req = urllib.request.Request(REGISTER_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    print(f"      client_id = {data['client_id']}")
    return data


def run_auth_flow(client_id):
    print("[2/4] Starter PKCE auth-code flow...")
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(16)
    qs = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": RESOURCE,
    })
    url = f"{AUTHORIZE_URL}?{qs}"

    server = _make_tls_callback_server(CallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("      Åpner nettleser. Klikk godkjenn.")
    print(f"      Fallback-URL: {url}")
    print()
    print("      VIKTIG: callback-serveren bruker et selvsignert TLS-sertifikat.")
    print("      Nettleseren vil vise en sikkerhetsadvarsel på slutten —")
    print("      klikk 'Avansert' → 'Fortsett til 127.0.0.1' (Chrome: skriv")
    print("      'thisisunsafe' på siden). Dette er trygt for dette engangsoppsettet.")
    webbrowser.open(url)

    deadline = time.time() + 600
    while time.time() < deadline and _callback["code"] is None and _callback["error"] is None:
        time.sleep(1)
    server.shutdown()

    if _callback["error"]:
        sys.exit(f"OAuth-feil: {_callback['error']}")
    if not _callback["code"]:
        sys.exit("Timeout - ingen callback innen 5 min")
    if _callback["state"] != state:
        sys.exit(f"State mismatch: {_callback['state']} != {state}")
    return _callback["code"], verifier


def exchange_code(client_id, code, verifier):
    print("[3/4] Bytter auth-code mot refresh token...")
    form = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
        "resource": RESOURCE,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=form, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        tokens = json.loads(resp.read())
    if "refresh_token" not in tokens:
        sys.exit(f"Ingen refresh_token i respons: {tokens}")
    print(f"      Mottatt access_token + refresh_token (scope={tokens.get('scope')})")
    return tokens


def write_secret(secret_name, region, profile, client, tokens):
    print(f"[4/4] Skriver til Secrets Manager: {secret_name} (region={region})...")
    import boto3
    session_kwargs = {"region_name": region}
    if profile:
        session_kwargs["profile_name"] = profile
    session = boto3.Session(**session_kwargs)
    sm = session.client("secretsmanager")

    payload = json.dumps({
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret"),
        "refresh_token": tokens["refresh_token"],
    })
    try:
        sm.update_secret(SecretId=secret_name, SecretString=payload)
        print("      Oppdaterte eksisterende secret")
    except sm.exceptions.ResourceNotFoundException:
        sm.create_secret(
            Name=secret_name,
            Description="Vardenlab MCP OAuth tokens for golf-scraper Lambda",
            SecretString=payload,
        )
        print("      Opprettet ny secret")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secret", default="golfbox-mcp-tokens")
    ap.add_argument("--region", default="eu-north-1")
    ap.add_argument("--profile", default="tennis-bot")
    args = ap.parse_args()

    client = register_client()
    code, verifier = run_auth_flow(client["client_id"])
    tokens = exchange_code(client["client_id"], code, verifier)
    write_secret(args.secret, args.region, args.profile, client, tokens)

    print()
    print("FERDIG. Neste steg:")
    print(f"  1. Sett env-var: GOLF_DATA_SOURCE=mcp på golf-scraper Lambda")
    print(f"  2. Sett env-var: MCP_TOKEN_SECRET={args.secret} (om annet enn default)")
    print(f"  3. Sørg for IAM-policy: secretsmanager:GetSecretValue + UpdateSecret")
    print(f"     på arn:aws:secretsmanager:{args.region}:*:secret:{args.secret}*")


if __name__ == "__main__":
    main()
