import unittest

try:
    import game_input_controls as controls
except ModuleNotFoundError:
    controls = None


class GameInputControlsTests(unittest.TestCase):
    def require_controls(self):
        self.assertIsNotNone(controls, "game input safety controls are not implemented")

    def test_requires_expected_foreground_window(self):
        self.require_controls()
        self.assertTrue(controls.validate_target("Camera Mode", "Camera Mode - World"))
        with self.assertRaises(ValueError):
            controls.validate_target("Camera Mode", "Notepad")

    def test_rejects_unsafe_keys_and_accepts_game_keys(self):
        self.require_controls()
        self.assertEqual(controls.validate_key("W"), "w")
        self.assertEqual(controls.validate_key("space"), "space")
        with self.assertRaises(ValueError):
            controls.validate_key("alt+f4")

    def test_bounds_key_hold_duration(self):
        self.require_controls()
        self.assertEqual(controls.validate_duration_ms(1200), 1200)
        with self.assertRaises(ValueError):
            controls.validate_duration_ms(2001)

    def test_always_releases_a_held_key(self):
        self.require_controls()
        events = []

        def fail_sleep(_duration):
            raise RuntimeError("simulated interruption")

        with self.assertRaises(RuntimeError):
            controls.bounded_hold(
                lambda: events.append("down"),
                lambda: events.append("up"),
                100,
                sleep=fail_sleep,
            )
        self.assertEqual(events, ["down", "up"])

    def test_releases_even_if_press_reports_an_error(self):
        self.require_controls()
        events = []

        def fail_press():
            events.append("down")
            raise RuntimeError("simulated input error")

        with self.assertRaises(RuntimeError):
            controls.bounded_hold(
                fail_press,
                lambda: events.append("up"),
                100,
            )
        self.assertEqual(events, ["down", "up"])

    def test_bounds_relative_mouse_movement(self):
        self.require_controls()
        self.assertEqual(controls.validate_mouse_delta(-500, 300), (-500, 300))
        with self.assertRaises(ValueError):
            controls.validate_mouse_delta(900, 0)


if __name__ == "__main__":
    unittest.main()
