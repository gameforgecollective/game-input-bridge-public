"""Coordinated game-input checks with fake native I/O; no real keys are sent."""

import ctypes
import struct
import unittest
from unittest.mock import Mock, patch

import game_input_mcp as bridge


class CharacterControlTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.pressed = set()
        self.moves = []
        self.sleep_states = []
        self.key_events = []
        bridge.held_keys.clear()
        self.addCleanup(bridge.held_keys.clear)

        def capture(count, pointer, size):
            packet = ctypes.string_at(pointer, size)
            offset = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4
            dx, dy = struct.unpack_from("<ll", packet, offset)
            self.moves.append((dx, dy, set(self.pressed)))
            return 1

        def press(key):
            self.key_events.append(("down", key))
            self.pressed.add(key)

        def release(key):
            self.key_events.append(("up", key))
            self.pressed.discard(key)

        def sleep(seconds):
            self.assertGreaterEqual(seconds, 0)
            self.sleep_states.append(set(self.pressed))
            self.now += seconds

        self.native = Mock()
        self.native.SendInput = Mock(side_effect=capture)
        for patcher in (
            patch.object(ctypes, "WinDLL", return_value=self.native),
            patch.object(bridge, "active_window_title", return_value="Camera Mode"),
            patch.object(bridge.pyautogui, "keyDown", side_effect=press),
            patch.object(bridge.pyautogui, "keyUp", side_effect=release),
            patch.object(bridge.pyautogui, "failSafeCheck"),
            patch.object(bridge.time, "perf_counter", side_effect=lambda: self.now),
            patch.object(bridge.time, "sleep", side_effect=sleep),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def control(self, **kwargs):
        self.assertTrue(callable(getattr(bridge, "control_character", None)), "Coordinated movement is not implemented")
        return bridge.control_character("Camera Mode", **kwargs)

    def test_sprint_and_look_happen_while_both_keys_are_held(self):
        result = self.control(keys=["W", "ctrl"], dx=60, dy=-30, duration_ms=60)
        self.assertTrue(self.moves)
        self.assertTrue(all(held == {"w", "ctrl"} for _, _, held in self.moves))
        self.assertEqual((sum(x for x, _, _ in self.moves), sum(y for _, y, _ in self.moves)), (60, -30))
        self.assertEqual(self.pressed, set())
        self.assertEqual(bridge.held_keys, set())
        self.assertTrue(result["released"])
        self.assertAlmostEqual(self.now, 0.06)

    def test_forward_jump_without_camera_motion_holds_for_the_requested_time(self):
        self.control(keys=["w", "space"], duration_ms=80)
        self.assertFalse(self.moves)
        self.assertTrue(self.sleep_states)
        self.assertTrue(all(held == {"w", "space"} for held in self.sleep_states))
        self.assertAlmostEqual(self.now, 0.08)
        self.assertFalse(self.pressed)

    def test_smooth_turn_starts_and_ends_gently_without_losing_distance(self):
        self.control(keys=[], dx=100, duration_ms=100)
        amounts = [x for x, _, _ in self.moves]
        self.assertEqual(sum(amounts), 100)
        self.assertTrue(all(x > 0 for x in amounts))
        self.assertLess(amounts[0], max(amounts))
        self.assertLess(amounts[-1], max(amounts))

    def test_focus_loss_releases_all_keys_and_stops_camera_events(self):
        with patch.object(bridge, "active_window_title", side_effect=["Camera Mode", "Camera Mode", "Notepad"]):
            with self.assertRaisesRegex(ValueError, "active window"):
                self.control(keys=["w", "ctrl", "space"], dx=60, duration_ms=60)
        self.assertEqual(len(self.moves), 1)
        self.assertFalse(self.pressed)
        self.assertFalse(bridge.held_keys)

    def test_partially_failed_key_press_is_released(self):
        def fail_second(key):
            self.pressed.add(key)
            if key == "space":
                raise OSError("simulated partial key press")

        with patch.object(bridge.pyautogui, "keyDown", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.control(keys=["w", "space"], duration_ms=50)
        self.assertFalse(self.pressed)
        self.assertFalse(bridge.held_keys)

    def test_native_mouse_failure_releases_movement_keys(self):
        self.native.SendInput.side_effect = None
        self.native.SendInput.return_value = 0
        with self.assertRaises(OSError):
            self.control(keys=["w", "ctrl"], dx=20, duration_ms=40)
        self.assertFalse(self.pressed)

    def test_emergency_stop_still_releases_keys_and_restores_the_stop_setting(self):
        def release_with_stop_check(key):
            self.assertFalse(bridge.pyautogui.FAILSAFE)
            self.pressed.discard(key)

        with patch.object(bridge.pyautogui, "failSafeCheck", side_effect=[None, None, bridge.pyautogui.FailSafeException("stop")]):
            with patch.object(bridge.pyautogui, "keyUp", side_effect=release_with_stop_check):
                with self.assertRaises(bridge.pyautogui.FailSafeException):
                    self.control(keys=["w", "ctrl"], dx=40, duration_ms=60)
        self.assertFalse(self.pressed)
        self.assertTrue(bridge.pyautogui.FAILSAFE)

    def test_one_failed_release_does_not_prevent_releasing_the_other_keys(self):
        def release_except_space(key):
            if key == "space":
                raise OSError("simulated failed key release")
            self.pressed.discard(key)

        with patch.object(bridge.pyautogui, "keyUp", side_effect=release_except_space):
            with self.assertRaisesRegex(RuntimeError, "could not be released"):
                self.control(keys=["w", "space"], duration_ms=30)
        self.assertEqual(self.pressed, {"space"})
        self.assertEqual(bridge.held_keys, {"space"})
        self.assertTrue(bridge.pyautogui.FAILSAFE)

    def test_native_call_overhead_does_not_accumulate_into_extra_hold_time(self):
        capture = self.native.SendInput.side_effect

        def delayed_capture(*args):
            result = capture(*args)
            self.now += 0.003
            return result

        self.native.SendInput.side_effect = delayed_capture
        self.control(keys=["w"], dx=100, duration_ms=100)
        self.assertAlmostEqual(self.now, 0.1)

    def test_invalid_movement_is_rejected_before_any_key_press(self):
        for args in (
            {"keys": ["e"]}, {"keys": ["w", "s"]},
            {"keys": ["a", "d"]}, {"keys": ["w"], "dx": 601},
            {"keys": ["w"], "duration_ms": 2001},
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.control(**args)
        self.assertFalse(self.key_events)
        self.assertFalse(self.moves)


if __name__ == "__main__":
    unittest.main()
