"""
Manual script to verify Bravia Quad connection (async version).

This script tests connectivity to a real Bravia Quad device using asyncio.
Mimics Home Assistant's async behavior for debugging.

Usage:
    python scripts/check_connection_async.py <host>
    python scripts/check_connection_async.py 192.168.1.100
"""

import asyncio
import contextlib
import json
import logging
import sys

logging.basicConfig(level=logging.DEBUG)

DEFAULT_PORT = 33336


async def check_async_connection(host: str, port: int = DEFAULT_PORT) -> bool:
    """
    Check async connection similar to Home Assistant.

    Args:
        host: IP address or hostname of the Bravia Quad device.
        port: Port number (default: 33336).

    Returns:
        True if connection test passed, False otherwise.

    """
    writer = None
    try:
        print(f"Connecting to {host}:{port}...")  # noqa: T201
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=10.0
        )
        print("Connected successfully!")  # noqa: T201

        # Give connection a moment to stabilize
        await asyncio.sleep(0.2)

        # Send test command
        command = {"id": 3, "type": "get", "feature": "main.power"}
        command_json = json.dumps(command) + "\n"
        print(f"Sending: {command_json.strip()}")  # noqa: T201

        writer.write(command_json.encode())
        await writer.drain()
        print("Command sent, waiting for response...")  # noqa: T201

        # Wait for response - device sends JSON without newline
        try:
            data = await asyncio.wait_for(reader.read(1024), timeout=10.0)
        except TimeoutError:
            print("Timeout waiting for response")  # noqa: T201
            return False

        if not data:
            print("Received empty response")  # noqa: T201
            return False

        response_str = data.decode("utf-8", errors="replace").strip()
        print(f"Response: {response_str}")  # noqa: T201

        try:
            response_data = json.loads(response_str)
        except json.JSONDecodeError as e:
            print(f"Failed to parse response: {e}")  # noqa: T201
            return False

        print(f"Parsed response: {json.dumps(response_data, indent=2)}")  # noqa: T201

        if (
            response_data.get("type") == "result"
            and response_data.get("feature") == "main.power"
        ):
            print("Connection test successful!")  # noqa: T201
            return True

        print("Unexpected response format")  # noqa: T201

    except OSError as e:
        print(f"Error: {e}")  # noqa: T201
        import traceback  # noqa: PLC0415

        traceback.print_exc()
    finally:
        if writer:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
        print("Connection closed")  # noqa: T201
    return False


def main() -> None:
    """Run the async connection check."""
    if len(sys.argv) < 2:  # noqa: PLR2004
        print(f"Usage: {sys.argv[0]} <host> [port]")  # noqa: T201
        print(f"Example: {sys.argv[0]} 192.168.1.100")  # noqa: T201
        sys.exit(1)

    host = sys.argv[1]
    try:
        port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT  # noqa: PLR2004
    except ValueError:
        print(f"Error: Invalid port number '{sys.argv[2]}'")  # noqa: T201
        print(f"Usage: {sys.argv[0]} <host> [port]")  # noqa: T201
        sys.exit(1)

    result = asyncio.run(check_async_connection(host, port))
    print(f"\nResult: {'PASSED' if result else 'FAILED'}")  # noqa: T201
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
