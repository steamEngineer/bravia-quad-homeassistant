"""
Manual script to verify Bravia Quad connection (sync version).

This script tests connectivity to a real Bravia Quad device using synchronous sockets.
Useful for debugging connection issues.

Usage:
    python scripts/check_connection.py <host>
    python scripts/check_connection.py 192.168.1.100
"""

import json
import socket
import sys

DEFAULT_PORT = 33336


def check_connection(host: str, port: int = DEFAULT_PORT) -> bool:
    """
    Check connection to Bravia Quad.

    Args:
        host: IP address or hostname of the Bravia Quad device.
        port: Port number (default: 33336).

    Returns:
        True if connection test passed, False otherwise.

    """
    sock = None
    try:
        # Create socket and connect
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        print(f"Connecting to {host}:{port}...")
        sock.connect((host, port))
        print("Connected successfully!")

        # Send test command
        command = {"id": 3, "type": "get", "feature": "main.power"}
        command_json = json.dumps(command) + "\n"
        print(f"Sending: {command_json.strip()}")
        sock.send(command_json.encode())

        # Receive response
        response = sock.recv(1024).decode()
        print(f"Response: {response.strip()}")

        # Parse response
        try:
            response_data = json.loads(response.strip())
        except json.JSONDecodeError as e:
            print(f"Failed to parse response: {e}")
            return False

        print(f"Parsed response: {json.dumps(response_data, indent=2)}")

        if (
            response_data.get("type") == "result"
            and response_data.get("feature") == "main.power"
        ):
            print("Connection test successful!")
            return True

        print("Unexpected response format")

    except TimeoutError:
        print("Connection timeout")
    except ConnectionRefusedError:
        print("Connection refused - check if IP control is enabled")
    except OSError as e:
        print(f"Error: {e}")
    finally:
        if sock:
            sock.close()
            print("Connection closed")
    return False


def main() -> None:
    """Run the connection check."""
    if len(sys.argv) < 2:  # noqa: PLR2004
        print(f"Usage: {sys.argv[0]} <host> [port]")
        print(f"Example: {sys.argv[0]} 192.168.1.100")
        sys.exit(1)

    host = sys.argv[1]
    try:
        port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT  # noqa: PLR2004
    except ValueError:
        print(f"Error: Invalid port number '{sys.argv[2]}'")
        print(f"Usage: {sys.argv[0]} <host> [port]")
        sys.exit(1)

    result = check_connection(host, port)
    print(f"\nResult: {'PASSED' if result else 'FAILED'}")
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
