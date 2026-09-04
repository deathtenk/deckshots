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

[[ "$(basename -- "$PLUGIN_DIR")" == "$PLUGIN_NAME" ]] || \
  die "DECKY_PLUGIN_DIR must point to a directory named $PLUGIN_NAME."

command -v node >/dev/null 2>&1 || die "Node.js 16.14 or newer is required to build Deckshots."

if command -v pnpm >/dev/null 2>&1; then
  PNPM=(pnpm)
elif command -v corepack >/dev/null 2>&1; then
  printf 'pnpm is not installed; using Corepack.\n'
  PNPM=(corepack pnpm)
elif command -v npx >/dev/null 2>&1; then
  printf 'pnpm is not installed; using a temporary copy through npx.\n'
  PNPM=(npx --yes pnpm@9)
else
  die "pnpm is unavailable and neither Corepack nor npx can provide it."
fi

printf 'Building Deckshots...\n'
cd "$SCRIPT_DIR"
"${PNPM[@]}" install --frozen-lockfile
"${PNPM[@]}" run typecheck
"${PNPM[@]}" run build

[[ -f dist/index.js ]] || die "build completed without creating dist/index.js"

STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/deckshots-install.XXXXXX")"
trap 'rm -rf -- "$STAGING_DIR"' EXIT

mkdir -p "$STAGING_DIR/dist"
cp -- dist/index.js "$STAGING_DIR/dist/index.js"
cp -- main.py plugin.json package.json README.md LICENSE "$STAGING_DIR/"

PLUGIN_PARENT="$(dirname -- "$PLUGIN_DIR")"
SUDO=()
if [[ ! -d "$PLUGIN_PARENT" || ! -w "$PLUGIN_PARENT" ]]; then
  command -v sudo >/dev/null 2>&1 || die "installing to $PLUGIN_PARENT requires root access, but sudo is unavailable."
  printf 'Root access is required to install into %s.\n' "$PLUGIN_PARENT"
  sudo -v
  SUDO=(sudo)
fi

printf 'Installing Deckshots to %s...\n' "$PLUGIN_DIR"
"${SUDO[@]}" mkdir -p "$PLUGIN_PARENT"
"${SUDO[@]}" rm -rf -- "$PLUGIN_DIR"
"${SUDO[@]}" mv -- "$STAGING_DIR" "$PLUGIN_DIR"
trap - EXIT

# Decky normally runs as the deck user. Keep the plugin readable by its loader.
"${SUDO[@]}" chmod -R u+rwX,go+rX "$PLUGIN_DIR"

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files plugin_loader.service >/dev/null 2>&1; then
  printf 'Restarting Decky Loader...\n'
  if ((${#SUDO[@]})); then
    sudo systemctl restart plugin_loader.service
  elif systemctl restart plugin_loader.service 2>/dev/null; then
    :
  elif command -v sudo >/dev/null 2>&1; then
    sudo systemctl restart plugin_loader.service
  else
    printf 'Could not restart Decky Loader without root access. Restart it or reboot the Steam Deck.\n'
  fi
else
  printf 'Decky Loader was not restarted automatically. Restart it or reboot the Steam Deck.\n'
fi

printf 'Deckshots installed successfully.\n'
