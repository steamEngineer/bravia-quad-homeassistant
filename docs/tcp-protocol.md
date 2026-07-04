# TCP protocol reference

The integration's **TCP transport** communicates with the Bravia Theatre device on port **33336** using JSON messages.

> **gRPC transport users:** see [sony-grpc-reference.md](sony-grpc-reference.md) instead. TCP details below apply only to legacy IP control mode.

## Command format

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

## Notifications

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

## Supported commands

### Power control

- **Get Power State**: `{"id": 3, "type": "get", "feature": "main.power"}`
- **Set Power On**: `{"id": 3, "type": "set", "feature": "main.power", "value": "on"}`
- **Set Power Off**: `{"id": 3, "type": "set", "feature": "main.power", "value": "off"}`

### Volume control

- **Get Volume**: `{"id": 2, "type": "get", "feature": "main.volumestep"}`
- **Set Volume**: `{"id": 2, "type": "set", "feature": "main.volumestep", "value": 50}` (0-100)

### Rear level control

- **Get Rear Level**: `{"id": 2, "type": "get", "feature": "main.rearvolumestep"}`
- **Set Rear Level**: `{"id": 2, "type": "set", "feature": "main.rearvolumestep", "value": 5}` (-10 to 10)

### Source selection

- **Get Source**: `{"id": 2, "type": "get", "feature": "main.input"}`
- **Set Source**: `{"id": 2, "type": "set", "feature": "main.input", "value": "tv"}`

**Available sources:**

- `tv` - TV (eARC)
- `hdmi1` - HDMI In
- `spotify` - Spotify
- `bluetooth` - Bluetooth
- `airplay2` - AirPlay (gRPC reports `airplay`; detected when active; cannot be set via command — only activated when an AirPlay client casts to the Bravia)

### Bass level control

The bass level range depends on whether a subwoofer is connected:

**With subwoofer:**

- **Get Bass Level**: `{"id": 2, "type": "get", "feature": "main.bassstep"}`
- **Set Bass Level**: `{"id": 2, "type": "set", "feature": "main.bassstep", "value": 5}` (-10 to 10)

**Without subwoofer:**

- **Get Bass Level**: `{"id": 2, "type": "get", "feature": "main.bassstep"}`
- **Set Bass Level**: `{"id": 2, "type": "set", "feature": "main.bassstep", "value": 1}` (0=MIN, 1=MID, 2=MAX)

### Voice enhancer

- **Get Voice Enhancer**: `{"id": 1, "type": "get", "feature": "audio.voiceenhancer"}`
- **Set Voice Enhancer On**: `{"id": 1, "type": "set", "feature": "audio.voiceenhancer", "value": "upon"}`
- **Set Voice Enhancer Off**: `{"id": 1, "type": "set", "feature": "audio.voiceenhancer", "value": "upoff"}`

### Sound field

- **Get Sound Field**: `{"id": 1, "type": "get", "feature": "audio.soundfield"}`
- **Set Sound Field On**: `{"id": 1, "type": "set", "feature": "audio.soundfield", "value": "on"}`
- **Set Sound Field Off**: `{"id": 1, "type": "set", "feature": "audio.soundfield", "value": "off"}`

### Night mode

- **Get Night Mode**: `{"id": 1, "type": "get", "feature": "audio.nightmode"}`
- **Set Night Mode On**: `{"id": 1, "type": "set", "feature": "audio.nightmode", "value": "on"}`
- **Set Night Mode Off**: `{"id": 1, "type": "set", "feature": "audio.nightmode", "value": "off"}`

### HDMI CEC

- **Get HDMI CEC**: `{"id": 1, "type": "get", "feature": "hdmi.cec"}`
- **Set HDMI CEC On**: `{"id": 1, "type": "set", "feature": "hdmi.cec", "value": "on"}`
- **Set HDMI CEC Off**: `{"id": 1, "type": "set", "feature": "hdmi.cec", "value": "off"}`

### Auto standby

- **Get Auto Standby**: `{"id": 1, "type": "get", "feature": "system.autostandby"}`
- **Set Auto Standby On**: `{"id": 1, "type": "set", "feature": "system.autostandby", "value": "on"}`
- **Set Auto Standby Off**: `{"id": 1, "type": "set", "feature": "system.autostandby", "value": "off"}`

### Dynamic Range Compressor (DRC)

- **Get DRC**: `{"id": 1, "type": "get", "feature": "audio.drangecomp"}`
- **Set DRC Auto**: `{"id": 1, "type": "set", "feature": "audio.drangecomp", "value": "auto"}`
- **Set DRC On**: `{"id": 1, "type": "set", "feature": "audio.drangecomp", "value": "on"}`
- **Set DRC Off**: `{"id": 1, "type": "set", "feature": "audio.drangecomp", "value": "off"}`

**Note**: The DRC entity uses polling to update its state, as the device does not send notifications for this feature.

### Auto Volume (AAV)

- **Get AAV**: `{"id": 1, "type": "get", "feature": "audio.aav"}`
- **Set AAV On**: `{"id": 1, "type": "set", "feature": "audio.aav", "value": "on"}`
- **Set AAV Off**: `{"id": 1, "type": "set", "feature": "audio.aav", "value": "off"}`

**Note**: The Auto Volume entity uses polling to update its state, as the device does not send notifications for this feature.

_Per [Sony docs](https://helpguide.sony.net/ht/a7000/v1/en/contents/TP1000070959.html) on the feature, Auto Volume should be **disabled** when listening to music._

## Manual connection test

Test the TCP connection manually:

```bash
netcat <IP_ADDRESS> 33336
{"id":3, "type":"get","feature":"main.power"}
```

You should receive a JSON response with the power state.

Or using Python:

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
