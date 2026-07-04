"""Tests for Sony Seeds OAuth helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.bravia_quad.grpc.credentials import (
    GrpcOAuthError,
    async_complete_oauth_flow,
    async_exchange_oauth_redirect,
    build_authorization_url,
    generate_pkce_pair,
    parse_authorization_code,
    parse_oauth_redirect_state,
    start_oauth_login,
)

SSH_APP = "ssh-app://signin?code=abc123&state=state456"


def test_generate_pkce_pair_lengths() -> None:
    """PKCE verifier and challenge should be non-empty URL-safe strings."""
    verifier, challenge = generate_pkce_pair()
    assert verifier
    assert challenge
    assert verifier != challenge


def test_build_authorization_url_contains_pkce_params() -> None:
    """Authorize URL should include PKCE and state query parameters."""
    _verifier, challenge = generate_pkce_pair()
    url = build_authorization_url(code_challenge=challenge, state="state123")
    assert "code_challenge=" in url
    assert "state=state123" in url
    assert "client_id=" in url


def test_start_oauth_login_returns_matching_triplet() -> None:
    """Fresh login should return URL, verifier, and state together."""
    auth_url, code_verifier, state = start_oauth_login()
    assert auth_url.startswith("https://")
    assert code_verifier
    assert state
    assert f"state={state}" in auth_url


def test_parse_authorization_code_from_ssh_app() -> None:
    assert parse_authorization_code(SSH_APP) == "abc123"
    assert parse_authorization_code("raw-code") == "raw-code"


def test_parse_authorization_code_empty_raises() -> None:
    with pytest.raises(GrpcOAuthError, match="empty"):
        parse_authorization_code("   ")


def test_parse_oauth_redirect_state() -> None:
    assert parse_oauth_redirect_state(SSH_APP) == "state456"
    assert parse_oauth_redirect_state("raw-code") is None


async def test_async_exchange_oauth_redirect_validates_state() -> None:
    """Mismatched OAuth state should fail before token exchange."""
    session = AsyncMock()
    with pytest.raises(GrpcOAuthError, match="state"):
        await async_exchange_oauth_redirect(
            session,
            SSH_APP,
            "verifier",
            expected_state="different-state",
        )


async def test_async_complete_oauth_flow() -> None:
    """OAuth completion should merge session keys with token response."""
    session = AsyncMock()
    token_response = {"access_token": "at", "refresh_token": "rt", "expires_in": 1800}
    session_keys = {
        "device_id": "dev-1",
        "key_id": "kid",
        "session_key": "sk",
        "hmac_key": "hk",
        "expires_in": 86400,
    }

    with (
        patch(
            "custom_components.bravia_quad.grpc.credentials.async_exchange_oauth_redirect",
            new=AsyncMock(return_value=token_response),
        ),
        patch(
            "custom_components.bravia_quad.grpc.credentials.async_credentials_from_oauth",
            new=AsyncMock(
                return_value={
                    **session_keys,
                    "access_token": "at",
                    "refresh_token": "rt",
                }
            ),
        ),
    ):
        bundle = await async_complete_oauth_flow(
            session,
            SSH_APP,
            "verifier",
            expected_state="state456",
        )

    assert bundle["session_key"] == "sk"
    assert bundle["refresh_token"] == token_response["refresh_token"]
