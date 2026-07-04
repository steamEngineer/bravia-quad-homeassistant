#!/usr/bin/env python3
"""
Sony Seeds Services Authentication Flow
Reconstructs the authentication flow to obtain session keys for gRPC communication.

Flow:
1. Authorization (OAuth2 PKCE) - opens browser for user authentication
2. Token Exchange - exchanges authorization code for access_token
3. Get Devices - retrieves list of devices
4. Get Session Keys - retrieves session_key and hmac_key for gRPC
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "custom_components"))

from bravia_quad.grpc.credentials import (  # noqa: E402
    AUTH_BASE_URL,
    CLIENT_ID,
    REDIRECT_URI,
    TOKEN_USER_AGENT,
    build_credentials_bundle,
    get_devices,
    get_session_keys,
    parse_authorization_code,
    refresh_credentials,
    start_oauth_login,
)

# Re-export for scripts that import from get_session_keys (e.g. grpc_auth_gate)
__all__ = [
    "build_credentials_bundle",
    "load_credentials",
    "refresh_credentials",
    "write_credentials",
]


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code verifier and code challenge."""
    code_verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
    )
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
        .decode("utf-8")
        .rstrip("=")
    )
    return code_verifier, code_challenge


def generate_random_string(length: int = 32) -> str:
    """Generate a random URL-safe string."""
    return (
        base64.urlsafe_b64encode(secrets.token_bytes(length))
        .decode("utf-8")
        .rstrip("=")
    )


def get_authorization_url(
    state: str | None = None,
    nonce: str | None = None,
    code_challenge: str | None = None,
) -> tuple[str, str, str, str]:
    """Generate the authorization URL for OAuth2 PKCE flow."""
    if state is None:
        state = generate_random_string(43)
    if nonce is None:
        nonce = generate_random_string(43)
    if code_challenge is None:
        _, code_challenge = generate_pkce_pair()

    claims = json.dumps(
        {"id_token": {"idp_identifier": None}, "userinfo": {"idp_identifier": None}},
        separators=(",", ":"),
    )

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "response_type": "code",
        "scope": "openid",
        "claims": claims,
        "country": "US",
        "prompt": "login",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    url = f"{AUTH_BASE_URL}/user/authorize"
    authorization_url = f"{url}?{urllib.parse.urlencode(params)}"

    return authorization_url, state, nonce, code_challenge


def exchange_token(authorization_code: str, code_verifier: str) -> dict[str, Any]:
    """Exchange authorization code for access token."""
    url = f"{AUTH_BASE_URL}/token"
    payload = {
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
    }
    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "connection": "close",
        "user-agent": TOKEN_USER_AGENT,
        "host": "v1.api.auth.seeds.services",
        "accept-encoding": "gzip",
    }
    response = requests.post(url, data=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def get_account_info(access_token: str) -> dict[str, Any]:
    """Get account information using access token."""
    url = f"{AUTH_BASE_URL}/account_info"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/x-www-form-urlencoded",
        "connection": "close",
        "user-agent": TOKEN_USER_AGENT,
        "host": "v1.api.auth.seeds.services",
        "accept-encoding": "gzip",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def extract_ssh_app_redirect_from_har(har_path: str | Path) -> str:
    """Return the ssh-app://signin redirect URL from a browser HAR capture."""
    with Path(har_path).open(encoding="utf-8") as fh:
        har = json.load(fh)
    for entry in har["log"]["entries"]:
        for header in entry["response"].get("headers", []):
            if header.get("name", "").lower() != "location":
                continue
            value = header.get("value", "")
            if value.startswith("ssh-app://"):
                return value
    msg = f"No ssh-app:// redirect in HAR: {har_path}"
    raise ValueError(msg)


def load_credentials(path: str | Path) -> dict[str, Any]:
    """Load a credentials JSON file (session keys + optional OAuth tokens)."""
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def write_credentials(path: str | Path, credentials: dict[str, Any]) -> None:
    """Write credentials JSON."""
    with Path(path).open("w", encoding="utf-8") as fh:
        json.dump(credentials, fh, indent=2)
        fh.write("\n")


def complete_oauth_flow(
    authorization_code: str,
    code_verifier: str,
    device_id: str | None = None,
) -> dict[str, Any]:
    """Exchange code for token, fetch devices, return credentials bundle."""
    token_response = exchange_token(authorization_code, code_verifier)
    access_token = token_response["access_token"]
    devices_response = get_devices(access_token)
    devices = devices_response.get("devices", [])
    if not devices:
        msg = "No devices returned from Sony Seeds IoT API"
        raise RuntimeError(msg)
    resolved_device_id = device_id or devices[0]["device_id"]
    session_keys_response = get_session_keys(resolved_device_id, access_token)
    session_keys_response.setdefault("device_id", resolved_device_id)
    return build_credentials_bundle(session_keys_response, token_response)


def start_browser_login(*, open_browser: bool = False) -> tuple[str, str, str]:
    """Generate a fresh authorize URL and PKCE verifier."""
    auth_url, code_verifier, state = start_oauth_login()
    if open_browser:
        import webbrowser

        webbrowser.open(auth_url)
    return auth_url, code_verifier, state


def main() -> None:
    """CLI entry point for Sony Seeds OAuth → gRPC session keys."""
    import argparse

    parser = argparse.ArgumentParser(description="Sony Seeds OAuth → gRPC session keys")
    parser.add_argument(
        "--token",
        nargs=2,
        metavar=("ACCESS_TOKEN", "DEVICE_ID"),
        help="Fetch session keys with an existing access token",
    )
    parser.add_argument(
        "--code",
        nargs="+",
        metavar=("CODE_OR_REDIRECT", "CODE_VERIFIER"),
        help="Complete flow from authorization code (or ssh-app:// redirect URL)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh gRPC keys using refresh_token from -i/--input (no browser)",
    )
    parser.add_argument(
        "--from-har",
        metavar="HAR",
        help="Extract ssh-app:// redirect from a Chrome HAR and exchange (needs --code-verifier)",
    )
    parser.add_argument(
        "--code-verifier",
        metavar="VERIFIER",
        help="PKCE code verifier paired with the authorize URL used in the HAR capture",
    )
    parser.add_argument(
        "-i",
        "--input",
        metavar="FILE",
        help="Read existing credentials JSON (for --refresh)",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Generate a fresh authorize URL (optionally open browser, then paste redirect)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="With --login, open the authorize URL in the default browser",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Write session keys JSON to FILE",
    )
    args = parser.parse_args()

    def _emit(credentials: dict[str, Any]) -> None:
        output = json.dumps(credentials, indent=2)
        print(output)
        if args.output:
            write_credentials(args.output, credentials)

    if args.refresh:
        if not args.input:
            print("--refresh requires -i/--input credentials file", file=sys.stderr)
            sys.exit(1)
        credentials = refresh_credentials(load_credentials(args.input))
        _emit(credentials)
        return

    if args.from_har:
        if not args.code_verifier:
            print(
                "--from-har requires --code-verifier from the same login attempt",
                file=sys.stderr,
            )
            sys.exit(1)
        redirect = extract_ssh_app_redirect_from_har(args.from_har)
        auth_code = parse_authorization_code(redirect)
        credentials = complete_oauth_flow(auth_code, args.code_verifier)
        _emit(credentials)
        return

    if args.token:
        access_token, device_id = args.token
        session_keys_response = get_session_keys(device_id, access_token)
        session_keys_response.setdefault("device_id", device_id)
        previous = load_credentials(args.input) if args.input else None
        token_stub = {"access_token": access_token}
        credentials = build_credentials_bundle(
            session_keys_response, token_stub, previous=previous
        )
        _emit(credentials)
        return

    if args.code:
        redirect_or_code, code_verifier = args.code[0], args.code[1]
        device_id = args.code[2] if len(args.code) > 2 else None
        auth_code = parse_authorization_code(redirect_or_code)
        credentials = complete_oauth_flow(auth_code, code_verifier, device_id)
        _emit(credentials)
        return

    if args.login:
        auth_url, code_verifier, state = start_browser_login(open_browser=args.open)
        print("=" * 80)
        print("Sony Seeds login (fresh session — do not reuse old URLs)")
        print("=" * 80)
        print(
            "\n1. Open this URL (incognito/private window helps if the page is blank):\n"
        )
        print(auth_url)
        print(
            "\n2. Sign in with your Sony account for "
            "'Home Entertainment & Sound Service'."
        )
        print(
            "\n3. After login Chrome tries to open ssh-app://signin?code=... "
            "and fails on desktop — the URL is NOT in the address bar."
        )
        print(
            "   In Chrome DevTools (F12) → Network → filter signin → copy the "
            "ssh-app://signin?... Request URL or Location header, or just code=."
        )
        print(f"\n   Expected state: {state}")
        print(f"   Code verifier (save this): {code_verifier}\n")
        redirect = input("Paste redirect URL or authorization code: ").strip()
        if not redirect:
            print("No input provided.", file=sys.stderr)
            sys.exit(1)
        auth_code = parse_authorization_code(redirect)
        credentials = complete_oauth_flow(auth_code, code_verifier)
        _emit(credentials)
        return

    auth_url, code_verifier, state = start_browser_login(open_browser=False)
    print("\n" + "=" * 80)
    print("STEP 1: Authorization (generate a NEW URL each attempt)")
    print("=" * 80)
    print("Open this URL in your browser and authenticate:")
    print(f"\n{auth_url}\n")
    print("After authentication the browser redirects to:")
    print(f"{REDIRECT_URI}?code=<AUTHORIZATION_CODE>&state={state}")
    print("\nSave these values (required for token exchange):")
    print(f"  Code Verifier: {code_verifier}")
    print(f"  State: {state}")
    print("\nThen run either:")
    print(
        f"  python get_session_keys.py --code '<paste ssh-app redirect or code>' {code_verifier}"
    )
    print(
        "  python get_session_keys.py --from-har capture.har --code-verifier <verifier> -o session_keys.json"
    )
    print("  python get_session_keys.py --login --open -o session_keys.json")
    print(
        "  python get_session_keys.py --refresh -i session_keys.json -o session_keys.json"
    )
    print("=" * 80)


if __name__ == "__main__":
    main()
