"""Test script to verify Bravia Quad connection."""

import json
import socket


def test_connection():
    """Test connection to Bravia Quad."""
    host = "10.0.110.130"
    port = 33336

    try:
        # Create socket and connect
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        print(f"Connecting to {host}:{port}...")
        s.connect((host, port))
        print("Connected successfully!")

        # Send test command
        command = {"id": 3, "type": "get", "feature": "main.power"}
        command_json = json.dumps(command) + "\n"
        print(f"Sending: {command_json.strip()}")
        s.send(command_json.encode())

        # Receive response
        response = s.recv(1024).decode()
        print(f"Response: {response.strip()}")

        # Parse response
        try:
            response_data = json.loads(response.strip())
            print(f"Parsed response: {json.dumps(response_data, indent=2)}")

            if (
                response_data.get("type") == "result"
                and response_data.get("feature") == "main.power"
            ):
                print("Connection test successful!")
                return True
            print("Unexpected response format")
            return False
        except json.JSONDecodeError as e:
            print(f"Failed to parse response: {e}")
            return False

    except TimeoutError:
        print("Connection timeout")
        return False
    except ConnectionRefusedError:
        print("Connection refused - check if IP control is enabled")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        s.close()
        print("Connection closed")


if __name__ == "__main__":
    test_connection()
