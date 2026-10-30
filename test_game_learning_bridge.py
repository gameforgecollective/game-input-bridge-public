"""Bridge learning integration tests: no keyboard, mouse, capture or focus input."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game_input_mcp as bridge
from game_learning import LearningStore


class LearningBridgeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(bridge, "get_game_learning", None)),
                        "Learning System tools are not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = LearningStore(Path(self.temp.name) / "journal.sqlite3", computer_id="test-pc")
        sharing_patch = patch.object(bridge, "configured_exchange", return_value=None)
        sharing_patch.start()
        self.addCleanup(sharing_patch.stop)
        store_patch = patch.object(bridge, "learning_store", return_value=self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)
        for name in ("send_keyboard_key", "send_relative_mouse", "capture_game_view",
                     "require_target", "target_pointer"):
            blocker = patch.object(bridge, name, side_effect=AssertionError(f"learning called {name}"))
            blocker.start()
            self.addCleanup(blocker.stop)
        for name in ("keyDown", "keyUp", "mouseDown", "mouseUp", "moveTo"):
            blocker = patch.object(bridge.pyautogui, name, side_effect=AssertionError("learning sent input"))
            blocker.start()
            self.addCleanup(blocker.stop)

    def test_inspection_reports_configured_controls_before_input(self):
        fixture = {"window_title": "Calibration Fixture", "keyboard_backend": "sendinput_scancode",
                   "movement": "WASD", "camera": "relative mouse"}
        with patch.dict(bridge.GAME_PROFILES, {"calibration_fixture": fixture}, clear=True), \
             patch.object(bridge, "active_window_title", return_value="Calibration Fixture"):
            result = bridge.inspect_active_window()
        self.assertIn("control_settings", result)
        settings = result["control_settings"]
        self.assertEqual(settings["profile"], "calibration_fixture")
        self.assertEqual(settings["keyboard_backend"], "sendinput_scancode")
        self.assertEqual(settings["bindings"]["movement"], "WASD")
        self.assertEqual(settings["bindings"]["camera"], "relative mouse")
        self.assertFalse(settings["runtime_verified"])
        self.assertFalse(settings["controls_authorized"])
        self.assertFalse(self.store.path.exists())

    def test_inspection_labels_unknown_controls_as_unverified(self):
        with patch.object(bridge, "active_window_title", return_value="Calibration Unknown"):
            result = bridge.inspect_active_window()
        self.assertIn("control_settings", result)
        settings = result["control_settings"]
        self.assertEqual(settings["profile"], "unverified")
        self.assertIn(settings["keyboard_backend"], {"sendinput_scancode", "pyautogui_virtual_key"})
        self.assertEqual(settings["bindings"], {})
        self.assertFalse(settings["runtime_verified"])
        self.assertFalse(settings["controls_authorized"])
        self.assertIsNone(result["learning_system"])
        self.assertFalse(self.store.path.exists())

    def test_absent_foreground_has_no_active_control_settings(self):
        with patch.object(bridge, "active_window_title", return_value=""):
            result = bridge.inspect_active_window()
        self.assertIn("control_settings", result)
        self.assertIsNone(result["control_settings"])
        self.assertFalse(result["input_ready"])

    def test_modifying_diagnostics_cannot_change_controls_or_safety(self):
        fixture = {"window_title": "Calibration Fixture", "keyboard_backend": "sendinput_scancode",
                   "movement": "WASD"}
        with patch.dict(bridge.GAME_PROFILES, {"calibration_fixture": fixture}, clear=True), \
             patch.object(bridge, "active_window_title", return_value="Calibration Fixture"):
            first = bridge.inspect_active_window()
            self.assertIn("control_settings", first)
            first["control_settings"]["bindings"]["movement"] = "unsafe override"
            first["control_settings"]["limits"]["max_hold_ms"] = 90000
            second = bridge.inspect_active_window()["control_settings"]
            self.assertEqual(second["bindings"]["movement"], "WASD")
            with self.assertRaises(ValueError):
                bridge.validate_duration_ms(2001)
            self.assertEqual(second["limits"], {"max_hold_ms": 2000,
                "max_mouse_delta": 600, "max_sequence_steps": 3, "max_sequence_ms": 8000})

    def record(self, **changes):
        data = dict(game="Pointer Mode", title="Coop routine", category="routine",
                    status="observed", source="demonstration", attempted="Collect eggs",
                    expected="Eggs enter inventory", before="Two eggs on coop floor",
                    observed="Egg x2 pickup text", evidence=["demo.md:egg-pickup"], context={})
        data.update(changes)
        return bridge.record_game_lesson(**data)

    def test_record_recall_correct_and_history_without_input(self):
        row = self.record()
        self.assertFalse(row["controls_authorized"])
        current = bridge.get_game_learning("Pointer Mode")
        self.assertEqual(current["lessons"][0]["id"], row["record"]["id"])
        update = bridge.correct_game_lesson(row["record"]["id"], status="uncertain",
            source="user_explanation", observed="Need to check the full coop next time",
            evidence=[], reason="Snapshot did not cover every corner")
        history = bridge.get_game_lesson_history(row["record"]["lesson_id"])
        self.assertEqual(history["total_records"], 2)
        self.assertEqual(history["records"][-1]["id"], update["record"]["id"])

    def test_foreground_inspection_automatically_recalls_known_game(self):
        self.record()
        with patch.object(bridge, "active_window_title", return_value="Pointer Mode"):
            result = bridge.inspect_active_window()
        self.assertEqual(result["title"], "Pointer Mode")
        self.assertTrue(result["input_ready"])
        self.assertTrue(result["learning_system"]["available"])
        self.assertEqual(result["learning_system"]["lessons"][0]["title"], "Coop routine")
        self.assertFalse(result["learning_system"]["controls_authorized"])

    def test_unknown_app_is_not_assumed_to_be_a_game(self):
        for title in ("Notepad", "", "Windows Lock Screen"):
            with self.subTest(title=title), patch.object(bridge, "active_window_title", return_value=title):
                self.assertIsNone(bridge.inspect_active_window()["learning_system"])
        self.assertFalse(self.store.path.exists())

    def test_distinct_game_titles_do_not_inherit_substring_matches(self):
        self.record(game="Camera Mode")
        self.record(game="Camera Mode Expansion", title="Dungeons control")
        self.assertEqual(bridge.get_game_learning("Camera Mode")["total_lessons"], 1)
        self.assertEqual(bridge.get_game_learning("Camera Mode Expansion")["lessons"][0]["title"], "Dungeons control")
        for title in ("Camera Mode Expansion", "Alternate Camera Mode notes - Notepad"):
            with self.subTest(title=title), patch.object(bridge, "active_window_title", return_value=title):
                self.assertIsNone(bridge.inspect_active_window()["learning_system"])

    def test_exact_known_aliases_match_but_invalid_names_are_not_rewritten(self):
        self.record(game="Legacy Camera Mode")
        self.assertEqual(bridge.get_game_learning("legacy_camera_mode")["total_lessons"], 1)
        with self.assertRaises(ValueError):
            self.record(game="C:\\games\\Camera Mode")
        self.record(game="Sample Adventure: Chapter One")
        self.assertEqual(bridge.get_game_learning("Sample Adventure: Chapter One")["total_lessons"], 1)

    def test_learning_storage_failure_is_explicit_and_preserves_foreground_info(self):
        self.store.path.write_bytes(b"broken SQLite")
        with patch.object(bridge, "active_window_title", return_value="Pointer Mode"):
            result = bridge.inspect_active_window()
        self.assertEqual(result["title"], "Pointer Mode")
        self.assertFalse(result["learning_system"]["available"])
        self.assertIn("control_settings", result)
        self.assertEqual(result["control_settings"]["keyboard_backend"], "sendinput_scancode")
        self.assertTrue(result["learning_system"]["error"])
        self.assertFalse(result["learning_system"]["controls_authorized"])
        with self.assertRaises(Exception):
            bridge.get_game_learning("Pointer Mode")

    def test_learning_tools_registered_in_mcp_discovery(self):
        tools = asyncio.run(bridge.mcp.list_tools())
        names = {tool.name for tool in tools}
        self.assertTrue({"get_game_learning", "record_game_lesson", "correct_game_lesson",
                         "get_game_lesson_history"} <= names)

    def test_shared_lessons_are_returned_separately_and_local_save_survives_sync_error(self):
        from game_learning_sync import GitLearningExchange
        other = LearningStore(Path(self.temp.name) / "other.sqlite3", computer_id="other-pc")
        other.record("pointer_mode", title="Remote routine", category="routine", status="observed",
            source="demonstration", attempted="Watch", expected="See result", before="Before",
            observed="Observed result", evidence=["remote.md"], context={})
        self.store.import_records(other.export_records("AgentThree"))
        result = bridge.get_game_learning("Pointer Mode", sync_shared=False)
        self.assertEqual(result["shared_learning"]["lessons"][0]["helper"], "AgentThree")
        self.assertFalse(result["shared_learning"]["lessons"][0]["tested_on_this_pc"])
        exchange = GitLearningExchange(self.store, str(Path(self.temp.name) / "missing.git"), "AgentOne")
        with patch.object(bridge, "configured_exchange", return_value=exchange):
            saved = self.record()
        self.assertFalse(saved["sharing"]["ok"])
        self.assertTrue(saved["sharing"]["pending_sync"])
        self.assertEqual(self.store.recall("Pointer Mode")["total_lessons"], 1)

    def test_foreground_recall_is_cached_and_never_runs_git_sync(self):
        with patch.object(bridge, "active_window_title", return_value="Pointer Mode"), \
             patch.object(bridge, "configured_exchange", side_effect=AssertionError("foreground recall must not sync")):
            self.assertTrue(bridge.inspect_active_window()["learning_system"]["available"])

    def test_learning_identity_stays_separate_when_input_style_is_reused(self):
        settings = dict(bridge.GAME_PROFILES["pointer_mode"], window_title="Window A")
        with patch.dict(bridge.GAME_PROFILES, {"pointer_mode": settings}):
            self.record(game="Window A", title="Window A lesson")
            bridge.GAME_PROFILES["pointer_mode"] = dict(settings, window_title="Window B")
            self.assertEqual(bridge.get_game_learning("Window B", sync_shared=False)["total_lessons"], 0)
            self.assertEqual(bridge.get_game_learning("Window A", sync_shared=False)["total_lessons"], 1)

    def test_configured_foreground_recalls_actual_window_learning_key(self):
        settings = dict(bridge.GAME_PROFILES["pointer_mode"], window_title="My Foreground Window")
        with patch.dict(bridge.GAME_PROFILES, {"pointer_mode": settings}), \
             patch.object(bridge, "active_window_title", return_value="My Foreground Window"):
            self.record(game="My Foreground Window", title="Configured window lesson")
            result = bridge.inspect_active_window()["learning_system"]
            self.assertIsNotNone(result)
            self.assertEqual(result["game_id"], "my_foreground_window")
            self.assertEqual(result["lessons"][0]["title"], "Configured window lesson")


if __name__ == "__main__":
    unittest.main()
