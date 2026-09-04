# Deckshots

Deckshots is a small [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that automatically takes screenshots while a game is running.

## What it does

- Enables or disables automatic captures from Decky's Quick Access menu.
- Accepts an interval in milliseconds (minimum: 1000 ms).
- Provides a **Capture now** button for one-off screenshots.
- Requests screenshots from Gamescope's native control interface in SteamOS Gaming Mode.
- Saves each captured image into a configurable folder (default: `~/Pictures/Deckshots`).
- Continues automatic capture while the Decky panel is closed.
- Persists all settings across Decky and Steam restarts.

Deckshots invokes SteamOS's `gamescopectl screenshot` command against Gamescope's user-owned Wayland control socket. This asks Gamescope to write the image directly to the configured Deckshots folder, avoiding simulated input entirely. Captures use timestamped PNG names such as `deckshot_2026-09-04_18-59-04.png`. Because Gamescope writes screenshots asynchronously, Deckshots waits up to five seconds for each requested file to appear. A game must be running under Gamescope.

## Permissions

Deckshots runs as the normal Decky user. It does not access `/dev/uinput`, install a system service, or modify the read-only SteamOS system partition.

## Build

Node.js 16.14+ and pnpm 9 are required.

```sh
pnpm install
pnpm run typecheck
pnpm run build
```

The installable plugin files are `dist/index.js`, `main.py`, `plugin.json`, `package.json`, `README.md`, and `LICENSE`.

## Development install

Copy the project into Decky's plugins directory as `deckshots`, build it, and restart Decky Loader. The official Decky template's VS Code deploy task can also be adapted by setting its plugin name to `deckshots`.

## Notes

Very short intervals can generate substantial disk usage. Deckshots enforces a one-second minimum and never deletes screenshots automatically.
