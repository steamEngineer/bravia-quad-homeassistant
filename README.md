**USE AT YOUR OWN RISK. The hard work was reverse-engineering the sony bravia quad commands. Everything you see here was vibe-coded in cursor so I could make it work with home assistant.**

# Bravia Quad Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Home Assistant custom integration for controlling Sony Bravia Quad home theater systems via TCP/IP.

## Features

- **Power Control**: Turn your Bravia Quad system on and off
- **Volume Control**: Adjust volume from 0-100 via a number entity
- **Source Selection**: Switch between inputs (TV/eARC, HDMI In, Spotify)
- **Real-time Updates**: Automatically receives and processes notifications from the device for power, volume, and source changes
- **Device Integration**: All entities are properly nested under a single device in Home Assistant

## Installation

### HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed
2. Go to HACS → Integrations
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Search for "Bravia Quad" in HACS and install it
7. Restart Home Assistant

### Manual Installation

1. Copy the `bravia_quad` folder to your Home Assistant `custom_components` directory:
   ```
   <config>/custom_components/bravia_quad/
   ```

2. Restart Home Assistant

3. Go to **Settings** → **Devices & Services** → **Add Integration**

4. Search for "Bravia Quad" and follow the setup wizard

## Configuration

During setup, you will be prompted to provide:

- **IP Address**: The IP address of your Bravia Quad device
- **Name** (optional): A friendly name for the device (defaults to "Bravia Quad")

The integration will automatically test the connection by sending a power status request. Make sure:

- IP control is enabled on your Bravia Quad device
- The device is accessible on your network
- Port 33336 is not blocked by a firewall

## Entities

The integration creates the following entities under your Bravia Quad device:

| Entity | Type | Description |
|--------|------|-------------|
| `switch.bravia_quad_*_power` | Switch | Control power on/off |
| `number.bravia_quad_*_volume` | Number | Control volume (0-100) |
| `select.bravia_quad_*_source` | Select | Select input source (TV/eARC, HDMI In, Spotify) |

*Note: `*` represents your device's unique entry ID*

## Protocol Details

The integration communicates with the Bravia Quad device via TCP on port **33336** using JSON messages:

### Command Format

**Get Request:**
```json
{"id": 3, "type": "get", "feature": "main.power"}
```

**Get Response:**
```json
{"feature": "main.power", "id": 3, "type": "result", "value": "off"}
```

**Set Request:**
```json
{"id": 3, "type": "set", "feature": "main.power", "value": "on"}
```

**Set Response:**
```json
{"id": 3, "type": "result", "value": "ACK"}
```

### Notifications

When maintaining an open connection, the device sends real-time notifications:

```json
{"feature": "main.power", "type": "notify", "value": "on"}
{"feature": "main.volumestep", "type": "notify", "value": "21"}
{"feature": "main.input", "type": "notify", "value": "spotify"}
```

## Supported Commands

### Power Control

- **Get Power State**: `{"id": 3, "type": "get", "feature": "main.power"}`
- **Set Power On**: `{"id": 3, "type": "set", "feature": "main.power", "value": "on"}`
- **Set Power Off**: `{"id": 3, "type": "set", "feature": "main.power", "value": "off"}`

### Volume Control

- **Get Volume**: `{"id": 2, "type": "get", "feature": "main.volumestep"}`
- **Set Volume**: `{"id": 2, "type": "set", "feature": "main.volumestep", "value": 50}` (0-100)

### Source Selection

- **Get Source**: `{"id": 2, "type": "get", "feature": "main.input"}`
- **Set Source**: `{"id": 2, "type": "set", "feature": "main.input", "value": "tv"}`

**Available Sources:**
- `tv` - TV (eARC)
- `hdmi1` - HDMI In
- `spotify` - Spotify

## Troubleshooting

### Connection Issues

If you encounter connection problems:

1. **Verify IP Address**: Ensure the IP address is correct and the device is on the same network
2. **Check IP Control**: Verify that IP control is enabled on your Bravia Quad device
3. **Firewall**: Ensure port 33336 is not blocked by your firewall
4. **Test Connection**: Test the connection manually using netcat:
   ```bash
   netcat <IP_ADDRESS> 33336
   {"id":3, "type":"get","feature":"main.power"}
   ```
   You should receive a JSON response with the power state.

### Entity States Not Updating

- Check the Home Assistant logs for any error messages
- Ensure the notification listener is running (check logs for "Starting notification listener")
- Try reloading the integration: **Settings** → **Devices & Services** → **Bravia Quad** → **Reload**

### Volume or Source Shows Default Values

- The integration polls for initial values on startup
- If values don't update, check that the device is responding to get commands
- Notifications will update values in real-time when changes occur

## Development

### Using the DevContainer

The easiest way to develop and test this integration is using the included DevContainer configuration with Visual Studio Code.

1. Make sure you have [Visual Studio Code](https://code.visualstudio.com/) and the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) installed.
2. Clone this repository.
3. Open the repository in VS Code and click "Reopen in Container" when prompted (or use the command palette: `Dev Containers: Reopen in Container`).
4. Once the container is ready, run `scripts/develop` to start Home Assistant with the integration loaded.
5. Access Home Assistant at [http://localhost:8123](http://localhost:8123).

### Available Scripts

| Script | Description |
|--------|-------------|
| `scripts/setup` | Installs Python dependencies from `requirements.txt` |
| `scripts/develop` | Starts Home Assistant with the integration in debug mode |
| `scripts/lint` | Runs Ruff to format and lint the code |

### Project Structure

```
custom_components/bravia_quad/
├── __init__.py              # Integration setup
├── manifest.json            # Integration metadata
├── config_flow.py           # Configuration flow
├── bravia_quad_client.py    # TCP client for device communication
├── switch.py                # Power switch entity
├── number.py                # Volume number entity
├── select.py                # Source select entity
├── const.py                 # Constants
└── strings.json             # UI strings
```

### Testing

To test the connection manually:

```python
import socket
import json

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('YOUR_IP', 33336))
s.send(b'{"id":3, "type":"get","feature":"main.power"}\n')
response = s.recv(1024).decode()
print(json.loads(response))
s.close()
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This integration is provided as-is under the MIT License.

## Disclaimer

This integration is not officially supported by Sony. Use at your own risk.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

---

**Made with ❤️ for the Home Assistant community**
