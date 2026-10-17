#!/usr/bin/env bash
# Install the pinned toolchain into ~/.hourproof/bin (no sudo). Linux x86-64/arm64 and macOS.
# Windows: use WSL2 (Ubuntu) and run this script inside it.
# Pins are the exact versions the kill tests passed with (K2/K3/K4, Oct 2026).
set -euo pipefail

FOUNDRY=v1.8.5
NARGO=v1.0.0-beta.22
BB=v5.0.0-nightly.20260522   # the bb that bbup maps to nargo 1.0.0-beta.22
DEST="${HOURPROOF_BIN:-$HOME/.hourproof/bin}"
mkdir -p "$DEST"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

os="$(uname -s)"; arch="$(uname -m)"
case "$os-$arch" in
  Linux-x86_64)  F=linux_amd64;  N=x86_64-unknown-linux-gnu;  B=amd64-linux ;;
  Linux-aarch64) F=linux_arm64;  N=aarch64-unknown-linux-gnu; B=arm64-linux ;;
  Darwin-arm64)  F=darwin_arm64; N=aarch64-apple-darwin;      B=arm64-darwin ;;
  Darwin-x86_64) F=darwin_amd64; N=x86_64-apple-darwin;       B=amd64-darwin ;;
  *) echo "Unsupported platform $os-$arch (on Windows use WSL2)"; exit 1 ;;
esac

fetch() { echo "  downloading $1"; curl -fsSL --retry 3 -o "$2" "$1"; }

if [ ! -x "$DEST/forge" ]; then
  fetch "https://github.com/foundry-rs/foundry/releases/download/$FOUNDRY/foundry_${FOUNDRY}_${F}.tar.gz" "$TMP/f.tgz"
  tar -xzf "$TMP/f.tgz" -C "$DEST" forge cast anvil
fi
if [ ! -x "$DEST/nargo" ]; then
  fetch "https://github.com/noir-lang/noir/releases/download/$NARGO/nargo-$N.tar.gz" "$TMP/n.tgz"
  tar -xzf "$TMP/n.tgz" -C "$DEST"
fi
if [ ! -x "$DEST/bb" ]; then
  fetch "https://github.com/AztecProtocol/barretenberg/releases/download/$BB/barretenberg-$B.tar.gz" "$TMP/b.tgz" \
    || fetch "https://github.com/AztecProtocol/aztec-packages/releases/download/$BB/barretenberg-$B.tar.gz" "$TMP/b.tgz"
  tar -xzf "$TMP/b.tgz" -C "$DEST"
fi
chmod +x "$DEST"/*

echo
for t in forge cast anvil nargo bb; do printf "  %-6s %s\n" "$t" "$("$DEST/$t" --version 2>/dev/null | head -1)"; done
echo
echo "Add to your shell profile (the Makefile does this for you):"
echo "  export PATH=\"$DEST:\$PATH\""
