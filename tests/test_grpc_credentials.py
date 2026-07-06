"""Tests for Sony Seeds gRPC credential helpers."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.bravia_quad.grpc.credentials import (
    GrpcCredentialsError,
    GrpcCredentialsRefreshError,
    async_refresh_credentials,
    build_credentials_bundle,
    credentials_to_json,
    keys_need_refresh,
    parse_credentials_json,
    refresh_credentials,
)


def test_keys_need_refresh_within_buffer() -> None:
    credentials = {"session_keys_expires_at": int(time.time()) + 1800}
    assert keys_need_refresh(credentials) is True


def test_keys_need_refresh_still_valid() -> None:
    now = int(time.time())
    credentials = {
        "session_keys_expires_at": now + 7200,
        "access_token_expires_at": now + 7200,
    }
    assert keys_need_refresh(credentials) is False


def test_keys_need_refresh_expired_access_token() -> None:
    now = int(time.time())
    credentials = {
        "session_keys_expires_at": now + 86400,
        "access_token_expires_at": now - 60,
    }
    assert keys_need_refresh(credentials) is True


def test_keys_need_refresh_without_expiry() -> None:
    assert keys_need_refresh({}) is False


def test_parse_and_serialize_credentials_roundtrip() -> None:
    payload = {"device_id": "dev", "refresh_token": "rt"}
    keys_json = credentials_to_json(payload)
    assert parse_credentials_json(keys_json) == payload


def test_refresh_credentials_requires_refresh_token() -> None:
    with pytest.raises(GrpcCredentialsError, match="No refresh_token"):
        refresh_credentials({"device_id": "dev"})


def test_refresh_credentials_success() -> None:
    previous = {
        "device_id": "dev-1",
        "refresh_token": "rt-old",
        "key_id": "old-key",
    }
    token_response = {"access_token": "at-new", "expires_in": 1800}
    session_keys = {
        "key_id": "new-key",
        "session_key": "sk",
        "hmac_key": "hk",
        "expires_in": 86400,
    }

    with (
        patch(
            "custom_components.bravia_quad.grpc.credentials.refresh_access_token",
            return_value=token_response,
        ),
        patch(
            "custom_components.bravia_quad.grpc.credentials.get_session_keys",
            return_value=session_keys,
        ) as mock_get_keys,
    ):
        refreshed = refresh_credentials(previous)

    mock_get_keys.assert_called_once_with("dev-1", "at-new")
    assert refreshed["key_id"] == "new-key"
    assert refreshed["access_token"] == "at-new"
    assert refreshed["refresh_token"] == "rt-old"
    assert "session_keys_expires_at" in refreshed


async def test_async_refresh_credentials_success() -> None:
    previous = {
        "device_id": "dev-1",
        "refresh_token": "rt-old",
    }
    token_response = {"access_token": "at-new", "expires_in": 1800}
    session_keys = {
        "key_id": "new-key",
        "session_key": "sk",
        "hmac_key": "hk",
        "expires_in": 86400,
    }
    session = AsyncMock()

    with (
        patch(
            "custom_components.bravia_quad.grpc.credentials.async_refresh_access_token",
            new=AsyncMock(return_value=token_response),
        ),
        patch(
            "custom_components.bravia_quad.grpc.credentials.async_get_session_keys",
            new=AsyncMock(return_value=session_keys),
        ),
    ):
        refreshed = await async_refresh_credentials(session, previous)

    assert refreshed["key_id"] == "new-key"
    assert refreshed["refresh_token"] == "rt-old"


async def test_async_refresh_credentials_http_error() -> None:
    session = AsyncMock()
    previous = {"device_id": "dev-1", "refresh_token": "rt-old"}

    with (
        patch(
            "custom_components.bravia_quad.grpc.credentials.async_refresh_access_token",
            new=AsyncMock(side_effect=GrpcCredentialsRefreshError("HTTP 401")),
        ),
        pytest.raises(GrpcCredentialsRefreshError),
    ):
        await async_refresh_credentials(session, previous)


def test_build_credentials_bundle_preserves_refresh_token() -> None:
    session_keys = {
        "device_id": "dev",
        "key_id": "kid",
        "session_key": "sk",
        "hmac_key": "hk",
        "expires_in": 86400,
    }
    token_response = {"access_token": "at-new", "expires_in": 3600}
    previous = {"refresh_token": "rt-old"}
    bundle = build_credentials_bundle(session_keys, token_response, previous=previous)
    assert bundle["access_token"] == "at-new"
    assert bundle["refresh_token"] == "rt-old"
    assert json.loads(credentials_to_json(bundle))["session_key"] == "sk"
