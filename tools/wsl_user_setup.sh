#!/bin/bash
# Install pebble-tool and the latest Pebble SDK for the current WSL user.
# Run from Windows: wsl -d Ubuntu-24.04 -- bash /mnt/e/snowscout/tools/wsl_user_setup.sh
#
# This distro runs on WSL1 (no CPU virtualization), where `uv tool install` fails with
# "Cannot allocate memory" on its file copies. uv is used only to fetch Python 3.13;
# pipx does the install.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
# the SDK installer runs `uv pip` itself; linking from the cache avoids most WSL1 copy failures
export UV_LINK_MODE=symlink
grep -q UV_LINK_MODE ~/.profile || echo 'export UV_LINK_MODE=symlink' >> ~/.profile
# run tools/wsl_node_setup.sh first: Ubuntu's own node does not start on WSL1

command -v uv >/dev/null || pipx install uv
pipx ensurepath >/dev/null 2>&1 || true
rm -rf "$HOME/.local/share/uv/tools/pebble-tool"      # leftovers of a failed uv install
uv python install 3.13
pipx install --force pebble-tool --python "$(uv python find 3.13)"
pebble --version
pebble sdk install latest < /dev/null
pebble sdk list
