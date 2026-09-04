# Deckshots

Deckshots is a small [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that automatically takes Steam screenshots while a game is running.

## What it does

- Enables or disables automatic captures from Decky's Quick Access menu.
- Accepts an interval in milliseconds (minimum: 1000 ms).
- Uses Steam's F12 screenshot hotkey, so screenshots remain in Steam's screenshot library.
- Copies each captured image into a configurable folder (default: `~/Pictures/Deckshots`).
- Persists all settings across Decky and Steam restarts.

Steam does not expose `ISteamScreenshots::TriggerScreenshot` to Decky plugins. Deckshots sends F12 through Steam's controller keyboard interface instead, waits for Steam to register the screenshot, then copies Steam's file. The Steam Overlay and screenshots must be enabled, and a game must be running.

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
