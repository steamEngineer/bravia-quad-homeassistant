"""Sync gRPC client for Bravia Theatre (h2c on port 55051)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import grpc

from ..grpc_value_normalize import grpc_exec_unavailable_reason
from .bravia_control_pb2 import (
    ConfirmKeysRequest,
    ConfirmSigninRequest,
    ExecCommandWithAuthResponse,
    FieldListRequest,
    GetSessionRandomRequest,
    GetStatesWithAuthRequest,
    GetStatesWithAuthResponse,
    StartNotifyStatesRequest,
)
from .bravia_control_pb2_grpc import ControlDeviceServiceStub
from .exec_command_request import (
    build_exec_command_with_auth_request,
    legacy_value_to_kwargs,
    parse_exec_response,
    sign_exec_auth_token,
)
from .get_nonce_request import build_get_nonce_request, parse_get_nonce_response
from .get_states_auth import (
    build_get_states_signing_preimage,
    build_mutex_signing_preimage,
    sign_get_states_auth_token,
    sign_get_states_request_body,
)
from .get_states_request import (
    build_get_states_with_auth_request,
    build_small_get_states_with_auth_request,
    extract_auth_token_from_states_response,
    load_field_paths,
)
from .get_states_response import parse_get_states_response
from .notify_decode import decode_notify_delta

_LOGGER = logging.getLogger(__name__)
_DOMAIN_LOGGER = logging.getLogger("custom_components.bravia_quad")


@dataclass(frozen=True, slots=True)
class NotifyStateUpdate:
    """Single field delta from StartNotifyStates."""

    path: str
    value: Any


class BraviaGrpcClient:
    """Client for communicating with Bravia devices via gRPC over h2c"""

    def __init__(self, host: str, port: int = 55051, debug: bool = False):
        """
        Initialize the Bravia gRPC client

        Args:
            host: IP address or hostname of the Bravia device
            port: Port number (default: 55051)
            debug: Enable debug output (default: False)

        """
        self.host = host
        self.port = port
        self.channel = None
        self.stub = None
        self.session_id = None
        self.session_random = None
        self.auth_token = None
        self.nonce = None
        self.nonce_hmac = None
        self.session_key_hex: str | None = None
        self.hmac_key_hex: str | None = None
        self.authenticated = False
        self.debug = debug
        self._notify_state: dict[str, Any] = {}
        self._notify_stream: Any | None = None
        self.last_rpc_error: str | None = None
        self.last_error_is_transport = False

    @property
    def notify_state(self) -> dict[str, Any]:
        """Latest values from StartNotifyStates deltas (path → value)."""
        return dict(self._notify_state)

    def _say(self, msg: str) -> None:
        """Log normal gRPC client events."""
        _LOGGER.info("%s", msg)

    def _record_rpc_error(self, err: grpc.RpcError) -> None:
        """Remember the latest RPC failure and whether it is transport-level."""
        details = err.details() or ""
        self.last_rpc_error = f"{err.code()}: {details}"
        if err.code() != grpc.StatusCode.UNAVAILABLE:
            return
        lowered = details.lower()
        if "connection refused" in lowered or "failed to connect" in lowered:
            self.last_error_is_transport = True

    def _trace_enabled(self) -> bool:
        """Integration option or HA logger DEBUG for bravia_quad."""
        return (
            self.debug
            or _LOGGER.isEnabledFor(logging.DEBUG)
            or _DOMAIN_LOGGER.isEnabledFor(logging.DEBUG)
        )

    def _debug(self, msg: str) -> None:
        """Log verbose wire/session traces when gRPC tracing is enabled."""
        if not self._trace_enabled():
            return
        if self.debug:
            _LOGGER.info("[gRPC debug] %s", msg)
        else:
            _LOGGER.debug("%s", msg)

    def connect(self):
        """Establish gRPC connection using h2c (HTTP/2 cleartext)"""
        # Create insecure channel for h2c (HTTP/2 cleartext)
        # This is required for Bravia devices which use HTTP/2 without TLS
        target = f"{self.host}:{self.port}"

        # Use insecure channel for h2c
        # Note: The dump shows user-agent: dart-grpc/2.0.0, but Python gRPC uses different user-agent
        # This shouldn't matter for functionality, but noting it for reference
        # Keepalive settings adjusted to prevent "too_many_pings" errors from the device
        # The device rejects pings too frequently, so we use longer intervals or disable keepalive
        # For streaming calls, keepalive pings are not needed as the stream itself keeps the connection alive
        self.channel = grpc.insecure_channel(
            target,
            options=[
                # Keepalive settings: use longer intervals to avoid "too_many_pings" errors
                # Set to 30 seconds to be well above the device's threshold
                (
                    "grpc.keepalive_time_ms",
                    30000,
                ),  # Send keepalive ping every 30 seconds
                (
                    "grpc.keepalive_timeout_ms",
                    10000,
                ),  # Timeout for keepalive ping (10 seconds)
                (
                    "grpc.keepalive_permit_without_calls",
                    False,
                ),  # Don't ping when no active calls
                # HTTP/2 ping settings: use longer intervals
                ("grpc.http2.max_pings_without_data", 0),  # No pings without data
                (
                    "grpc.http2.min_time_between_pings_ms",
                    30000,
                ),  # Minimum 30 seconds between pings
                (
                    "grpc.http2.min_ping_interval_without_data_ms",
                    30000,
                ),  # Minimum 30 seconds for pings without data
                # Try to match the dump's behavior more closely
                ("grpc.http2.write_buffer_size", 65536),
            ],
        )

        self.stub = ControlDeviceServiceStub(self.channel)
        # Channel is lazy; TCP is not verified until the first RPC.
        self._debug(f"Created gRPC channel for {target}")

    def disconnect(self):
        """Close the gRPC connection"""
        if self._notify_stream is not None:
            self._notify_stream.cancel()
            self._notify_stream = None
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
            self.authenticated = False

    def authenticate(
        self,
        device_key: str | None = None,
        session_key: str | None = None,
        hmac_key: str | None = None,
        key_id: str | None = None,
        device_id: str | None = None,
        skip_auth: bool = False,
    ) -> bool:
        """
        Authenticate with the Bravia device

        Args:
            device_key: Optional device key/password (legacy parameter)
            session_key: Hex-encoded session key (64 chars = 32 bytes) - not used for auth_data
            hmac_key: Hex-encoded HMAC key (64 chars = 32 bytes) for ConfirmKeys
            key_id: Optional key ID (UUID) to use as session_id (from key generation API response)
            device_id: Device ID (UUID string) - required for generating auth_data (SHA256 hash)
            skip_auth: If True, skip authentication and try to use methods directly
                       (may work for some read-only operations)

        Returns:
            True if session established successfully, False otherwise

        Note:
            The device requires:
            - device_id: Used to generate auth_data for ConfirmSignin (SHA256(device_id))
            - hmac_key: Used to HMAC session_id for ConfirmKeys key_data (32 bytes)
            - key_id: Optional - if provided, used as session_id (same UUID for ConfirmKeys and GetSessionRandom)

            auth_data is SHA256(device_id) - device-specific, not session-specific.

        """
        self.last_rpc_error = None
        self.last_error_is_transport = False
        try:
            # If skip_auth is True, try to proceed without authentication
            if skip_auth:
                # Generate a dummy session_id and try to use methods directly
                self.session_id = str(uuid.uuid4())
                self.session_random = b"\x00" * 8
                self.auth_token = b"\x00" * 32
                self.authenticated = True
                self._say("Skipping authentication - attempting direct access")
                self._say(
                    "Note: Some operations may fail without proper authentication"
                )
                return True

            # Step 1: Generate or use provided session ID
            # If key_id is provided, use it as session_id (from key generation API)
            # Otherwise generate a new UUID4
            if key_id:
                self.session_id = key_id
            else:
                self.session_id = str(uuid.uuid4())
            if session_key:
                self.session_key_hex = session_key
            if hmac_key:
                self.hmac_key_hex = hmac_key

            # Step 1.5: Try ConfirmSignin and ConfirmKeys first (dump shows this order)
            # The dump shows: ConfirmSignin -> ConfirmKeys -> GetSessionRandom
            # And GetSessionRandom uses the SAME session_id as ConfirmKeys
            try:
                # Try ConfirmSignin
                # HYPOTHESIS: ConfirmSignin might be optional or might accept any 32-byte value
                # The dump shows different auth_data bytes, suggesting it might be device/session specific
                # But ConfirmKeys/GetSessionRandom work even when ConfirmSignin returns false
                signin_req = ConfirmSigninRequest()
                if device_id:
                    # auth_data is SHA256(device_id) - device-specific
                    signin_req.auth_data = self._generate_auth_data(device_id)
                elif device_key:
                    # Fallback: try treating device_key as device_id (legacy support)
                    signin_req.auth_data = self._generate_auth_data(device_key)
                else:
                    # Try with 32 zero bytes - maybe device accepts it
                    signin_req.auth_data = b"\x00" * 32

                try:
                    # Serialize to compare with dump
                    serialized_req = signin_req.SerializeToString()
                    self._debug(
                        f"ConfirmSignin request: auth_data={len(signin_req.auth_data)} bytes"
                    )
                    self._debug(
                        f"ConfirmSignin auth_data hex: {signin_req.auth_data.hex()}"
                    )
                    self._debug(
                        f"ConfirmSignin serialized request length: {len(serialized_req)} bytes"
                    )
                    self._debug(f"ConfirmSignin serialized hex: {serialized_req.hex()}")
                    if self.debug:
                        dump_auth_data = bytes.fromhex(
                            "258d61cc06d121a81e56d39b939b32267f144b30c3d858cfafdb03283cd23ebf"
                        )
                        self._debug(
                            f"Dump auth_data (for comparison): {dump_auth_data.hex()}"
                        )
                        self._debug(
                            "Our auth_data matches dump format: "
                            f"{len(signin_req.auth_data) == len(dump_auth_data)}"
                        )
                    signin_resp = self.stub.ConfirmSignin(signin_req)
                    signin_success = (
                        signin_resp.success
                        if hasattr(signin_resp, "success")
                        else False
                    )
                    self._debug(f"ConfirmSignin response: success={signin_success}")
                    if not signin_success:
                        self._say(
                            "ConfirmSignin failed: The device rejected the authentication credentials"
                        )
                        self._say(f"  auth_data: {signin_req.auth_data.hex()[:64]}...")
                        self._say("  This indicates the session_key may be:")
                        self._say("    - Expired or invalid")
                        self._say("    - For a different device/session")
                        self._say("    - Requiring transformation before use")
                        # Still continue to try ConfirmKeys - maybe it will work anyway
                        # (some devices might accept ConfirmKeys even if ConfirmSignin fails)
                except grpc.RpcError as e:
                    self._debug(f"ConfirmSignin error: {e.code()} - {e.details()}")
                    self._record_rpc_error(e)
                    # Continue anyway

                # Try ConfirmKeys with the session_id (dump shows this before GetSessionRandom)
                keys_req = ConfirmKeysRequest()
                keys_req.session_id = self.session_id
                if hmac_key:
                    # Use hmac_key to HMAC the session_id
                    keys_req.key_data = self._generate_key_data(
                        hmac_key, self.session_id
                    )
                elif device_key:
                    # Fallback to old method
                    keys_req.key_data = self._generate_key_data(
                        device_key, self.session_id
                    )
                else:
                    # Dump shows key_data is 32 bytes - maybe it's required even without a key
                    # Try with 32 zero bytes (dummy data)
                    keys_req.key_data = b"\x00" * 32

                try:
                    self._debug(
                        f"ConfirmKeys request: session_id={self.session_id}, "
                        f"key_data={len(keys_req.key_data)} bytes"
                    )
                    self.stub.ConfirmKeys(keys_req)
                    self._debug("ConfirmKeys succeeded")
                except grpc.RpcError as e:
                    self._debug(f"ConfirmKeys error: {e.code()} - {e.details()}")
                    self._record_rpc_error(e)
                    # Continue anyway - maybe GetSessionRandom will work
            except Exception as e:
                self._debug(f"Auth setup exception: {type(e).__name__} - {e}")

            # App order (libapp.so): ConfirmSignin → ConfirmKeys → GetNonce → GetSessionRandom
            self._fetch_nonce()

            # Step 2: GetSessionRandom with the same session_id as ConfirmKeys
            try:
                session_req = GetSessionRandomRequest(session_id=self.session_id)

                self._debug(f"GetSessionRandom request: session_id={self.session_id}")

                session_resp = self.stub.GetSessionRandom(session_req)

                self._debug("GetSessionRandom response received")
                self._debug(
                    "session_random length: "
                    f"{len(session_resp.session_random) if session_resp.session_random else 0}"
                )
                self._debug(
                    "auth_token length: "
                    f"{len(session_resp.auth_token) if session_resp.auth_token else 0}"
                )
                self.session_random = session_resp.session_random
                self.auth_token = session_resp.auth_token
            except grpc.RpcError as e:
                self._say(f"GetSessionRandom error: {e.code()} - {e.details()}")
                self._record_rpc_error(e)
                if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                    self._say(
                        "Invalid argument - the request format may not match device expectations"
                    )
                    self._say(f"  Session ID: {self.session_id}")
                    self._say("  This might indicate a proto definition mismatch")
                return False
            except Exception:
                raise

            # Step 3: Confirm signin (if keys provided) - this is now handled above
            # Legacy code path - kept for backward compatibility
            if device_key and not session_key and not hmac_key:
                try:
                    # Legacy: Generate auth data - try device_key as device_id
                    # Note: This is legacy code path, should use device_id parameter instead
                    auth_data = self._generate_auth_data(
                        device_key
                    )  # Treating device_key as device_id
                    signin_req = ConfirmSigninRequest(auth_data=auth_data)
                    signin_resp = self.stub.ConfirmSignin(signin_req)

                    if not signin_resp.success:
                        self._say("Signin confirmation failed")
                        # Continue anyway - some operations may work

                    # Step 4: Confirm keys
                    key_data = self._generate_key_data(device_key, self.session_id)
                    keys_req = ConfirmKeysRequest(
                        session_id=self.session_id, key_data=key_data
                    )
                    self.stub.ConfirmKeys(keys_req)
                except grpc.RpcError as e:
                    self._say(
                        f"Authentication with key failed: {e.code()} - {e.details()}"
                    )
                    self._say(
                        "Continuing without full authentication - some operations may work"
                    )

            # Mark as authenticated if we got session data
            if self.session_random and self.auth_token:
                self.authenticated = True
                self._say("Session established successfully")
                return True
            self._say("Failed to get session data")
            return False

        except Exception as e:
            self._say(f"Authentication error: {e}")
            # traceback
            _LOGGER.exception("gRPC client error")
            return False

    def _encode_varint(self, value: int) -> bytes:
        """
        Encode an integer as a protobuf varint

        Args:
            value: Integer to encode

        Returns:
            Bytes representing the varint-encoded value

        """
        result = bytearray()
        while value > 0x7F:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value & 0x7F)
        return bytes(result)

    def _generate_auth_data(self, device_id: str) -> bytes:
        """
        Generate authentication data from device ID

        Args:
            device_id: Device ID (UUID string)

        Returns:
            32 bytes of auth_data (SHA256 hash of device_id)

        Note:
            auth_data is simply SHA256(device_id) - it's device-specific,
            not derived from session_key or hmac_key.

        """
        return hashlib.sha256(device_id.encode("utf-8")).digest()

    def _generate_key_data(self, hmac_key: str, session_id: str) -> bytes:
        """
        Generate key confirmation data using HMAC key

        Args:
            hmac_key: Hex-encoded HMAC key (64 chars = 32 bytes)
            session_id: Session ID string to sign

        Returns:
            32 bytes of key_data (HMAC signature)

        """
        # HMAC key is provided as hex string, convert to bytes
        try:
            if len(hmac_key) == 64:
                key_bytes = bytes.fromhex(hmac_key)
            else:
                key_bytes = hmac_key.encode("utf-8")[:32].ljust(32, b"\x00")
        except ValueError:
            key_bytes = hmac_key.encode("utf-8")[:32].ljust(32, b"\x00")

        # HMAC the session_id with the HMAC key
        # Using SHA256 as that's standard for HMAC
        return hmac.new(key_bytes, session_id.encode("utf-8"), hashlib.sha256).digest()

    def _fetch_nonce(self) -> bool:
        """Call GetNonce (app auth chain step before GetSessionRandom)."""
        if not self.session_id or not self.channel:
            return False
        method = "/jp.co.sony.hes.ssh.controldevice.v1.ControlDeviceService/GetNonce"
        unary = self.channel.unary_unary(
            method,
            request_serializer=lambda payload: payload,
            response_deserializer=lambda payload: payload,
        )
        try:
            raw = unary.future(build_get_nonce_request(self.session_id)).result()
        except grpc.RpcError as e:
            self._say(f"GetNonce error: {e.code()} - {e.details()}")
            self._record_rpc_error(e)
            return False
        parsed = parse_get_nonce_response(raw)
        if not parsed:
            self._say("GetNonce response parse failed")
            return False
        self.nonce, self.nonce_hmac = parsed
        self._debug(f"GetNonce nonce={self.nonce.hex()} hmac={self.nonce_hmac.hex()}")
        return True

    def _is_valid_uuid(self, uuid_string: str) -> bool:
        """Check if string is a valid UUID"""
        try:
            uuid.UUID(uuid_string)
            return True
        except:
            return False

    def _get_states_unary_callable(self):
        method = (
            "/jp.co.sony.hes.ssh.controldevice.v1.ControlDeviceService/"
            "GetStatesWithAuth"
        )
        return self.channel.unary_unary(
            method,
            request_serializer=lambda payload: (
                payload if isinstance(payload, bytes) else payload.SerializeToString()
            ),
            response_deserializer=lambda payload: payload,
        )

    def get_states_raw(self, request_bytes: bytes) -> tuple[bytes | None, str | None]:
        """
        Send raw GetStatesWithAuth bytes.

        Returns (response_bytes, error_message).
        """
        if not self.authenticated:
            return None, "not authenticated"
        try:
            response = self._get_states_unary_callable().future(request_bytes).result()
            return response, None
        except grpc.RpcError as e:
            return None, f"{e.code().name}: {e.details()}"

    def _apply_get_states_response_tokens(self, raw: bytes) -> None:
        next_token = extract_auth_token_from_states_response(raw)
        if next_token:
            self.auth_token = next_token
        try:
            resp = GetStatesWithAuthResponse()
            resp.ParseFromString(raw)
            # Quad overloads session_random on GetStates RX; only accept 8-byte wire value.
            if resp.session_random and len(resp.session_random) == 8:
                self.session_random = resp.session_random
            if resp.auth_token:
                self.auth_token = resp.auth_token
            if resp.session_id:
                self.session_id = resp.session_id
        except Exception:
            pass

    def get_states_dict(
        self,
        field_paths: list[str] | None = None,
        *,
        auth_token: bytes | None = None,
        use_signed_auth: bool = False,
    ) -> dict[str, Any] | None:
        """GetStatesWithAuth returning parsed ``{path: value}`` dict."""
        if not self.authenticated:
            self._say("Not authenticated. Call authenticate() first.")
            return None
        paths = field_paths or load_field_paths()
        token = auth_token if auth_token is not None else self.auth_token
        if use_signed_auth and self.hmac_key_hex:
            inner_parts = b"".join(
                b"\x0a" + self._encode_varint(len(p.encode())) + p.encode()
                for p in paths
            )
            nested = b"\x0a" + self._encode_varint(len(inner_parts)) + inner_parts
            preimage = build_get_states_signing_preimage(
                nested,
                session_random=self.session_random,
                session_id=self.session_id,
            )
            token = sign_get_states_auth_token(self.hmac_key_hex, preimage)
        request_bytes = build_get_states_with_auth_request(
            paths,
            session_random=self.session_random,
            session_id=self.session_id,
            auth_token=token,
        )
        raw, err = self.get_states_raw(request_bytes)
        if err or not raw:
            if field_paths is not None and len(field_paths) != len(load_field_paths()):
                _LOGGER.debug("GetStates batch (%d paths) failed: %s", len(paths), err)
            else:
                self._say(f"GetStates error: {err}")
            return None
        self._apply_get_states_response_tokens(raw)
        return parse_get_states_response(raw)

    def get_states_single_path(
        self,
        field_path: str,
        *,
        use_signed_auth: bool = False,
        quiet: bool = False,
    ) -> dict[str, Any] | None:
        """GetStates for one field path (small wire request, app-setting safe)."""
        if not self.authenticated:
            if not quiet:
                self._say("Not authenticated. Call authenticate() first.")
            return None
        token = self.auth_token
        if use_signed_auth and self.hmac_key_hex:
            preimage = build_mutex_signing_preimage(
                field_path,
                session_random=self.session_random,
                session_id=self.session_id,
            )
            token = sign_get_states_auth_token(self.hmac_key_hex, preimage)
        request_bytes = build_small_get_states_with_auth_request(
            field_path,
            session_random=self.session_random,
            session_id=self.session_id,
            auth_token=token,
        )
        raw, err = self.get_states_raw(request_bytes)
        if err or not raw:
            if quiet:
                _LOGGER.debug("GetStates %s failed: %s", field_path, err)
            else:
                self._say(f"GetStates error: {err}")
            return None
        self._apply_get_states_response_tokens(raw)
        parsed = parse_get_states_response(raw)
        if parsed:
            self._notify_state.update(parsed)
        return parsed

    @staticmethod
    def _encode_varint(value: int) -> bytes:
        out = bytearray()
        while value > 0x7F:
            out.append((value & 0x7F) | 0x80)
            value >>= 7
        out.append(value)
        return bytes(out)

    def acquire_client_mutex(self, *, use_signed_auth: bool = False) -> bool:
        """Send mutex-path GetStatesWithAuth (``client_control.mutex.any``)."""
        if not self.session_id or not self.session_random or not self.auth_token:
            return False
        path = "client_control.mutex.any"
        token_candidates: list[bytes] = [self.auth_token]
        if use_signed_auth and self.hmac_key_hex:
            preview = build_small_get_states_with_auth_request(
                path,
                session_random=self.session_random,
                session_id=self.session_id,
                auth_token=b"\x00" * 32,
            )
            token_candidates.append(
                sign_get_states_request_body(self.hmac_key_hex, preview)
            )
        for token in token_candidates:
            request_bytes = build_small_get_states_with_auth_request(
                path,
                session_random=self.session_random,
                session_id=self.session_id,
                auth_token=token,
            )
            raw, err = self.get_states_raw(request_bytes)
            if err or not raw:
                continue
            self._apply_get_states_response_tokens(raw)
            return True
        self._say("Mutex GetStates failed for all auth token candidates")
        return False

    def get_states_app_sequence(
        self,
        *,
        mutex_repeats: int = 2,
        notify_brief: bool = True,
    ) -> dict[str, Any] | None:
        """
        Mirror BRAVIA Connect GetStates flow (Frida capture on fw 001.454).

        Order: HMAC-signed full snapshot → StartNotifyStates → signed mutex (×N).
        """
        if not self.authenticated:
            self._say("Not authenticated. Call authenticate() first.")
            return None
        paths = load_field_paths()
        full_token = self.auth_token
        if self.hmac_key_hex:
            inner_parts = b"".join(
                b"\x0a" + self._encode_varint(len(p.encode())) + p.encode()
                for p in paths
            )
            nested = b"\x0a" + self._encode_varint(len(inner_parts)) + inner_parts
            preimage = build_get_states_signing_preimage(
                nested,
                session_random=self.session_random,
                session_id=self.session_id,
            )
            full_token = sign_get_states_auth_token(self.hmac_key_hex, preimage)
        full_req = build_get_states_with_auth_request(
            paths,
            session_random=self.session_random,
            session_id=self.session_id,
            auth_token=full_token,
        )
        raw, err = self.get_states_raw(full_req)
        if err or not raw:
            self._say(f"App-sequence full GetStates error: {err}")
            return None
        self._apply_get_states_response_tokens(raw)
        snapshot = parse_get_states_response(raw)

        if notify_brief:
            stop = threading.Event()

            def _notify_worker() -> None:
                try:
                    req = StartNotifyStatesRequest(session_id=self.session_id)
                    for resp in self.stub.StartNotifyStates(req):
                        if resp.auth_token:
                            self.auth_token = resp.auth_token
                        delta_blob = resp.session_random
                        if delta_blob:
                            path, value = decode_notify_delta(delta_blob)
                            if path:
                                self._notify_state[path] = value
                        if stop.is_set():
                            break
                except Exception:
                    pass

            worker = threading.Thread(target=_notify_worker, daemon=True)
            worker.start()
            time.sleep(0.3)
            stop.set()
            worker.join(timeout=1.0)

        for i in range(mutex_repeats):
            if not self.acquire_client_mutex(use_signed_auth=True):
                self._say(f"App-sequence mutex GetStates #{i + 1} failed")
                return snapshot or None

        return snapshot or self.get_states_dict(use_signed_auth=True)

    def get_states_with_preflight(
        self,
        *,
        use_signed_auth: bool = False,
    ) -> dict[str, Any] | None:
        """Mutex preflight then full GetStates snapshot."""
        if not self.acquire_client_mutex(use_signed_auth=use_signed_auth):
            return None
        return self.get_states_dict(use_signed_auth=use_signed_auth)

    def get_states(
        self, field_list: FieldListRequest | None = None
    ) -> FieldListRequest | None:
        """Get device states via GetStatesWithAuth (unary snapshot)."""
        if not self.authenticated:
            self._say("Not authenticated. Call authenticate() first.")
            return None

        if field_list is not None:
            return self._get_states_protobuf(field_list)

        parsed = self.get_states_with_preflight()
        if parsed is None:
            parsed = self.get_states_dict()
        if parsed is None:
            return None
        # ponytail: minimal FieldListRequest shim for callers expecting proto object
        field_list_obj = FieldListRequest()
        if "power" in parsed:
            field_list_obj.power = str(parsed["power"])
        if "mute" in parsed:
            field_list_obj.mute = str(parsed["mute"])
        if "volume" in parsed:
            field_list_obj.volume = str(parsed["volume"])
        return field_list_obj

    def _get_states_protobuf(
        self, field_list: FieldListRequest
    ) -> FieldListRequest | None:
        """Legacy protobuf-shaped GetStatesWithAuth (known to fail on Quad)."""
        try:
            req = GetStatesWithAuthRequest(
                field_list=field_list,
                session_random=self.session_random,
                session_id=self.session_id,
                auth_token=self.auth_token,
            )
            resp = self.stub.GetStatesWithAuth(req)
            if resp.session_random:
                self.session_random = resp.session_random
            if resp.auth_token:
                self.auth_token = resp.auth_token
            return resp.states
        except grpc.RpcError as e:
            self._say(f"GetStates error: {e.code()} - {e.details()}")
            return None

    def collect_notify_snapshot(
        self,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        """
        Accumulate StartNotifyStates deltas until ``timeout`` elapses.

        Blocks until the first notify or ``timeout`` (stream open with no deltas).
        Prefer an active notify loop; for reads use ``notify_state`` after changes.
        """
        if not self.authenticated:
            return {}

        stop_at = time.monotonic() + timeout

        def worker() -> None:
            try:
                req = StartNotifyStatesRequest(session_id=self.session_id)
                for resp in self.stub.StartNotifyStates(req):
                    if resp.auth_token:
                        self.auth_token = resp.auth_token
                    if resp.session_id:
                        self.session_id = resp.session_id
                    delta_blob = resp.session_random
                    if delta_blob:
                        path, value = decode_notify_delta(delta_blob)
                        if path:
                            self._notify_state[path] = value
                    if time.monotonic() >= stop_at:
                        return
            except grpc.RpcError as e:
                self._say(f"collect_notify_snapshot error: {e.code()} - {e.details()}")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout + 0.5)
        if thread.is_alive():
            # Unblock the streaming RPC by closing the channel.
            self.disconnect()
        return dict(self._notify_state)

    def _sign_exec_auth_token(
        self,
        command_path: str,
        **exec_kwargs: int | bool | str,
    ) -> bool:
        """
        Compute rolling ExecCommandWithAuth auth_token via HMAC-SHA256.

        Frida capture (fw 3.9.1): ``HMAC-SHA256(hmac_key, exec_preimage)``.
        """
        if not self.session_id or not self.session_random:
            return False
        if not self.hmac_key_hex:
            self._say("Exec auth requires hmac_key from Sony Seeds keys")
            return False
        try:
            self.auth_token = sign_exec_auth_token(
                self.hmac_key_hex,
                command_path,
                session_random=self.session_random,
                session_id=self.session_id,
                **exec_kwargs,
            )
        except ValueError as exc:
            self._say(f"Exec auth sign error: {exc}")
            return False
        return True

    def _preflight_exec_auth_token(self) -> bool:
        """
        Obtain a rolling auth_token via GetStatesWithAuth (app mutex chain).

        BRAVIA Connect typically runs full snapshot GetStates, then
        ``client_control.mutex.any``, before ExecCommand. The response
        auth_token signs the exec body (GetSessionRandom token alone is not
        enough on fw 001.454).
        """
        if not self.session_id or not self.session_random or not self.auth_token:
            return False

        method = (
            "/jp.co.sony.hes.ssh.controldevice.v1.ControlDeviceService/"
            "GetStatesWithAuth"
        )
        unary_callable = self.channel.unary_unary(
            method,
            request_serializer=lambda payload: (
                payload if isinstance(payload, bytes) else payload.SerializeToString()
            ),
            response_deserializer=lambda payload: payload,
        )
        auth = self.auth_token

        def _try_get_states(label: str, request_bytes: bytes) -> bool:
            try:
                response = unary_callable.future(request_bytes).result()
            except grpc.RpcError as e:
                self._say(
                    f"Exec preflight GetStates ({label}) error: "
                    f"{e.code()} - {e.details()}"
                )
                return False
            next_token = extract_auth_token_from_states_response(response)
            if not next_token:
                self._say(
                    f"Exec preflight GetStates ({label}) response missing auth_token"
                )
                return False
            nonlocal auth
            auth = next_token
            return True

        try:
            field_paths = load_field_paths()
        except ValueError:
            field_paths = None

        if field_paths:
            full_request = build_get_states_with_auth_request(
                field_paths,
                session_random=self.session_random,
                session_id=self.session_id,
                auth_token=auth,
            )
            _try_get_states("full", full_request)

        small_request = build_small_get_states_with_auth_request(
            "client_control.mutex.any",
            session_random=self.session_random,
            session_id=self.session_id,
            auth_token=auth,
        )
        if not _try_get_states("mutex", small_request):
            return False
        self.auth_token = auth
        return True

    def _refresh_session_tokens(self) -> bool:
        """Rotate session_random/auth_token via GetSessionRandom."""
        if not self.session_id:
            return False
        try:
            session_resp = self.stub.GetSessionRandom(
                GetSessionRandomRequest(session_id=self.session_id)
            )
        except grpc.RpcError as e:
            self._say(f"GetSessionRandom refresh error: {e.code()} - {e.details()}")
            return False
        self.session_random = session_resp.session_random
        self.auth_token = session_resp.auth_token
        if session_resp.session_id:
            self.session_id = session_resp.session_id
        return True

    def exec_command(
        self,
        command_path: str,
        value: Any = None,
        string_value: str | None = None,
        *,
        int_value: int | None = None,
        bool_value: bool | None = None,
    ) -> bool:
        """
        Execute a command on the device.

        Args:
            command_path: Path to the command (e.g., "sound_setting.sound_effect")
            value: Deprecated positional int/bool shim for legacy callers
            string_value: String enum value (bass, sound_effect, …)
            int_value: Absolute integer target (volume, rear level, …)
            bool_value: On/off for bool command paths

        Returns:
            True if command executed successfully, False otherwise

        """
        if not self.authenticated:
            self._say("Not authenticated. Call authenticate() first.")
            return False

        exec_kwargs: dict[str, int | bool | str] = {}
        if string_value is not None:
            exec_kwargs["string_value"] = string_value
        elif int_value is not None:
            exec_kwargs["int_value"] = int_value
        elif bool_value is not None:
            exec_kwargs["bool_value"] = bool_value
        elif value is not None:
            exec_kwargs.update(legacy_value_to_kwargs(command_path, int(value)))

        if not exec_kwargs:
            self._say("ExecCommand requires int_value, bool_value, or string_value")
            return False

        if grpc_exec_unavailable_reason(self._notify_state, command_path):
            self._debug("ExecCommand blocked (unavailable): %s", command_path)
            return False

        if not self._sign_exec_auth_token(command_path, **exec_kwargs):
            return False

        try:
            manual_request_bytes = build_exec_command_with_auth_request(
                command_path,
                session_random=self.session_random,
                session_id=self.session_id,
                auth_token=self.auth_token,
                **exec_kwargs,
            )
            method = (
                "/jp.co.sony.hes.ssh.controldevice.v1.ControlDeviceService/"
                "ExecCommandWithAuth"
            )
            unary_callable = self.channel.unary_unary(
                method,
                request_serializer=lambda payload: (
                    payload
                    if isinstance(payload, bytes)
                    else payload.SerializeToString()
                ),
                response_deserializer=lambda payload: payload,
            )
            response = unary_callable.future(manual_request_bytes).result()
            self._debug(
                f"ExecCommand {command_path} {exec_kwargs} "
                f"tx={len(manual_request_bytes)}B rx={len(response)}B"
            )
            success = parse_exec_response(response)
            if not success:
                resp = ExecCommandWithAuthResponse()
                resp.ParseFromString(response)
                success = resp.success
            unavailable = grpc_exec_unavailable_reason(self._notify_state, command_path)
            if (
                success
                and unavailable is None
                and command_path != "playback_control.playback_command"
            ):
                self._cache_exec_value(command_path, exec_kwargs)
            return success

        except grpc.RpcError as e:
            self._say(f"ExecCommand error: {e.code()} - {e.details()}")
            return False

    def _cache_exec_value(
        self, command_path: str, exec_kwargs: dict[str, int | bool | str]
    ) -> None:
        """Mirror a successful exec into notify_state before the stream delta arrives."""
        if "string_value" in exec_kwargs:
            self._notify_state[command_path] = exec_kwargs["string_value"]
        elif "bool_value" in exec_kwargs:
            self._notify_state[command_path] = exec_kwargs["bool_value"]
        elif "int_value" in exec_kwargs:
            self._notify_state[command_path] = exec_kwargs["int_value"]

    def start_notify_states(self) -> Iterator[NotifyStateUpdate]:
        """
        Start receiving state change notifications (streaming).

        Yields decoded field-path deltas from ``session_random`` (proto mislabel).
        """
        if not self.authenticated:
            self._say("Not authenticated. Call authenticate() first.")
            return iter([])

        try:
            req = StartNotifyStatesRequest(session_id=self.session_id)

            stream = self.stub.StartNotifyStates(req)
            self._notify_stream = stream
            try:
                for resp in stream:
                    if resp.auth_token:
                        self.auth_token = resp.auth_token
                    if resp.session_id:
                        self.session_id = resp.session_id

                    delta_blob = resp.session_random
                    if not delta_blob:
                        continue
                    path, value = decode_notify_delta(delta_blob)
                    if not path:
                        continue
                    self._notify_state[path] = value
                    self._debug(f"Notify {path}={value!r}")
                    yield NotifyStateUpdate(path=path, value=value)
            finally:
                if self._notify_stream is stream:
                    self._notify_stream = None

        except grpc.RpcError as e:
            self._say(f"StartNotifyStates error: {e.code()} - {e.details()}")
            if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                self._say(
                    "Invalid argument - session may have expired, try re-authenticating"
                )
        except Exception:
            _LOGGER.exception("StartNotifyStates error")

    def get_power_state(self) -> str | None:
        """Get current power state."""
        cached = self._notify_state.get("power")
        if cached is not None:
            if isinstance(cached, str):
                return cached
            if isinstance(cached, bool):
                return "on" if cached else "off"
            if isinstance(cached, int):
                return "on" if cached else "off"
        states = self.get_states()
        if states:
            return states.power
        return None

    def set_power(self, on: bool) -> bool:
        """Set power state"""
        return self.exec_command("power", value=1 if on else 0)

    def get_mute_state(self) -> str | None:
        """Get current mute state."""
        cached = self._notify_state.get("mute")
        if cached is not None:
            if isinstance(cached, str):
                return cached
            if isinstance(cached, bool):
                return "on" if cached else "off"
            if isinstance(cached, int):
                return "on" if cached else "off"
        states = self.get_states()
        if states:
            return states.mute
        return None

    def set_mute(self, muted: bool) -> bool:
        """Set mute state"""
        return self.exec_command("mute", value=1 if muted else 0)

    def get_volume(self) -> str | None:
        """Get current volume."""
        cached = self._notify_state.get("volume")
        if cached is not None:
            return str(cached)
        states = self.get_states()
        if states and hasattr(states, "sound_setting") and states.sound_setting:
            return getattr(states.sound_setting, "volume", None)
        return None

    def set_volume(self, volume: int) -> bool:
        """Set volume level"""
        return self.exec_command("volume", value=volume)

    def get_playback_info(self) -> dict[str, Any] | None:
        """Get current playback information"""
        states = self.get_states()
        if states and hasattr(states, "playback_control") and states.playback_control:
            pc = states.playback_control
            return {
                "title": getattr(pc, "title", None),
                "artist": getattr(pc, "artist", None),
                "album": getattr(pc, "album", None),
                "playback_state": getattr(pc, "playback_state", None),
                "position": getattr(pc, "position", None),
                "duration": getattr(pc, "duration", None),
                "service_name": getattr(pc, "service_name", None),
            }
        return None


def load_keys_from_file(file_path: str) -> dict[str, str]:
    """
    Load authentication keys from a JSON file

    Args:
        file_path: Path to JSON file containing keys

    Returns:
        Dictionary with keys: device_id, key_id, session_key, hmac_key, expires_in

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid

    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Keys file not found: {file_path}")

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    # Validate required fields
    required_fields = ["session_key", "hmac_key"]
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        raise ValueError(
            f"Missing required fields in keys file: {', '.join(missing_fields)}"
        )

    return {
        "device_id": data.get("device_id"),
        "key_id": data.get("key_id"),
        "session_key": data["session_key"],
        "hmac_key": data["hmac_key"],
        "auth_data": data.get(
            "auth_data"
        ),  # Optional auth_data field for ConfirmSignin
        "expires_in": data.get("expires_in", 86400),
    }
