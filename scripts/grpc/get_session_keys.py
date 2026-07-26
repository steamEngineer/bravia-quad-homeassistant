#!/usr/bin/env python3
"""Compatibility shim: Sony Seeds OAuth → gRPC session keys.

Canonical CLI: ``python tools/get_session_keys.py`` in the
`pybravia-connect` package. This wrapper keeps scrape workflow paths and
imports stable for local HA scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any

from pybravia_connect import (
    build_credentials_bundle,
    complete_oauth_flow,
    get_session_keys,
    load_credentials,
    parse_authorization_code,
    refresh_credentials,
    start_oauth_login,
    write_credentials,
)
from pybravia_connect.credentials import REDIRECT_URI

# Re-export for scripts that import from get_session_keys (e.g. scrape_auth_gate)
__all__ = [
    "build_credentials_bundle",
    "extract_ssh_app_redirect_from_har",
    "load_credentials",
    "parse_authorization_code",
    "refresh_credentials",
    "write_credentials",
]


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


def _start_browser_login(*, open_browser: bool = False) -> tuple[str, str, str]:
    auth_url, code_verifier, state = start_oauth_login()
    if open_browser:
        webbrowser.open(auth_url)
    return auth_url, code_verifier, state


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for Sony Seeds OAuth → gRPC session keys."""
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
        help=(
            "Extract ssh-app:// redirect from a Chrome HAR and exchange "
            "(needs --code-verifier)"
        ),
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
        help=(
            "Generate a fresh authorize URL "
            "(optionally open browser, then paste redirect)"
        ),
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
    args = parser.parse_args(argv)

    def _emit(credentials: dict[str, Any]) -> None:
        print(json.dumps(credentials, indent=2))
        if args.output:
            write_credentials(args.output, credentials)

    if args.refresh:
        if not args.input:
            print("--refresh requires -i/--input credentials file", file=sys.stderr)
            return 1
        _emit(refresh_credentials(load_credentials(args.input)))
        return 0

    if args.from_har:
        if not args.code_verifier:
            print(
                "--from-har requires --code-verifier from the same login attempt",
                file=sys.stderr,
            )
            return 1
        redirect = extract_ssh_app_redirect_from_har(args.from_har)
        _emit(complete_oauth_flow(redirect, args.code_verifier))
        return 0

    if args.token:
        access_token, device_id = args.token
        session_keys_response = get_session_keys(device_id, access_token)
        session_keys_response.setdefault("device_id", device_id)
        previous = load_credentials(args.input) if args.input else None
        token_stub = {"access_token": access_token}
        _emit(
            build_credentials_bundle(
                session_keys_response, token_stub, previous=previous
            )
        )
        return 0

    if args.code:
        if len(args.code) < 2:
            print(
                "--code requires CODE_OR_REDIRECT and CODE_VERIFIER",
                file=sys.stderr,
            )
            return 1
        redirect_or_code, code_verifier = args.code[0], args.code[1]
        device_id = args.code[2] if len(args.code) > 2 else None
        _emit(
            complete_oauth_flow(
                redirect_or_code,
                code_verifier,
                device_id=device_id,
            )
        )
        return 0

    if args.login:
        auth_url, code_verifier, state = _start_browser_login(open_browser=args.open)
        print("=" * 80)
        print("Sony Seeds login (fresh session — do not reuse old URLs)")
        print("=" * 80)
        print(
            "\n1. Open this URL "
            "(incognito/private window helps if the page is blank):\n"
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
            return 1
        _emit(complete_oauth_flow(redirect, code_verifier, expected_state=state))
        return 0

    auth_url, code_verifier, state = _start_browser_login(open_browser=False)
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
    print("\nCanonical CLI (pybravia-connect checkout):")
    print("  python tools/get_session_keys.py --login --open -o session_keys.json")
    print("\nHA scrape workflow wrapper (this script):")
    print(
        "  uv run python scripts/grpc/get_session_keys.py --login --open "
        "-o scripts/grpc/session_keys.json"
    )
    print(
        "  uv run python scripts/grpc/get_session_keys.py --refresh "
        "-i scripts/grpc/session_keys.json -o scripts/grpc/session_keys.json"
    )
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
