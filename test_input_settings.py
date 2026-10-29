"""Local input settings use synthetic window names and send no input."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


class InputSettingsTests(unittest.TestCase):
    def load(self, settings=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        shutil.copy2(Path(__file__).with_name("game_input_controls.py"), root / "game_input_controls.py")
        if settings is not None:
            (root / "input-settings.local.json").write_text(json.dumps(settings), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("isolated_controls", root / "game_input_controls.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_unknown_window_uses_physical_keyboard_without_assuming_verified_controls(self):
        name, settings = self.load().game_profile_for_window("My Foreground Window")
        self.assertEqual(name, "unverified")
        self.assertEqual(settings["keyboard_backend"], "sendinput_scancode")

    def test_local_title_and_keyboard_settings_are_loaded_without_source_edits(self):
        controls = self.load({"window_title": "My Foreground Window", "input_style": "pointer",
                              "keyboard_backend": "pyautogui_virtual_key"})
        name, settings = controls.game_profile_for_window("My Foreground Window")
        self.assertEqual(name, "pointer_mode")
        self.assertEqual(settings["keyboard_backend"], "pyautogui_virtual_key")
        self.assertEqual(settings["window_title"], "My Foreground Window")

    def test_invalid_settings_fail_before_input(self):
        for settings in ({"window_title": "", "input_style": "pointer"},
                         {"window_title": "My Window", "input_style": "unknown"},
                         {"window_title": "My Window", "keyboard_backend": "arbitrary-code"},
                         {"window_title": "My Window", "max_hold_ms": 90000}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.load(settings)


if __name__ == "__main__":
    unittest.main()
