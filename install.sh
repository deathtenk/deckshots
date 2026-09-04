#!/usr/bin/env bash

set -Eeuo pipefail

PLUGIN_NAME="deckshots"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DECKY_HOME="${DECKY_HOME:-${HOME}/homebrew}"
PLUGIN_DIR="${DECKY_PLUGIN_DIR:-${DECKY_HOME}/plugins/${PLUGIN_NAME}}"

die() {
  printf 'Deckshots installer: %s\n' "$*" >&2
  exit 1
}

command -v pnpm >/dev/null 2>&1 || die "pnpm is required (version 9 or newer)."

printf 'Building Deckshots...\n'
cd "$SCRIPT_DIR"
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run build

[[ -f dist/index.js ]] || die "build completed without creating dist/index.js"

STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/deckshots-install.XXXXXX")"
trap 'rm -rf -- "$STAGING_DIR"' EXIT

mkdir -p "$STAGING_DIR/dist"
cp -- dist/index.js "$STAGING_DIR/dist/index.js"
cp -- main.py plugin.json package.json README.md LICENSE "$STAGING_DIR/"

printf 'Installing Deckshots to %s...\n' "$PLUGIN_DIR"
mkdir -p "$(dirname -- "$PLUGIN_DIR")"
rm -rf -- "$PLUGIN_DIR"
mv -- "$STAGING_DIR" "$PLUGIN_DIR"
trap - EXIT

# Decky normally runs as the deck user. Keep the plugin readable by its loader.
chmod -R u+rwX,go+rX "$PLUGIN_DIR"

if command -v systemctl >/dev/null 2>&1 && systemctl --user list-unit-files plugin_loader.service >/dev/null 2>&1; then
  printf 'Restarting Decky Loader...\n'
  systemctl --user restart plugin_loader.service
else
  printf 'Decky Loader was not restarted automatically. Restart it or reboot the Steam Deck.\n'
fi

printf 'Deckshots installed successfully.\n'
