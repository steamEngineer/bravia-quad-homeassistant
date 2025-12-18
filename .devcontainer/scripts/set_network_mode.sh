#!/usr/bin/env bash

set -e

DEVCONTAINER_JSON=".devcontainer/devcontainer.json"
MODE="${1:-bridge}"

if [[ ! -f "$DEVCONTAINER_JSON" ]]; then
    echo "Error: devcontainer.json not found at $DEVCONTAINER_JSON"
    exit 1
fi

if [[ "$MODE" != "host" ]] && [[ "$MODE" != "bridge" ]]; then
    echo "Error: Mode must be 'host' or 'bridge'"
    exit 1
fi

# Use Python to modify JSON safely
python3 << EOF
import json
import sys

json_file = "${DEVCONTAINER_JSON}"
mode = "${MODE}"

try:
    with open(json_file, 'r') as f:
        config = json.load(f)

    if mode == "host":
        config["runArgs"] = ["--network=host"]
        print("✓ Updated devcontainer.json to use host networking")
    else:  # bridge
        config["runArgs"] = ["--network=bridge"]
        print("✓ Updated devcontainer.json to use bridge networking")

    with open(json_file, 'w') as f:
        json.dump(config, f, indent=2)
        f.write('\n')

    print("")
    print("⚠️  You need to rebuild the devcontainer for changes to take effect:")
    print("   1. Open Command Palette (Ctrl+Shift+P / Cmd+Shift+P)")
    print("   2. Run: Dev Containers: Rebuild Container")
    print("Once built, you can verify the IP address inside the container matches the host IP address.")
    print("Run: ip a")

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
EOF
