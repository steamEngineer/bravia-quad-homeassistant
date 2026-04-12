#!/usr/bin/env python3
"""
Simulate a Bravia Quad device disconnect and reconnect scenario.

Starts a fake TCP server that mimics the Bravia Quad protocol, connects the
client, then kills the server to simulate a network drop. After a pause, the
server restarts and the client should automatically reconnect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

# Add the project root so custom_components is importable
sys.path.insert(0, "/workspaces/bravia-quad-homeassistant")

from custom_components.bravia_quad.bravia_quad_client import BraviaQuadClient
from custom_components.bravia_quad.const import DEFAULT_PORT

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
_LOGGER = logging.getLogger("simulate")

HOST = "127.0.0.1"
PORT = DEFAULT_PORT  # 33336


class FakeBraviaServer:
    """Minimal TCP server that speaks enough of the Bravia Quad protocol."""

    def __init__(self) -> None:
        self._server: asyncio.Server | None = None
        self._clients: list[asyncio.StreamWriter] = []

    async def start(self) -> None:
        """Start listening."""
        self._server = await asyncio.start_server(
            self._handle_client, HOST, PORT, reuse_address=True
        )
        _LOGGER.info("Fake Bravia server listening on %s:%s", HOST, PORT)

    async def stop(self) -> None:
        """Stop the server and close all client connections."""
        for writer in self._clients:
            writer.close()
        self._clients.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        _LOGGER.info("Fake Bravia server stopped")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single client connection."""
        peer = writer.get_extra_info("peername")
        _LOGGER.info("Client connected from %s", peer)
        self._clients.append(writer)

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace").strip()
                _LOGGER.debug("Received: %s", text)

                # Parse and respond to each JSON command
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cmd = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    cmd_type = cmd.get("type")
                    feature = cmd.get("feature", "")
                    cmd_id = cmd.get("id", 0)

                    if cmd_type == "get":
                        # Return a dummy value based on feature
                        value = self._get_value(feature)
                        resp = {
                            "id": cmd_id,
                            "type": "result",
                            "feature": feature,
                            "value": value,
                        }
                    elif cmd_type == "set":
                        resp = {
                            "id": cmd_id,
                            "type": "result",
                            "feature": feature,
                            "value": "ACK",
                        }
                    else:
                        resp = {"id": cmd_id, "type": "error", "value": "unknown"}

                    resp_json = json.dumps(resp) + "\n"
                    _LOGGER.debug("Sending: %s", resp_json.strip())
                    writer.write(resp_json.encode())
                    await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            _LOGGER.info("Client connection reset")
        except asyncio.CancelledError:
            pass
        finally:
            self._clients.discard(writer) if hasattr(self._clients, "discard") else None
            writer.close()
            _LOGGER.info("Client disconnected")

    @staticmethod
    def _get_value(feature: str) -> str | int:
        """Return a dummy value for a feature."""
        defaults: dict[str, str | int] = {
            "main.power": "on",
            "main.volumestep": 42,
            "main.input": "tv",
            "main.rearvolumestep": 0,
            "main.bassstep": 1,
            "audio.voiceenhancer": "upoff",
            "audio.soundfield": "off",
            "audio.nightmode": "off",
            "hdmi.cec": "off",
            "system.autostandby": "off",
            "audio.drangecomp": "auto",
            "audio.aav": "off",
            "main.mute": "off",
        }
        return defaults.get(feature, "off")


async def main() -> None:
    """Run the full disconnect/reconnect simulation."""
    server = FakeBraviaServer()
    await server.start()

    # --- Phase 1: Connect the client ---
    _LOGGER.info("=" * 60)
    _LOGGER.info("PHASE 1: Connecting client to fake server")
    _LOGGER.info("=" * 60)

    client = BraviaQuadClient(HOST, "SimTest")

    # Track availability changes
    availability_log: list[bool] = []

    def on_availability(available: bool) -> None:
        availability_log.append(available)
        _LOGGER.info(
            ">>> AVAILABILITY CHANGED: %s <<<",
            "AVAILABLE" if available else "UNAVAILABLE",
        )

    client.register_availability_callback(on_availability)

    await client.async_connect()
    _LOGGER.info("Client connected: %s", client.is_connected)

    await client.async_listen_for_notifications()
    _LOGGER.info("Notification listener started")

    # Fetch initial state
    await client.async_fetch_all_states()
    _LOGGER.info(
        "Initial state - Power: %s, Volume: %d, Input: %s",
        client.power_state,
        client.volume,
        client.input,
    )

    await asyncio.sleep(1)

    # --- Phase 2: Kill the server (simulate disconnect) ---
    _LOGGER.info("")
    _LOGGER.info("=" * 60)
    _LOGGER.info("PHASE 2: Stopping server to simulate disconnect")
    _LOGGER.info("=" * 60)

    await server.stop()

    # Wait for the client to detect the disconnect
    _LOGGER.info("Waiting for client to detect disconnect...")
    for i in range(10):
        await asyncio.sleep(1)
        _LOGGER.info(
            "  t+%ds  connected=%s  listening=%s",
            i + 1,
            client.is_connected,
            client._listening,
        )
        if not client.is_connected:
            _LOGGER.info("Client detected disconnect!")
            break

    assert not client.is_connected, "Client should have detected the disconnect"

    # --- Phase 3: Restart the server (simulate device coming back) ---
    _LOGGER.info("")
    _LOGGER.info("=" * 60)
    _LOGGER.info("PHASE 3: Restarting server to simulate reconnect")
    _LOGGER.info("=" * 60)

    await server.start()

    # Wait for the client to reconnect
    _LOGGER.info("Waiting for client to reconnect...")
    for i in range(15):
        await asyncio.sleep(1)
        _LOGGER.info(
            "  t+%ds  connected=%s  listening=%s",
            i + 1,
            client.is_connected,
            client._listening,
        )
        if client.is_connected:
            _LOGGER.info("Client reconnected!")
            break

    assert client.is_connected, "Client should have reconnected"

    # Verify state was refreshed
    _LOGGER.info(
        "State after reconnect - Power: %s, Volume: %d, Input: %s",
        client.power_state,
        client.volume,
        client.input,
    )

    # --- Phase 4: Clean up ---
    _LOGGER.info("")
    _LOGGER.info("=" * 60)
    _LOGGER.info("PHASE 4: Cleanup")
    _LOGGER.info("=" * 60)

    await client.async_disconnect()
    await server.stop()

    _LOGGER.info("")
    _LOGGER.info("=" * 60)
    _LOGGER.info("SIMULATION COMPLETE")
    _LOGGER.info("Availability transitions: %s", availability_log)
    expected = [False, True]
    if availability_log == expected:
        _LOGGER.info("SUCCESS: Availability changed as expected %s", expected)
    else:
        _LOGGER.error("UNEXPECTED: Expected %s but got %s", expected, availability_log)
        sys.exit(1)
    _LOGGER.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
