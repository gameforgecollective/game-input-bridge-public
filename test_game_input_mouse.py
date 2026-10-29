"""Regression checks for game camera input; no input reaches the desktop."""

import ctypes
import struct
import unittest
from unittest.mock import Mock, patch

import game_input_mcp as bridge


class RelativeCameraInputTests(unittest.TestCase):
    def setUp(self):
        self.packets = []

        def capture(count, pointer, size):
            self.assertEqual(count, 1)
            self.packets.append(ctypes.string_at(pointer, size))
            return 1

        self.native = Mock()
        self.native.SendInput = Mock(side_effect=capture)
        self.dll_patch = patch.object(ctypes, "WinDLL", return_value=self.native)
        self.dll_patch.start()
        self.addCleanup(self.dll_patch.stop)
        self.target_patch = patch.object(bridge, "active_window_title", return_value="Camera Mode")
        self.target_patch.start()
        self.addCleanup(self.target_patch.stop)
        # Re-entering the old desktop cursor path must fail this regression.
        self.cursor_patch = patch.object(bridge.pyautogui, "moveRel", side_effect=AssertionError("desktop cursor positioning cannot drive the camera"))
        self.cursor_patch.start()
        self.addCleanup(self.cursor_patch.stop)

    def test_camera_uses_signed_relative_input_with_correct_native_layout(self):
        result = bridge.move_mouse("Camera Mode", 57, -23, 35)
        self.assertTrue(self.packets, "No relative mouse events were sent")
        movements = []
        for packet in self.packets:
            self.assertEqual(len(packet), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
            self.assertEqual(struct.unpack_from("<I", packet)[0], 0)
            offset = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4
            dx, dy, data, flags = struct.unpack_from("<llII", packet, offset)
            self.assertEqual(data, 0)
            self.assertTrue(flags & 0x0001)
            self.assertFalse(flags & 0x8000, "Camera events must not use absolute coordinates")
            movements.append((dx, dy))
        self.assertEqual(tuple(map(sum, zip(*movements))), (57, -23))
        self.assertGreater(len(movements), 1, "Timed movement must be split into smooth steps")
        self.assertTrue(all(abs(x) <= 15 and abs(y) <= 6 for x, y in movements))
        self.assertEqual(result["backend"], "sendinput_relative")
        self.assertEqual(result["events_sent"], len(self.packets))
        self.assertIs(result["camera_motion_verified"], False)

    def test_native_rejection_is_reported_as_failure(self):
        self.native.SendInput.side_effect = None
        self.native.SendInput.return_value = 0
        with self.assertRaises(OSError):
            bridge.move_mouse("Camera Mode", 10, 0, 1)

    def test_focus_loss_stops_the_remaining_movement(self):
        self.target_patch.stop()
        self.target_patch = patch.object(bridge, "active_window_title", side_effect=["Camera Mode", "Camera Mode", "Notepad"])
        self.target_patch.start()
        with self.assertRaisesRegex(ValueError, "active window"):
            bridge.move_mouse("Camera Mode", 60, -30, 60)
        self.assertEqual(len(self.packets), 1)

    def test_zero_delta_sends_no_events(self):
        result = bridge.move_mouse("Camera Mode", 0, 0, 1)
        self.assertFalse(self.packets)
        self.assertFalse(result["moved"])

    def test_invalid_input_sends_no_events(self):
        with self.assertRaises(ValueError):
            bridge.move_mouse("Camera Mode", 601, 0, 1)
        self.assertFalse(self.packets)


if __name__ == "__main__":
    unittest.main()
