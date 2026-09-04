import asyncio
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import decky


DEFAULT_INTERVAL_MS = 5000
MIN_INTERVAL_MS = 1000
SETTINGS_FILE = "settings.json"
GAMESCOPECTL_PATH = "/usr/bin/gamescopectl"
GAMESCOPE_DISPLAY = "gamescope-0"
SCREENSHOT_WRITE_TIMEOUT_SECONDS = 5
SCREENSHOT_POLL_INTERVAL_SECONDS = 0.05


class Plugin:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._capture_lock = asyncio.Lock()
        self._settings_changed = asyncio.Event()
        self._capture_task = None

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
        if normalised["enabled"]:
            self._start_capture_loop()
        else:
            await self._stop_capture_loop()
        return normalised

    def _start_capture_loop(self) -> None:
        if self._capture_task is not None and not self._capture_task.done():
            self._settings_changed.set()
            return
        self._capture_task = asyncio.create_task(self._capture_loop())

    async def _stop_capture_loop(self) -> None:
        task = self._capture_task
        if task is None:
            return
        self._settings_changed.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if self._capture_task is task:
            self._capture_task = None

    async def _capture_loop(self) -> None:
        decky.logger.info("Automatic screenshot loop started")
        try:
            while True:
                self._settings_changed.clear()
                settings = await self.get_settings()
                if not settings["enabled"]:
                    return

                try:
                    await asyncio.wait_for(
                        self._settings_changed.wait(),
                        timeout=settings["interval_ms"] / 1000,
                    )
                    # Settings changed; restart the wait using the new interval.
                    continue
                except asyncio.TimeoutError:
                    await self.capture_screenshot()
        except asyncio.CancelledError:
            raise
        finally:
            decky.logger.info("Automatic screenshot loop stopped")
            if self._capture_task is asyncio.current_task():
                self._capture_task = None

    def _gamescope_socket(self) -> Path:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        return Path(runtime_dir) / GAMESCOPE_DISPLAY

    def _request_gamescope_screenshot_sync(self, destination: Path) -> None:
        socket_path = self._gamescope_socket()
        if not socket_path.exists():
            raise RuntimeError(f"Gamescope control socket is unavailable: {socket_path}")
        if not Path(GAMESCOPECTL_PATH).is_file():
            raise RuntimeError(f"SteamOS Gamescope control client is unavailable: {GAMESCOPECTL_PATH}")

        environment = os.environ.copy()
        environment["XDG_RUNTIME_DIR"] = str(socket_path.parent)
        environment["GAMESCOPE_WAYLAND_DISPLAY"] = socket_path.name
        try:
            completed = subprocess.run(
                [GAMESCOPECTL_PATH, "screenshot", str(destination)],
                check=True,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "").strip()
            raise RuntimeError(f"gamescopectl failed: {detail or error.returncode}") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("gamescopectl timed out") from error
        # gamescopectl returns once Gamescope accepts the request. The compositor
        # writes the PNG asynchronously, which normally takes several hundred ms.
        deadline = time.monotonic() + SCREENSHOT_WRITE_TIMEOUT_SECONDS
        while True:
            try:
                if destination.is_file() and destination.stat().st_size > 0:
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                detail = (completed.stderr or completed.stdout or "").strip()
                suffix = f": {detail}" if detail else ""
                raise RuntimeError(f"Gamescope did not write the requested screenshot{suffix}")
            time.sleep(SCREENSHOT_POLL_INTERVAL_SECONDS)
        decky.logger.info("Gamescope wrote screenshot to %s", destination)

    async def _capture_screenshot(self) -> str:
        async with self._capture_lock:
            settings = await self.get_settings()
            destination_dir = Path(settings["output_path"])
            destination_dir.mkdir(parents=True, exist_ok=True)
            captured = datetime.now()
            destination = destination_dir / f"deckshot_{captured:%Y-%m-%d_%H-%M-%S}.png"
            counter = 1
            while destination.exists():
                destination = destination_dir / f"deckshot_{captured:%Y-%m-%d_%H-%M-%S}_{counter}.png"
                counter += 1
            await asyncio.to_thread(self._request_gamescope_screenshot_sync, destination)
            return str(destination)

    async def capture_screenshot(self) -> dict:
        try:
            return {"ok": True, "path": await self._capture_screenshot(), "error": None}
        except Exception as error:
            message = str(error) or type(error).__name__
            decky.logger.exception("Deckshots capture failed: %s", message)
            return {"ok": False, "path": None, "error": message}

    async def _main(self):
        decky.logger.info("Deckshots loaded")
        if (await self.get_settings())["enabled"]:
            self._start_capture_loop()

    async def _unload(self):
        await self._stop_capture_loop()
        decky.logger.info("Deckshots unloaded")
