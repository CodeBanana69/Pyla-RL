import unittest
from unittest.mock import patch

from window_controller import (
    WindowController,
    DEFAULT_BRAWL_STARS_PACKAGE,
    _foreground_package_from_text,
    _package_task_display_from_text,
    _valid_window_rect,
    _window_title_matches_emulator,
    resolve_brawl_stars_package,
)


class LongRunWatchdogTests(unittest.TestCase):
    def test_foreground_package_parser_handles_current_focus(self):
        text = "mCurrentFocus=Window{123 u0 com.supercell.brawlstars/com.supercell.titan.GameApp}"
        self.assertEqual(_foreground_package_from_text(text), "com.supercell.brawlstars")

    def test_foreground_package_parser_handles_focused_app(self):
        text = "mFocusedApp=ActivityRecord{123 u0 com.android.launcher/.Launcher t1}"
        self.assertEqual(_foreground_package_from_text(text), "com.android.launcher")

    def test_foreground_package_parser_ignores_input_method_target(self):
        text = (
            "mInputMethodTarget=Window{123 u0 com.android.launcher/.Launcher}\n"
            "topResumedActivity=ActivityRecord{456 u0 com.supercell.brawlstars/com.supercell.titan.GameApp}"
        )
        self.assertEqual(_foreground_package_from_text(text), "com.supercell.brawlstars")

    def test_host_window_title_matching_supports_ldplayer_and_mumu(self):
        self.assertTrue(_window_title_matches_emulator("LDPlayer - Brawl Stars", "LDPlayer"))
        self.assertTrue(_window_title_matches_emulator("Android Device", "MuMu"))
        self.assertTrue(_window_title_matches_emulator("Brawl Stars", "MuMu"))
        self.assertFalse(_window_title_matches_emulator("Command Prompt", "MuMu"))

    def test_host_window_rect_rejects_tiny_windows(self):
        self.assertTrue(_valid_window_rect((10, 10, 810, 610)))
        self.assertFalse(_valid_window_rect((10, 10, 80, 60)))

    def test_package_display_parser_finds_hidden_mumu_display(self):
        text = (
            "RootTask{abc #1 type=home displayId=0}\n"
            "  * Task{home #10 A=com.mumu.launcher U=0 displayId=0}\n"
            "RootTask{def #2 type=standard displayId=6}\n"
            "  * Task{game #42 A=com.supercell.brawlstars U=0 visible=true}\n"
        )
        self.assertEqual(
            _package_task_display_from_text(text, "com.supercell.brawlstars"),
            (42, 6),
        )

    @patch("window_controller.time.time")
    def test_emulator_restart_respects_cooldown(self, mock_time):
        controller = object.__new__(WindowController)
        controller.last_emulator_restart_time = 100.0
        controller.emulator_restart_cooldown = 180.0
        mock_time.return_value = 150.0

        self.assertFalse(controller.restart_emulator_profile())

    @patch.object(WindowController, "launch_saved_emulator_profile", return_value=False)
    @patch.object(WindowController, "keys_up")
    @patch("window_controller.time.time")
    def test_emulator_restart_failure_does_not_raise(self, mock_time, _mock_keys_up, _mock_launch):
        controller = object.__new__(WindowController)
        controller.selected_emulator = "LDPlayer"
        controller.emulator_profile_index = 0
        controller.configured_serial = "emulator-5554"
        controller.scrcpy_client = None
        controller.last_emulator_restart_time = 0.0
        controller.emulator_restart_cooldown = 180.0
        mock_time.return_value = 300.0

        self.assertFalse(controller.restart_emulator_profile())

    @patch("window_controller._start_android_app_on_display", return_value=True)
    @patch("window_controller._stop_android_app", return_value=True)
    @patch("window_controller._move_android_task_to_display", return_value=True)
    @patch("window_controller._wake_android_display")
    @patch("window_controller.time.sleep")
    @patch(
        "window_controller._get_package_task_display",
        side_effect=[(42, 10), (42, 10), (42, 10)],
    )
    def test_passive_display_repair_does_not_restart_app(
        self,
        _mock_display,
        _mock_sleep,
        _mock_wake,
        _mock_move,
        mock_stop,
        _mock_start,
    ):
        controller = object.__new__(WindowController)
        controller.connected_serial = "emulator-5554"
        controller.brawl_stars_package = "com.supercell.brawlstars"
        controller.last_known_display_id = 0
        controller.display_repair_count = 0
        controller.recovery_logger = None

        self.assertFalse(controller.ensure_brawl_stars_on_primary_display(passive=True))
        mock_stop.assert_not_called()

    @patch("window_controller._start_android_app_on_display", return_value=True)
    @patch("window_controller._stop_android_app", return_value=True)
    @patch("window_controller._move_android_task_to_display", return_value=True)
    @patch("window_controller._wake_android_display")
    @patch("window_controller.time.sleep")
    @patch("window_controller.time.time", return_value=1000.0)
    @patch(
        "window_controller._get_package_task_display",
        side_effect=[(42, 10), (42, 10), (42, 10)],
    )
    def test_display_repair_app_restart_respects_cooldown(
        self,
        _mock_display,
        _mock_time,
        _mock_sleep,
        _mock_wake,
        _mock_move,
        mock_stop,
        _mock_start,
    ):
        controller = object.__new__(WindowController)
        controller.connected_serial = "emulator-5554"
        controller.brawl_stars_package = "com.supercell.brawlstars"
        controller.last_known_display_id = 0
        controller.display_repair_count = 0
        controller.app_restart_count = 0
        controller.recovery_logger = None
        controller.last_display_app_restart_time = 980.0
        controller.display_app_restart_cooldown = 60.0

        self.assertFalse(controller.ensure_brawl_stars_on_primary_display(allow_app_restart=True))
        mock_stop.assert_not_called()

    @patch("window_controller._kill_scrcpy_server_on_device", return_value=True)
    @patch("window_controller.time.sleep")
    @patch("window_controller.threading.Thread")
    def test_restart_scrcpy_client_kills_device_server_when_stop_times_out(
        self,
        mock_thread_class,
        _mock_sleep,
        mock_kill,
    ):
        controller = object.__new__(WindowController)
        controller.scrcpy_generation = 0
        controller.connected_serial = "emulator-5554"
        controller._SCRCPY_STOP_TIMEOUT = 5.0
        controller.scrcpy_restart_count = 0
        controller.scrcpy_restart_window = []
        controller.recovery_logger = None
        controller.ensure_emulator_online = lambda: True
        controller.is_emulator_online = lambda: True
        controller.start_scrcpy_client = lambda: None
        controller.wait_for_fresh_frame = lambda timeout=6.0: True
        controller.scrcpy_client = object()

        stop_thread = mock_thread_class.return_value
        stop_thread.is_alive.return_value = True

        self.assertTrue(controller.restart_scrcpy_client())
        mock_kill.assert_called_once_with("emulator-5554")

    def test_kill_scrcpy_server_on_device_uses_pkill(self):
        from window_controller import _kill_scrcpy_server_on_device

        with patch("window_controller._run_adb") as mock_run:
            mock_run.return_value.returncode = 0
            self.assertTrue(_kill_scrcpy_server_on_device("emulator-5554"))
            self.assertTrue(
                any("pkill" in args[0][1] for args in mock_run.call_args_list)
            )

    @patch("window_controller._start_android_app_on_display", return_value=True)
    @patch("window_controller._stop_android_app", return_value=True)
    @patch("window_controller._move_android_task_to_display", return_value=True)
    @patch("window_controller._wake_android_display")
    @patch("window_controller.time.sleep")
    @patch(
        "window_controller._get_package_task_display",
        side_effect=[(42, 10), (42, 10), (42, 10), (42, 0)],
    )
    def test_primary_display_repair_force_restarts_when_move_does_not_stick(
        self,
        _mock_display,
        _mock_sleep,
        _mock_wake,
        _mock_move,
        mock_stop,
        mock_start,
    ):
        controller = object.__new__(WindowController)
        controller.connected_serial = "emulator-5554"
        controller.brawl_stars_package = "com.supercell.brawlstars"
        controller.last_display_app_restart_time = 0.0
        controller.display_app_restart_cooldown = 60.0
        controller.display_repair_count = 0
        controller.app_restart_count = 0
        controller.recovery_logger = None

        self.assertTrue(controller.ensure_brawl_stars_on_primary_display(allow_app_restart=True))
        mock_stop.assert_called_once_with("emulator-5554", "com.supercell.brawlstars")
        mock_start.assert_called_with(
            "emulator-5554",
            "com.supercell.brawlstars",
            display_id=0,
        )

    @patch("window_controller._start_android_app_on_display", return_value=True)
    @patch("window_controller._stop_android_app", return_value=True)
    @patch("window_controller._move_android_task_to_display", return_value=True)
    @patch("window_controller._wake_android_display")
    @patch("window_controller.time.sleep")
    @patch(
        "window_controller._get_package_task_display",
        side_effect=[(42, 10), (42, 10), (42, 10)],
    )
    def test_primary_display_log_only_does_not_restart_app(
        self,
        _mock_display,
        _mock_sleep,
        _mock_wake,
        _mock_move,
        mock_stop,
        _mock_start,
    ):
        controller = object.__new__(WindowController)
        controller.connected_serial = "emulator-5554"
        controller.brawl_stars_package = "com.supercell.brawlstars"

        self.assertFalse(controller.ensure_brawl_stars_on_primary_display(log_only=True))
        mock_stop.assert_not_called()

    def test_restart_brawl_stars_returns_false_when_adb_is_offline(self):
        controller = object.__new__(WindowController)
        controller.ensure_emulator_online = lambda: False

        self.assertFalse(controller.restart_brawl_stars())

    def test_restart_scrcpy_client_returns_false_when_start_fails_offline(self):
        controller = object.__new__(WindowController)
        controller.scrcpy_client = None
        controller.scrcpy_generation = 0
        controller.is_emulator_online = lambda: False
        controller.ensure_calls = 0

        def ensure_emulator_online():
            controller.ensure_calls += 1
            return controller.ensure_calls == 1

        controller.ensure_emulator_online = ensure_emulator_online
        controller.start_scrcpy_client = lambda: (_ for _ in ()).throw(Exception("device offline"))

        self.assertFalse(controller.restart_scrcpy_client())
        self.assertEqual(controller.ensure_calls, 2)

    def test_restart_scrcpy_client_requires_fresh_frame(self):
        controller = object.__new__(WindowController)
        controller.scrcpy_client = None
        controller.scrcpy_generation = 0
        controller.ensure_emulator_online = lambda: True
        controller.is_emulator_online = lambda: True
        controller.start_scrcpy_client = lambda: None
        controller.wait_for_fresh_frame = lambda timeout=6.0: False

        self.assertFalse(controller.restart_scrcpy_client())

    def test_press_key_does_not_crash_when_scrcpy_control_is_missing(self):
        controller = object.__new__(WindowController)
        controller.scrcpy_client = object()
        controller.connected_serial = "emulator-5554"
        controller.width_ratio = 1.0
        controller.height_ratio = 1.0
        controller.PID_ATTACK = 1
        controller.restart_calls = 0
        controller.adb_taps = []

        def restart_scrcpy_client():
            controller.restart_calls += 1
            return False

        controller.restart_scrcpy_client = restart_scrcpy_client
        controller._adb_tap = lambda x, y: controller.adb_taps.append((x, y)) or True

        self.assertTrue(controller.press_key("Q"))
        self.assertEqual(controller.restart_calls, 1)
        self.assertEqual(len(controller.adb_taps), 1)

    def test_movement_does_not_enter_moving_state_without_scrcpy_control(self):
        controller = object.__new__(WindowController)
        controller.scrcpy_client = object()
        controller.connected_serial = "emulator-5554"
        controller.joystick_x = 100
        controller.joystick_y = 100
        controller.PID_JOYSTICK = 0
        controller.are_we_moving = False
        controller.last_joystick_down_time = 0.0
        controller.last_joystick_pos = (None, None)
        controller.restart_scrcpy_client = lambda: False

        controller.keys_down(["w"])

        self.assertFalse(controller.are_we_moving)

    def test_resolve_brawl_stars_package_uses_default_when_missing(self):
        self.assertEqual(
            resolve_brawl_stars_package({}),
            DEFAULT_BRAWL_STARS_PACKAGE,
        )

    def test_brawl_stars_package_property_matches_instance_value(self):
        controller = object.__new__(WindowController)
        controller.brawl_stars_package = "com.example.brawl"
        self.assertEqual(controller.BRAWL_STARS_PACKAGE, "com.example.brawl")

    def test_is_brawl_stars_running_uses_instance_package(self):
        controller = object.__new__(WindowController)
        controller.brawl_stars_package = "com.custom.brawl"
        controller.foreground_package = lambda timeout=3: "com.custom.brawl"
        self.assertTrue(controller.is_brawl_stars_running())

    @patch("window_controller._start_android_app_on_display", return_value=False)
    def test_start_brawl_stars_app_falls_back_to_device(self, _mock_adb_start):
        controller = object.__new__(WindowController)
        controller.brawl_stars_package = "com.supercell.brawlstars"
        controller.connected_serial = "emulator-5554"
        controller.device = unittest.mock.MagicMock()

        self.assertTrue(controller.start_brawl_stars_app())
        controller.device.app_start.assert_called_once_with("com.supercell.brawlstars")


if __name__ == "__main__":
    unittest.main()
