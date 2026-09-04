import asyncio
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import decky


DEFAULT_INTERVAL_MS = 5000
MIN_INTERVAL_MS = 1000
SETTINGS_FILE = "settings.json"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".avif"}


class Plugin:
    def __init__(self):
        self._lock = asyncio.Lock()

    @property
    def _settings_path(self) -> Path:
        return Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / SETTINGS_FILE

    def _defaults(self) -> dict:
        return {
            "enabled": False,
            "interval_ms": DEFAULT_INTERVAL_MS,
            "output_path": str(Path(decky.DECKY_USER_HOME) / "Pictures" / "Deckshots"),
        }

    def _normalise(self, raw: dict) -> dict:
        defaults = self._defaults()
        try:
            interval = max(MIN_INTERVAL_MS, int(raw.get("interval_ms", defaults["interval_ms"])))
        except (TypeError, ValueError):
            interval = defaults["interval_ms"]

        output = str(raw.get("output_path", defaults["output_path"])).strip()
        output = os.path.expandvars(os.path.expanduser(output))
        if not output or not os.path.isabs(output):
            raise ValueError("Output folder must be an absolute path (or start with ~)")
        return {
            "enabled": bool(raw.get("enabled", defaults["enabled"])),
            "interval_ms": interval,
            "output_path": output,
        }

    def _read_settings(self) -> dict:
        if not self._settings_path.exists():
            return self._defaults()
        try:
            with self._settings_path.open("r", encoding="utf-8") as handle:
                return self._normalise(json.load(handle))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            decky.logger.warning("Could not read Deckshots settings: %s", error)
            return self._defaults()

    def _write_settings(self, settings: dict) -> None:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._settings_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
            handle.write("\n")
        temporary.replace(self._settings_path)

    async def get_settings(self) -> dict:
        async with self._lock:
            return self._read_settings()

    async def save_settings(self, settings: dict) -> dict:
        normalised = self._normalise(settings)
        output = Path(normalised["output_path"])
        output.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            self._write_settings(normalised)
        return normalised

    async def copy_screenshot(self, sourcePath: str, appId: int, createdAt: int) -> dict:
        source = Path(sourcePath).resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ValueError("Steam returned an invalid screenshot path")

        settings = await self.get_settings()
        destination_dir = Path(settings["output_path"])
        destination_dir.mkdir(parents=True, exist_ok=True)

        try:
            captured = datetime.fromtimestamp(int(createdAt))
        except (TypeError, ValueError, OSError):
            captured = datetime.now()
        filename = f"deckshot_{int(appId)}_{captured:%Y-%m-%d_%H-%M-%S}{source.suffix.lower()}"
        destination = destination_dir / filename
        counter = 1
        while destination.exists():
            destination = destination_dir / f"{Path(filename).stem}_{counter}{source.suffix.lower()}"
            counter += 1

        shutil.copy2(source, destination)
        decky.logger.info("Copied Steam screenshot to %s", destination)
        return {"path": str(destination)}

    async def _main(self):
        decky.logger.info("Deckshots loaded")

    async def _unload(self):
        decky.logger.info("Deckshots unloaded")
