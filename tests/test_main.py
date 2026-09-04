import asyncio
import importlib
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime as RealDatetime
from pathlib import Path
from unittest.mock import patch


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        fake_decky = types.SimpleNamespace(
            DECKY_PLUGIN_SETTINGS_DIR=str(self.root / "settings"),
            DECKY_USER_HOME=str(self.root / "home"),
            logger=types.SimpleNamespace(info=lambda *args: None, warning=lambda *args: None),
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
            "enabled": True,
            "interval_ms": 200,
            "output_path": str(output),
        }))
        self.assertEqual(saved["interval_ms"], 1000)
        self.assertTrue(output.is_dir())
        on_disk = json.loads((self.root / "settings" / "settings.json").read_text())
        self.assertEqual(saved, on_disk)

    def test_rejects_relative_output_path(self):
        with self.assertRaises(ValueError):
            self.run_async(self.plugin.save_settings({
                "enabled": False,
                "interval_ms": 5000,
                "output_path": "relative/path",
            }))

    def test_copies_screenshot_with_stable_name(self):
        source = self.root / "steam-shot.jpg"
        source.write_bytes(b"screenshot")
        output = self.root / "captures"

        async def save_and_copy():
            await self.plugin.save_settings({
                "enabled": True,
                "interval_ms": 5000,
                "output_path": str(output),
            })
            with patch.object(self.module, "datetime") as mocked_datetime:
                mocked_datetime.fromtimestamp.return_value = RealDatetime.strptime(
                    "2026-09-04 12:34:56", "%Y-%m-%d %H:%M:%S"
                )
                return await self.plugin.copy_screenshot(str(source), 123, 1)

        result = self.run_async(save_and_copy())
        destination = Path(result["path"])
        self.assertEqual(destination.name, "deckshot_123_2026-09-04_12-34-56.jpg")
        self.assertEqual(destination.read_bytes(), b"screenshot")

    def test_rejects_non_image_source(self):
        source = self.root / "not-an-image.txt"
        source.write_text("no")
        with self.assertRaises(ValueError):
            self.run_async(self.plugin.copy_screenshot(str(source), 123, 1))


if __name__ == "__main__":
    unittest.main()
