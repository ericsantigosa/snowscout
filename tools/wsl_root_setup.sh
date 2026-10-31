#!/bin/bash
# One-time root setup of the WSL Ubuntu used for the Pebble SDK.
# Run from Windows: wsl -d Ubuntu-24.04 -u root -- bash /mnt/e/snowscout/tools/wsl_root_setup.sh
set -euo pipefail

USER_NAME=eric
if ! id "$USER_NAME" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$USER_NAME"   # no password: root stays reachable via `wsl -u root`
fi
printf '[user]\ndefault=%s\n' "$USER_NAME" > /etc/wsl.conf

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
# SDK dependencies from the Rebble/Core install docs, plus pipx (to install uv) and git
apt-get install -y -q python3-pip python3-venv pipx nodejs npm libsdl1.2debian libfdt1 git curl
echo "root setup done"
