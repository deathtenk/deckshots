import asyncio
import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        fake_decky = types.SimpleNamespace(
            DECKY_PLUGIN_DIR=str(self.root / "plugin"),
            DECKY_PLUGIN_SETTINGS_DIR=str(self.root / "settings"),
            DECKY_USER_HOME=str(self.root / "home"),
            logger=types.SimpleNamespace(
                info=lambda *args: None,
                warning=lambda *args: None,
                error=lambda *args: None,
                exception=lambda *args: None,
            ),
        )
        sys.modules["decky"] = fake_decky
        sys.modules.pop("main", None)
        self.module = importlib.import_module("main")
        self.plugin = self.module.Plugin()

    def tearDown(self):
        sys.modules.pop("main", None)
        sys.modules.pop("decky", None)
        self.tempdir.cleanup()

    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def test_defaults(self):
        settings = self.run_async(self.plugin.get_settings())
        self.assertFalse(settings["enabled"])
        self.assertEqual(settings["interval_ms"], 5000)
        self.assertEqual(settings["output_path"], str(self.root / "home" / "Pictures" / "Deckshots"))

    def test_save_normalises_and_persists(self):
        output = self.root / "captures"
        saved = self.run_async(self.plugin.save_settings({
            "enabled": False,
            "interval_ms": 200,
            "output_path": str(output),
        }))
        self.assertEqual(saved["interval_ms"], 1000)
        self.assertTrue(output.is_dir())
        on_disk = json.loads((self.root / "settings" / "settings.json").read_text())
        self.assertEqual(saved, on_disk)

    def test_enabling_starts_and_disabling_stops_backend_loop(self):
        async def exercise_loop():
            settings = {
                "enabled": True,
                "interval_ms": 5000,
                "output_path": str(self.root / "captures"),
            }
            await self.plugin.save_settings(settings)
            task = self.plugin._capture_task
            self.assertIsNotNone(task)
            self.assertFalse(task.done())

            await self.plugin.save_settings({**settings, "enabled": False})
            self.assertIsNone(self.plugin._capture_task)
            self.assertTrue(task.done())

        self.run_async(exercise_loop())

    def test_main_restores_enabled_backend_loop(self):
        settings = {
            "enabled": True,
            "interval_ms": 5000,
            "output_path": str(self.root / "captures"),
        }
        self.plugin._write_settings(settings)

        async def load_and_unload():
            await self.plugin._main()
            self.assertIsNotNone(self.plugin._capture_task)
            self.assertFalse(self.plugin._capture_task.done())
            await self.plugin._unload()
            self.assertIsNone(self.plugin._capture_task)

        self.run_async(load_and_unload())

    def test_rejects_relative_output_path(self):
        with self.assertRaises(ValueError):
            self.run_async(self.plugin.save_settings({
                "enabled": False,
                "interval_ms": 5000,
                "output_path": "relative/path",
            }))

    def test_gamescope_socket_uses_runtime_directory(self):
        with patch.dict(self.module.os.environ, {"XDG_RUNTIME_DIR": str(self.root / "runtime")}):
            self.assertEqual(
                self.plugin._gamescope_socket(),
                self.root / "runtime" / "gamescope-0",
            )

    def test_requests_screenshot_through_gamescope_control(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "gamescope-0").touch()
        helper = self.root / "gamescopectl"
        helper.touch()
        destination = self.root / "capture.png"

        def run(command, **kwargs):
            destination.write_bytes(b"png")
            return types.SimpleNamespace(stdout="", stderr="")

        with patch.dict(self.module.os.environ, {"XDG_RUNTIME_DIR": str(runtime)}), \
             patch.object(self.module, "GAMESCOPECTL_PATH", str(helper)), \
             patch.object(self.module.subprocess, "run", side_effect=run) as execute:
            self.plugin._request_gamescope_screenshot_sync(destination)

        command = execute.call_args.args[0]
        environment = execute.call_args.kwargs["env"]
        self.assertEqual(command, [str(helper), "screenshot", str(destination)])
        self.assertEqual(environment["XDG_RUNTIME_DIR"], str(runtime))
        self.assertEqual(environment["GAMESCOPE_WAYLAND_DISPLAY"], "gamescope-0")

    def test_waits_for_gamescope_to_finish_writing(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "gamescope-0").touch()
        helper = self.root / "gamescopectl"
        helper.touch()
        destination = self.root / "delayed.png"

        completed = types.SimpleNamespace(stdout="", stderr="")
        with patch.dict(self.module.os.environ, {"XDG_RUNTIME_DIR": str(runtime)}), \
             patch.object(self.module, "GAMESCOPECTL_PATH", str(helper)), \
             patch.object(self.module.subprocess, "run", return_value=completed), \
             patch.object(self.module.time, "sleep", side_effect=lambda _: destination.write_bytes(b"png")) as sleep:
            self.plugin._request_gamescope_screenshot_sync(destination)

        sleep.assert_called_once_with(self.module.SCREENSHOT_POLL_INTERVAL_SECONDS)

    def test_capture_returns_backend_error_message(self):
        with patch.object(
            self.plugin, "_capture_screenshot", new=AsyncMock(side_effect=RuntimeError("specific failure"))
        ):
            result = self.run_async(self.plugin.capture_screenshot())

        self.assertEqual(result, {"ok": False, "path": None, "error": "specific failure"})


if __name__ == "__main__":
    unittest.main()
