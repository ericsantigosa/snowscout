#!/bin/bash
# Install the official Node.js 22 LTS into ~/.local/node.
# Ubuntu's /usr/bin/node has a LOAD segment aligned to 0x2000, which the WSL1 loader
# rejects ("Exec format error"); the official build runs. ~/.profile puts it first on PATH.
set -euo pipefail

base=https://nodejs.org/dist/latest-v22.x
work=$(mktemp -d)
cd "$work"
curl -fsSLO "$base/SHASUMS256.txt"
tarball=$(grep -oE 'node-v22\.[0-9.]+-linux-x64\.tar\.xz' SHASUMS256.txt | head -1)
curl -fsSLO "$base/$tarball"
grep " $tarball\$" SHASUMS256.txt | sha256sum -c -

rm -rf "$HOME/.local/node"
mkdir -p "$HOME/.local/node"
tar -xJf "$tarball" -C "$HOME/.local/node" --strip-components=1
cd / && rm -rf "$work"

echo "--- alignment of the new binary:"
readelf -lW "$HOME/.local/node/bin/node" | grep LOAD
grep -q '.local/node/bin' ~/.profile || echo 'export PATH="$HOME/.local/node/bin:$PATH"' >> ~/.profile
export PATH="$HOME/.local/node/bin:$PATH"
echo "node $(node --version), npm $(npm --version), from $(command -v node)"
