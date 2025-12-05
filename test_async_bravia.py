"""Test async connection to Bravia Quad (mimics Home Assistant behavior)."""

import asyncio
import json
import logging

logging.basicConfig(level=logging.DEBUG)


async def test_async_connection():
    """Test async connection similar to Home Assistant."""
    host = "10.0.110.130"
    port = 33336

    try:
        print(f"Connecting to {host}:{port}...")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=10.0
        )
        print("Connected successfully!")

        # Give connection a moment to stabilize
        await asyncio.sleep(0.2)

        # Send test command
        command = {"id": 3, "type": "get", "feature": "main.power"}
        command_json = json.dumps(command) + "\n"
        print(f"Sending: {command_json.strip()}")

        writer.write(command_json.encode())
        await writer.drain()
        print("Command sent, waiting for response...")

        # Wait for response - device sends JSON without newline
        try:
            data = await asyncio.wait_for(reader.read(1024), timeout=10.0)

            if data:
                response_str = data.decode("utf-8", errors="replace").strip()
                print(f"Response: {response_str}")

                try:
                    response_data = json.loads(response_str)
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
            else:
                print("Received empty response")
                return False
        except TimeoutError:
            print("Timeout waiting for response")
            return False

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if "writer" in locals():
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        print("Connection closed")


if __name__ == "__main__":
    result = asyncio.run(test_async_connection())
    print(f"\nTest result: {'PASSED' if result else 'FAILED'}")
