# Bravia Quad Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Home Assistant custom integration for controlling Sony Bravia Quad home theater systems via TCP/IP.

## Features

- **Power Control**: Turn your Bravia Quad system on and off
- **Volume Control**: Adjust main volume from 0-100 via a number entity
- **Rear Level Control**: Adjust rear speaker level from -10-10 via a number entity
- **Source Selection**: Switch between inputs (TV/eARC, HDMI In, Spotify)
- **Bass Level Control**: Automatically adapts based on subwoofer presence:
  - With subwoofer: Slider from -10 to +10
  - Without subwoofer: Select between MIN, MID, MAX
- **Subwoofer Auto-Detection**: Automatically detects if a subwoofer is connected and adjusts bass level controls accordingly
- **Voice Enhancer**: Toggle voice enhancer on/off
- **Sound Field**: Toggle sound field processing on/off
- **Night Mode**: Toggle night mode on/off
- **HDMI CEC**: Toggle HDMI CEC on/off
- **Auto Standby**: Toggle automatic standby behavior on/off
- **Real-time Updates**: Automatically receives and processes notifications from the device for all state changes
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

| Entity | Type | Description | Range/Options |
|--------|------|-------------|---------------|
| `switch.bravia_quad_*_power` | Switch | Control power on/off | on/off |
| `number.bravia_quad_*_volume` | Number | Control main volume | 0-100 |
| `number.bravia_quad_*_rear_level` | Number | Control rear speaker level | -10-10 |
| `number.bravia_quad_*_bass_level` | Number | Control bass level (with subwoofer) | -10-10 |
| `select.bravia_quad_*_bass_level` | Select | Control bass level (without subwoofer) | MIN, MID, MAX |
| `select.bravia_quad_*_source` | Select | Select input source | TV (eARC), HDMI In, Spotify |
| `switch.bravia_quad_*_voice_enhancer` | Switch | Toggle voice enhancer | on/off |
| `switch.bravia_quad_*_sound_field` | Switch | Toggle sound field processing | on/off |
| `switch.bravia_quad_*_night_mode` | Switch | Toggle night mode | on/off |
| `switch.bravia_quad_*_hdmi_cec` | Switch | Toggle HDMI CEC | on/off |
| `switch.bravia_quad_*_auto_standby` | Switch | Toggle auto standby | on/off |
| `button.bravia_quad_*_detect_subwoofer` | Button | Re-detect subwoofer (diagnostic) | - |

*Note: `*` represents your device's unique entry ID*

*Note: Only one bass level entity will be created based on whether a subwoofer is detected.*

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

When maintaining an open connection, the device sends real-time notifications for all state changes:

```json
{"feature": "main.power", "type": "notify", "value": "on"}
{"feature": "main.volumestep", "type": "notify", "value": "21"}
{"feature": "main.input", "type": "notify", "value": "spotify"}
{"feature": "main.rearvolumestep", "type": "notify", "value": "5"}
{"feature": "main.bassstep", "type": "notify", "value": "1"}
{"feature": "audio.voiceenhancer", "type": "notify", "value": "upon"}
{"feature": "audio.soundfield", "type": "notify", "value": "on"}
{"feature": "audio.nightmode", "type": "notify", "value": "off"}
{"feature": "hdmi.cec", "type": "notify", "value": "on"}
{"feature": "system.autostandby", "type": "notify", "value": "off"}
```

## Supported Commands

### Power Control

- **Get Power State**: `{"id": 3, "type": "get", "feature": "main.power"}`
- **Set Power On**: `{"id": 3, "type": "set", "feature": "main.power", "value": "on"}`
- **Set Power Off**: `{"id": 3, "type": "set", "feature": "main.power", "value": "off"}`

### Volume Control

- **Get Volume**: `{"id": 2, "type": "get", "feature": "main.volumestep"}`
- **Set Volume**: `{"id": 2, "type": "set", "feature": "main.volumestep", "value": 50}` (0-100)

### Rear Level Control

- **Get Rear Level**: `{"id": 2, "type": "get", "feature": "main.rearvolumestep"}`
- **Set Rear Level**: `{"id": 2, "type": "set", "feature": "main.rearvolumestep", "value": 5}` (-10 to 10)

### Source Selection

- **Get Source**: `{"id": 2, "type": "get", "feature": "main.input"}`
- **Set Source**: `{"id": 2, "type": "set", "feature": "main.input", "value": "tv"}`

**Available Sources:**
- `tv` - TV (eARC)
- `hdmi1` - HDMI In
- `spotify` - Spotify

### Bass Level Control

The bass level range depends on whether a subwoofer is connected:

**With Subwoofer:**
- **Get Bass Level**: `{"id": 2, "type": "get", "feature": "main.bassstep"}`
- **Set Bass Level**: `{"id": 2, "type": "set", "feature": "main.bassstep", "value": 5}` (-10 to 10)

**Without Subwoofer:**
- **Get Bass Level**: `{"id": 2, "type": "get", "feature": "main.bassstep"}`
- **Set Bass Level**: `{"id": 2, "type": "set", "feature": "main.bassstep", "value": 1}` (0=MIN, 1=MID, 2=MAX)

### Voice Enhancer

- **Get Voice Enhancer**: `{"id": 1, "type": "get", "feature": "audio.voiceenhancer"}`
- **Set Voice Enhancer On**: `{"id": 1, "type": "set", "feature": "audio.voiceenhancer", "value": "upon"}`
- **Set Voice Enhancer Off**: `{"id": 1, "type": "set", "feature": "audio.voiceenhancer", "value": "upoff"}`

### Sound Field

- **Get Sound Field**: `{"id": 1, "type": "get", "feature": "audio.soundfield"}`
- **Set Sound Field On**: `{"id": 1, "type": "set", "feature": "audio.soundfield", "value": "on"}`
- **Set Sound Field Off**: `{"id": 1, "type": "set", "feature": "audio.soundfield", "value": "off"}`

### Night Mode

- **Get Night Mode**: `{"id": 1, "type": "get", "feature": "audio.nightmode"}`
- **Set Night Mode On**: `{"id": 1, "type": "set", "feature": "audio.nightmode", "value": "on"}`
- **Set Night Mode Off**: `{"id": 1, "type": "set", "feature": "audio.nightmode", "value": "off"}`

### HDMI CEC

- **Get HDMI CEC**: `{"id": 1, "type": "get", "feature": "hdmi.cec"}`
- **Set HDMI CEC On**: `{"id": 1, "type": "set", "feature": "hdmi.cec", "value": "on"}`
- **Set HDMI CEC Off**: `{"id": 1, "type": "set", "feature": "hdmi.cec", "value": "off"}`

### Auto Standby

- **Get Auto Standby**: `{"id": 1, "type": "get", "feature": "system.autostandby"}`
- **Set Auto Standby On**: `{"id": 1, "type": "set", "feature": "system.autostandby", "value": "on"}`
- **Set Auto Standby Off**: `{"id": 1, "type": "set", "feature": "system.autostandby", "value": "off"}`

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
├── __version__.py           # Version information
├── manifest.json            # Integration metadata
├── config_flow.py           # Configuration flow
├── bravia_quad_client.py    # TCP client for device communication
├── switch.py                # Power switch entity
├── number.py                # Volume number entity
├── select.py                # Source select entity
├── const.py                 # Constants
└── strings.json             # UI strings
```

### Code Quality

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and code formatting. The configuration follows Home Assistant's coding standards:

- **Linting**: Automated linting runs on all pull requests via GitHub Actions
- **Formatting**: Code is automatically formatted using Ruff
- **Python Version**: Targets Python 3.13

Run linting locally:
```bash
scripts/lint
```

### CI/CD

This project uses GitHub Actions for continuous integration and deployment:

- **Hassfest**: Validates the integration manifest and ensures compliance with Home Assistant standards
- **Lint**: Runs Ruff to check code quality and formatting on all pull requests
- **Release**: Automated release workflow that:
  - Validates version format
  - Updates version in `manifest.json` and `__version__.py`
  - Creates Git tags
  - Generates GitHub releases

Dependencies are automatically kept up to date via [Dependabot](https://github.com/dependabot) for:
- GitHub Actions
- Python packages (pip)
- DevContainer configuration

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

### Development Guidelines

1. **Code Style**: Follow the existing code style and use Ruff for formatting
2. **Testing**: Test your changes thoroughly before submitting
3. **Pull Requests**:
   - Ensure all CI checks pass (Hassfest, Lint)
   - Update documentation if needed
   - Follow conventional commit messages when possible
4. **Issues**: If you find a bug or have a feature request, please open an issue first to discuss

## License

This integration is provided as-is under the MIT License.

## Disclaimer

This integration is not officially supported by Sony. Use at your own risk.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

---

**Made with ❤️ for the Home Assistant community**
