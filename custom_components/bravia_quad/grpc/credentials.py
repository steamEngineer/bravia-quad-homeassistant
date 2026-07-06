"""Sony Seeds OAuth and gRPC session key helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from aiohttp import ClientResponseError, ClientSession

CLIENT_ID = "4f97b8e2-0bb3-45ef-be91-b68e85ca7ee1"
REDIRECT_URI = "ssh-app://signin"
API_KEY = "4wTuTmXg3p41yIqIa1TdfMtyejb6s2Mz83Dxv"
AUTH_BASE_URL = "https://v1.api.auth.seeds.services"
IOT_BASE_URL = "https://v1.api.iot.seeds.services"

TOKEN_USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 3a Build/TQ3A.230901.001)"
IOT_USER_AGENT = (
    "Phone (Android 13; Pixel 3a) jp.co.sony.hes.home/3.6.3 "
    "(18194e34-ed54-4eb8-b488-4ac3bb6b8a8e)"
)

SESSION_KEYS_REFRESH_BUFFER = 3600

_TOKEN_HEADERS = {
    "content-type": "application/x-www-form-urlencoded",
    "connection": "close",
    "user-agent": TOKEN_USER_AGENT,
    "host": "v1.api.auth.seeds.services",
    "accept-encoding": "gzip",
}
_IOT_HEADERS_BASE = {
    "user-agent": IOT_USER_AGENT,
    "x-api-key": API_KEY,
    "accept-encoding": "gzip",
    "host": "v1.api.iot.seeds.services",
}


class GrpcCredentialsError(ValueError):
    """Sony Seeds credentials are missing or invalid."""


class GrpcCredentialsRefreshError(OSError):
    """OAuth or session-key refresh failed."""


class GrpcOAuthError(ValueError):
    """Sony Seeds OAuth redirect or token exchange failed."""


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


def generate_oauth_state(length: int = 43) -> str:
    """Generate a random OAuth state parameter."""
    return (
        base64.urlsafe_b64encode(secrets.token_bytes(length))
        .decode("utf-8")
        .rstrip("=")
    )


def build_authorization_url(*, code_challenge: str, state: str) -> str:
    """Build the Sony Seeds OAuth authorize URL for a PKCE login attempt."""
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
        "nonce": generate_oauth_state(),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_BASE_URL}/user/authorize?{urllib.parse.urlencode(params)}"


def parse_authorization_code(redirect_or_code: str) -> str:
    """Extract authorization code from ssh-app redirect URL or raw code."""
    value = redirect_or_code.strip()
    if value.startswith("ssh-app://"):
        parsed = urllib.parse.urlparse(value)
        params = urllib.parse.parse_qs(parsed.query)
        codes = params.get("code")
        if not codes:
            msg = f"No code= parameter in redirect URL: {value[:120]}"
            raise GrpcOAuthError(msg)
        return codes[0]
    if "code=" in value and "://" in value:
        parsed = urllib.parse.urlparse(value)
        params = urllib.parse.parse_qs(parsed.query)
        codes = params.get("code")
        if codes:
            return codes[0]
    if not value:
        msg = "Authorization code is empty"
        raise GrpcOAuthError(msg)
    return value


def parse_oauth_redirect_state(redirect_or_code: str) -> str | None:
    """Return state= from a redirect URL, or None when not present."""
    value = redirect_or_code.strip()
    if not value.startswith("ssh-app://") and not ("code=" in value and "://" in value):
        return None
    parsed = urllib.parse.urlparse(value)
    params = urllib.parse.parse_qs(parsed.query)
    states = params.get("state")
    return states[0] if states else None


def start_oauth_login() -> tuple[str, str, str]:
    """Return (authorize_url, code_verifier, state) for a fresh Sony login."""
    code_verifier, code_challenge = generate_pkce_pair()
    state = generate_oauth_state()
    auth_url = build_authorization_url(code_challenge=code_challenge, state=state)
    return auth_url, code_verifier, state


def build_credentials_bundle(
    session_keys: dict[str, Any],
    token_response: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge gRPC session keys with OAuth tokens for later refresh."""
    now = int(time.time())
    bundle = dict(previous or {})
    bundle.update(session_keys)
    bundle["access_token"] = token_response["access_token"]
    refresh_token = token_response.get("refresh_token")
    if refresh_token:
        bundle["refresh_token"] = refresh_token
    elif previous and previous.get("refresh_token"):
        bundle["refresh_token"] = previous["refresh_token"]
    access_expires = token_response.get("expires_in")
    if access_expires is not None:
        bundle["access_token_expires_in"] = int(access_expires)
        bundle["access_token_expires_at"] = now + int(access_expires)
    grpc_expires = session_keys.get("expires_in")
    if grpc_expires is not None:
        bundle["session_keys_fetched_at"] = now
        bundle["session_keys_expires_at"] = now + int(grpc_expires)
    return bundle


def parse_credentials_json(keys_json: str) -> dict[str, Any]:
    """Parse Sony Seeds credentials from config entry JSON."""
    data = json.loads(keys_json)
    if not isinstance(data, dict):
        msg = "gRPC keys JSON must be an object"
        raise TypeError(msg)
    return data


def credentials_to_json(credentials: dict[str, Any]) -> str:
    """Serialize credentials for storage in a config entry."""
    return json.dumps(credentials, separators=(",", ":"))


def keys_need_refresh(
    credentials: dict[str, Any],
    *,
    buffer_seconds: int = SESSION_KEYS_REFRESH_BUFFER,
) -> bool:
    """Return True when session keys are missing or near expiry."""
    expires_at = credentials.get("session_keys_expires_at")
    if expires_at is None:
        return False
    return int(time.time()) >= int(expires_at) - buffer_seconds


def _sync_post_form(url: str, payload: dict[str, str], headers: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        msg = f"Sony Seeds token request failed: HTTP {exc.code}"
        raise GrpcCredentialsRefreshError(msg) from exc


def _sync_get_json(url: str, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        msg = f"Sony Seeds API request failed: HTTP {exc.code}"
        raise GrpcCredentialsRefreshError(msg) from exc


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Exchange a refresh token for a new access token (sync)."""
    return _sync_post_form(
        f"{AUTH_BASE_URL}/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
        _TOKEN_HEADERS,
    )


def get_devices(access_token: str) -> dict[str, Any]:
    """List Sony Seeds IoT devices (sync)."""
    headers = {
        **_IOT_HEADERS_BASE,
        "authorization": f"Bearer {access_token}",
    }
    return _sync_get_json(f"{IOT_BASE_URL}/devices", headers)


def get_device_states(device_id: str, access_token: str) -> dict[str, Any]:
    """Fetch device state snapshot from Sony Seeds IoT API (sync)."""
    headers = {
        **_IOT_HEADERS_BASE,
        "authorization": f"Bearer {access_token}",
    }
    return _sync_get_json(f"{IOT_BASE_URL}/devices/{device_id}/states", headers)


def get_session_keys(device_id: str, access_token: str) -> dict[str, Any]:
    """Fetch gRPC session keys for a device (sync)."""
    url = f"{IOT_BASE_URL}/devices/{device_id}/session_keys"
    headers = {
        **_IOT_HEADERS_BASE,
        "authorization": f"Bearer {access_token}",
    }
    body = b""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        msg = f"Sony Seeds session_keys request failed: HTTP {exc.code}"
        raise GrpcCredentialsRefreshError(msg) from exc


def refresh_credentials(
    credentials: dict[str, Any],
    device_id: str | None = None,
) -> dict[str, Any]:
    """Refresh OAuth access token and fetch new gRPC session keys (sync)."""
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        msg = "No refresh_token in credentials; re-authenticate the integration in Settings."
        raise GrpcCredentialsError(msg)
    token_response = refresh_access_token(refresh_token)
    access_token = token_response["access_token"]
    resolved_device_id = device_id or credentials.get("device_id")
    if not resolved_device_id:
        devices_response = get_devices(access_token)
        devices = devices_response.get("devices", [])
        if not devices:
            msg = "No devices returned from Sony Seeds IoT API"
            raise GrpcCredentialsRefreshError(msg)
        resolved_device_id = devices[0]["device_id"]
    session_keys = get_session_keys(resolved_device_id, access_token)
    session_keys.setdefault("device_id", resolved_device_id)
    return build_credentials_bundle(session_keys, token_response, previous=credentials)


async def async_exchange_authorization_code(
    session: ClientSession, authorization_code: str, code_verifier: str
) -> dict[str, Any]:
    """Exchange an authorization code for OAuth tokens (async)."""
    async with session.post(
        f"{AUTH_BASE_URL}/token",
        data={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": code_verifier,
        },
        headers=_TOKEN_HEADERS,
    ) as response:
        try:
            response.raise_for_status()
        except ClientResponseError as exc:
            msg = f"Sony Seeds token request failed: HTTP {exc.status}"
            raise GrpcCredentialsRefreshError(msg) from exc
        return await response.json()


async def async_exchange_oauth_redirect(
    session: ClientSession,
    redirect_or_code: str,
    code_verifier: str,
    *,
    expected_state: str | None = None,
) -> dict[str, Any]:
    """Validate redirect, exchange authorization code, return token response."""
    redirect_state = parse_oauth_redirect_state(redirect_or_code)
    if expected_state and redirect_state and redirect_state != expected_state:
        msg = "OAuth state does not match this login attempt"
        raise GrpcOAuthError(msg)
    auth_code = parse_authorization_code(redirect_or_code)
    return await async_exchange_authorization_code(session, auth_code, code_verifier)


async def async_credentials_from_oauth(
    session: ClientSession,
    token_response: dict[str, Any],
    device_id: str | None = None,
) -> dict[str, Any]:
    """Fetch gRPC session keys for a Sony IoT device and build credentials."""
    access_token = token_response["access_token"]
    resolved_device_id = device_id
    if not resolved_device_id:
        devices_response = await async_get_devices(session, access_token)
        devices = devices_response.get("devices", [])
        if not devices:
            msg = "No devices returned from Sony Seeds IoT API"
            raise GrpcCredentialsRefreshError(msg)
        resolved_device_id = devices[0]["device_id"]
    session_keys = await async_get_session_keys(
        session, resolved_device_id, access_token
    )
    session_keys.setdefault("device_id", resolved_device_id)
    return build_credentials_bundle(session_keys, token_response)


async def async_list_oauth_devices(
    session: ClientSession, token_response: dict[str, Any]
) -> list[dict[str, Any]]:
    """List Sony IoT devices available after OAuth token exchange."""
    devices_response = await async_get_devices(session, token_response["access_token"])
    devices = devices_response.get("devices", [])
    if not devices:
        msg = "No devices returned from Sony Seeds IoT API"
        raise GrpcCredentialsRefreshError(msg)
    return devices


async def async_complete_oauth_flow(
    session: ClientSession,
    redirect_or_code: str,
    code_verifier: str,
    *,
    expected_state: str | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    """Complete Sony OAuth and fetch gRPC session keys (async)."""
    token_response = await async_exchange_oauth_redirect(
        session,
        redirect_or_code,
        code_verifier,
        expected_state=expected_state,
    )
    return await async_credentials_from_oauth(
        session, token_response, device_id=device_id
    )


async def async_refresh_access_token(
    session: ClientSession, refresh_token: str
) -> dict[str, Any]:
    """Exchange a refresh token for a new access token (async)."""
    async with session.post(
        f"{AUTH_BASE_URL}/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
        headers=_TOKEN_HEADERS,
    ) as response:
        try:
            response.raise_for_status()
        except ClientResponseError as exc:
            msg = f"Sony Seeds token request failed: HTTP {exc.status}"
            raise GrpcCredentialsRefreshError(msg) from exc
        return await response.json()


async def async_get_devices(
    session: ClientSession, access_token: str
) -> dict[str, Any]:
    """List Sony Seeds IoT devices (async)."""
    headers = {
        **_IOT_HEADERS_BASE,
        "authorization": f"Bearer {access_token}",
    }
    async with session.get(f"{IOT_BASE_URL}/devices", headers=headers) as response:
        try:
            response.raise_for_status()
        except ClientResponseError as exc:
            msg = f"Sony Seeds devices request failed: HTTP {exc.status}"
            raise GrpcCredentialsRefreshError(msg) from exc
        return await response.json()


async def async_get_device_states(
    session: ClientSession, device_id: str, access_token: str
) -> dict[str, Any]:
    """Fetch device state snapshot from Sony Seeds IoT API (async)."""
    headers = {
        **_IOT_HEADERS_BASE,
        "authorization": f"Bearer {access_token}",
    }
    url = f"{IOT_BASE_URL}/devices/{device_id}/states"
    async with session.get(url, headers=headers) as response:
        try:
            response.raise_for_status()
        except ClientResponseError as exc:
            msg = f"Sony Seeds device states request failed: HTTP {exc.status}"
            raise GrpcCredentialsRefreshError(msg) from exc
        return await response.json()


async def async_get_session_keys(
    session: ClientSession, device_id: str, access_token: str
) -> dict[str, Any]:
    """Fetch gRPC session keys for a device (async)."""
    headers = {
        **_IOT_HEADERS_BASE,
        "authorization": f"Bearer {access_token}",
    }
    url = f"{IOT_BASE_URL}/devices/{device_id}/session_keys"
    async with session.post(url, headers=headers) as response:
        try:
            response.raise_for_status()
        except ClientResponseError as exc:
            msg = f"Sony Seeds session_keys request failed: HTTP {exc.status}"
            raise GrpcCredentialsRefreshError(msg) from exc
        return await response.json()


async def async_refresh_credentials(
    session: ClientSession,
    credentials: dict[str, Any],
    device_id: str | None = None,
) -> dict[str, Any]:
    """Refresh OAuth access token and fetch new gRPC session keys (async)."""
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        msg = "No refresh_token in credentials; re-authenticate the integration in Settings."
        raise GrpcCredentialsError(msg)
    token_response = await async_refresh_access_token(session, refresh_token)
    access_token = token_response["access_token"]
    resolved_device_id = device_id or credentials.get("device_id")
    if not resolved_device_id:
        devices_response = await async_get_devices(session, access_token)
        devices = devices_response.get("devices", [])
        if not devices:
            msg = "No devices returned from Sony Seeds IoT API"
            raise GrpcCredentialsRefreshError(msg)
        resolved_device_id = devices[0]["device_id"]
    session_keys = await async_get_session_keys(
        session, resolved_device_id, access_token
    )
    session_keys.setdefault("device_id", resolved_device_id)
    return build_credentials_bundle(session_keys, token_response, previous=credentials)
