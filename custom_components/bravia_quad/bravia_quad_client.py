"""Client for communicating with Bravia Quad device."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from .const import (
    DEFAULT_PORT,
    TCP_TIMEOUT,
    CMD_ID_POWER,
    CMD_ID_VOLUME,
    CMD_ID_INPUT,
    FEATURE_POWER,
    FEATURE_VOLUME,
    FEATURE_INPUT,
    POWER_ON,
    POWER_OFF,
)

_LOGGER = logging.getLogger(__name__)


class BraviaQuadClient:
    """Client for Bravia Quad TCP communication."""

    def __init__(self, host: str, name: str) -> None:
        """Initialize the Bravia Quad client."""
        self.host = host
        self.port = DEFAULT_PORT
        self.name = name
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._listening = False
        self._notification_callbacks: dict[str, list[Callable]] = {}
        self._power_state = POWER_OFF
        self._volume = 0
        self._input = "tv"  # Default input
        self._command_id_counter = 10  # Start from 10 to avoid conflicts

    async def async_connect(self) -> None:
        """Connect to the Bravia Quad device."""
        if self._connected:
            return

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=TCP_TIMEOUT,
            )
            # Give the connection a moment to stabilize
            await asyncio.sleep(0.1)
            self._connected = True
            _LOGGER.info("Connected to Bravia Quad at %s:%s", self.host, self.port)
        except Exception as err:
            self._connected = False
            _LOGGER.error("Failed to connect to Bravia Quad: %s", err)
            raise

    async def async_disconnect(self) -> None:
        """Disconnect from the Bravia Quad device."""
        self._listening = False
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        self._connected = False
        _LOGGER.info("Disconnected from Bravia Quad")

    async def async_test_connection(self) -> bool:
        """Test connection by sending a power status request."""
        if not self._connected:
            await self.async_connect()

        try:
            command = {
                "id": CMD_ID_POWER,
                "type": "get",
                "feature": FEATURE_POWER,
            }
            response = await self.async_send_command(command)
            
            if response and response.get("type") == "result":
                if response.get("feature") == FEATURE_POWER:
                    self._power_state = response.get("value", POWER_OFF)
                    return True
            return False
        except Exception as err:
            _LOGGER.error("Test connection failed: %s", err)
            return False

    async def async_send_command(
        self, command: dict[str, Any], timeout: float = TCP_TIMEOUT
    ) -> dict[str, Any] | None:
        """Send a command and wait for response."""
        if not self._connected:
            await self.async_connect()

        if not self._writer or not self._reader:
            raise ConnectionError("Not connected to device")

        try:
            # Send command
            command_json = json.dumps(command) + "\n"
            _LOGGER.debug("Sending command: %s", command_json.strip())
            self._writer.write(command_json.encode())
            await self._writer.drain()
            _LOGGER.debug("Command sent, waiting for response...")

            # Wait for response - device sends JSON without newline, so read bytes directly
            # Read with timeout - device typically responds quickly
            try:
                data = await asyncio.wait_for(
                    self._reader.read(1024), timeout=timeout
                )
                
                if data:
                    # Device may send JSON with or without newline
                    response_str = data.decode("utf-8", errors="replace").strip()
                    _LOGGER.debug("Received response: %s", response_str)
                    
                    if response_str:
                        try:
                            response = json.loads(response_str)
                            _LOGGER.debug("Successfully parsed response")
                            return response
                        except json.JSONDecodeError as e:
                            _LOGGER.warning("Failed to parse JSON response: %s (data: %s)", e, response_str)
                            return None
                else:
                    _LOGGER.warning("Received empty response")
                    return None
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout waiting for response (timeout=%s)", timeout)
                return None
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout waiting for response to command: %s", command)
            return None
        except Exception as err:
            _LOGGER.error("Error sending command: %s", err)
            return None

    async def async_set_power(self, state: str) -> bool:
        """Set power state (on/off)."""
        command = {
            "id": CMD_ID_POWER,
            "type": "set",
            "feature": FEATURE_POWER,
            "value": state,
        }
        response = await self.async_send_command(command)
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
                self._power_state = state
                return True
        return False

    async def async_set_volume(self, volume: int) -> bool:
        """Set volume (0-100)."""
        if volume < 0 or volume > 100:
            raise ValueError("Volume must be between 0 and 100")
        
        command = {
            "id": CMD_ID_VOLUME,
            "type": "set",
            "feature": FEATURE_VOLUME,
            "value": volume,
        }
        response = await self.async_send_command(command)
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
                self._volume = volume
                return True
        return False

    async def async_get_power(self) -> str:
        """Get current power state."""
        command = {
            "id": CMD_ID_POWER,
            "type": "get",
            "feature": FEATURE_POWER,
        }
        response = await self.async_send_command(command)
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_POWER:
                self._power_state = response.get("value", POWER_OFF)
                return self._power_state
        return self._power_state

    async def async_get_volume(self) -> int:
        """Get current volume."""
        command = {
            "id": CMD_ID_VOLUME,
            "type": "get",
            "feature": FEATURE_VOLUME,
        }
        response = await self.async_send_command(command)
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_VOLUME:
                try:
                    volume = int(response.get("value", 0))
                    if 0 <= volume <= 100:
                        self._volume = volume
                        return self._volume
                except (ValueError, TypeError):
                    pass
        return self._volume

    async def async_set_input(self, input_value: str) -> bool:
        """Set input (tv, hdmi1, spotify)."""
        command = {
            "id": CMD_ID_INPUT,
            "type": "set",
            "feature": FEATURE_INPUT,
            "value": input_value,
        }
        response = await self.async_send_command(command)
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
                self._input = input_value
                return True
        return False

    async def async_get_input(self) -> str:
        """Get current input."""
        command = {
            "id": CMD_ID_INPUT,
            "type": "get",
            "feature": FEATURE_INPUT,
        }
        response = await self.async_send_command(command)
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_INPUT:
                self._input = response.get("value", "tv")
                return self._input
        return self._input

    def register_notification_callback(
        self, feature: str, callback: Callable
    ) -> None:
        """Register a callback for notifications."""
        if feature not in self._notification_callbacks:
            self._notification_callbacks[feature] = []
        self._notification_callbacks[feature].append(callback)

    async def async_listen_for_notifications(self) -> None:
        """Listen for real-time notifications from the device."""
        if self._listening:
            return

        if not self._connected:
            await self.async_connect()

        self._listening = True
        _LOGGER.info("Starting notification listener")

        while self._listening and self._connected:
            try:
                if not self._reader:
                    break

                # Read data - device may send JSON with or without newline
                data = await asyncio.wait_for(
                    self._reader.read(1024), timeout=1.0
                )
                
                if not data:
                    await asyncio.sleep(0.1)
                    continue

                try:
                    # Handle responses that may or may not have newlines
                    response_str = data.decode("utf-8", errors="replace").strip()
                    # If there's a newline, take the first line
                    if "\n" in response_str:
                        response_str = response_str.split("\n", 1)[0].strip()
                    
                    notification = json.loads(response_str)
                    
                    if notification.get("type") == "notify":
                        feature = notification.get("feature")
                        value = notification.get("value")
                        
                        _LOGGER.debug(
                            "Received notification: feature=%s, value=%s",
                            feature,
                            value,
                        )
                        
                        # Update internal state
                        if feature == FEATURE_POWER:
                            self._power_state = value
                        elif feature == FEATURE_VOLUME:
                            try:
                                self._volume = int(value)
                            except (ValueError, TypeError):
                                pass
                        elif feature == FEATURE_INPUT:
                            self._input = value
                        
                        # Call registered callbacks
                        if feature in self._notification_callbacks:
                            for callback in self._notification_callbacks[feature]:
                                try:
                                    if asyncio.iscoroutinefunction(callback):
                                        await callback(value)
                                    else:
                                        callback(value)
                                except Exception as err:
                                    _LOGGER.error(
                                        "Error in notification callback: %s", err
                                    )
                except json.JSONDecodeError:
                    _LOGGER.warning("Failed to parse notification: %s", data)
                except Exception as err:
                    _LOGGER.error("Error processing notification: %s", err)

            except asyncio.TimeoutError:
                # Timeout is expected, continue listening
                continue
            except Exception as err:
                _LOGGER.error("Error in notification listener: %s", err)
                await asyncio.sleep(1.0)

        _LOGGER.info("Notification listener stopped")

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected

    @property
    def power_state(self) -> str:
        """Return current power state."""
        return self._power_state

    @property
    def volume(self) -> int:
        """Return current volume."""
        return self._volume

    @property
    def input(self) -> str:
        """Return current input."""
        return self._input

