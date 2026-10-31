#!/bin/bash
# Let pebble-tool's --adb option use the Windows adb.exe from inside WSL1.
set -euo pipefail
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/adb" <<'EOF'
#!/bin/sh
exec /mnt/d/AndroidSDK/platform-tools/adb.exe "$@"
EOF
chmod +x "$HOME/.local/bin/adb"
. "$HOME/.profile"
command -v adb
adb version | head -1
