"""Kiểm thử radar riêng bằng UART giả/widget ẩn; không dùng mạch hay data thật."""
from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from collections import deque
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from Python import measure_doa as doa
from Python import visualize_doa as visual


class FakeSerial:
    def __init__(self, events):
        self.events = deque(events)
        self.closed, self.reset = False, False
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True

    def reset_input_buffer(self):
        self.reset = True

    @property
    def in_waiting(self):
        if not self.events:
            return 0
        event = self.events[0]
        return 1 if isinstance(event, BaseException) else len(event)

    def read(self, size):
        self.read_sizes.append(size)
        event = self.events.popleft() if self.events else b""
        if isinstance(event, BaseException):
            raise event
        if len(event) > size:
            self.events.appendleft(event[size:])
        return event[:size]


class FakeViewer:
    def __init__(self, close_after):
        self.close_after, self.pumps = close_after, 0
        self.closed, self.frames = False, []
        self.connected, self.message, self.settings = False, "", None
        self.log, self.frame_count = [], 0

    def pump(self):
        self.pumps += 1
        return self.pumps <= self.close_after

    def update_frame(self, frame):
        self.frames.append(frame)

    def receive_frames(self, frames):
        self.frame_count += len(frames)
        self.update_frame(frames[-1])

    def add_log(self, message):
        self.log.append(message)

    def close(self):
        self.closed = True

    def set_connected(self, connected):
        self.connected = connected

    def clear_frame(self, message):
        self.message = message

    def set_status(self, message):
        self.message = message

    def set_settings(self, settings):
        self.settings = settings


class VisualizerTests(unittest.TestCase):
    def setUp(self):
        self.settings = visual.Settings(settle_seconds=0)

    def run_events(self, events, close_after=None):
        uart = FakeSerial(events)
        viewer = FakeViewer(len(events) if close_after is None else close_after)
        output = io.StringIO()
        with redirect_stdout(output):
            status = visual.run_visualizer(self.settings,
                serial_factory=lambda *a, **k: uart, viewer_factory=lambda _: viewer,
                sleep=lambda _: None)
        self.assertTrue(uart.closed)
        self.assertTrue(uart.reset)
        self.assertTrue(viewer.closed)
        return status, viewer, output.getvalue()

    def test_cardinal_orientation_preserves_raw_angles(self):
        expected = {0: (90, 100), 90: (100, 110), 180: (110, 100), 270: (100, 90)}
        for angle, (x, y) in expected.items():
            px, py = visual.radar_point(angle, 100, 100, 10)
            self.assertAlmostEqual(px, x)
            self.assertAlmostEqual(py, y)

    def test_only_latest_frame_of_each_batch_is_drawn(self):
        status, viewer, _ = self.run_events([b"DOA,1,90\nDOA,3,0,180,270\n", b"DOA,0\n"])
        self.assertEqual(status, "closed")
        self.assertEqual(viewer.frames, [doa.Frame((0, 180, 270)), doa.Frame(())])

    def test_split_frame_and_invalid_line_do_not_fake_empty_frame(self):
        _, viewer, _ = self.run_events([b"DOA,1,9", b"0\r\nDOA,1,999\n"])
        self.assertEqual(viewer.frames, [doa.Frame((90,))])

    def test_eval_is_ignored_and_warned_once(self):
        _, viewer, output = self.run_events([b"EVAL,0\n", b"EVAL,0\nDOA,1,270\n"])
        self.assertEqual(viewer.frames, [doa.Frame((270,))])
        self.assertEqual(output.count("Đang nhận EVAL"), 1)

    def test_empty_uart_can_be_closed_without_capture_timeout(self):
        status, viewer, _ = self.run_events([b""] * 5)
        self.assertEqual(status, "closed")
        self.assertEqual(viewer.frames, [])

    def test_visualizer_never_creates_files_or_calls_measurement(self):
        with patch("builtins.open", side_effect=AssertionError("No file writes")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("No folders")), \
             patch.object(doa, "open_new_csv", side_effect=AssertionError("No CSV")), \
             patch.object(doa, "analyze", side_effect=AssertionError("No reports")):
            status, _, _ = self.run_events([b"DOA,1,90\n", b"DOA,0\n"])
        self.assertEqual(status, "closed")

    def test_interrupt_and_uart_error_release_both_resources(self):
        for event, expected in ((KeyboardInterrupt(), "interrupted"), (OSError("lost"), "serial_error")):
            with self.subTest(expected=expected):
                status, _, _ = self.run_events([event])
                self.assertEqual(status, expected)

    def test_gui_startup_error_does_not_open_uart(self):
        calls = []
        def fail(_):
            raise RuntimeError("No Tk")
        with self.assertRaisesRegex(RuntimeError, "No Tk"):
            visual.run_visualizer(self.settings, serial_factory=lambda *a, **k: calls.append(a),
                                  viewer_factory=fail, sleep=lambda _: None)
        self.assertEqual(calls, [])

    def test_failed_port_keeps_window_available_for_changing_config(self):
        def fail(*args, **kwargs):
            raise OSError("Port busy")
        viewer = FakeViewer(3)
        with redirect_stdout(io.StringIO()):
            status = visual.run_visualizer(self.settings, serial_factory=fail,
                viewer_factory=lambda _: viewer, sleep=lambda _: None)
        self.assertEqual(status, "serial_error")
        self.assertEqual(viewer.pumps, 4)
        self.assertTrue(viewer.closed)

    def test_invalid_config_is_rejected_before_opening_uart(self):
        for change in ({"port": ""}, {"baud": 0}, {"baud": True}, {"mode": "other"},
                       {"stale_seconds": 0}, {"stale_seconds": float("nan")},
                       {"settle_seconds": -1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.settings, **change).validate()

    def test_direct_file_import_for_ide_run_needs_no_uart(self):
        path = Path(visual.__file__).resolve()
        code = ("import runpy, sys; "
                f"sys.path.insert(0, {str(path.parent)!r}); "
                f"module = runpy.run_path({str(path)!r}, run_name='smoke_test'); "
                "assert callable(module['main'])")
        result = subprocess.run([sys.executable, "-B", "-c", code],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))


class ExecutableSettingsTests(unittest.TestCase):
    def test_ini_overrides_settings_without_editing_python(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "visualize_doa.ini"
            path.write_text("[radar]\nport=COM7\nbaud=115200\nmode=no_ai\nstale_seconds=2.5\n",
                            encoding="utf-8-sig")
            settings = visual.load_settings(path)
        self.assertEqual((settings.port, settings.baud, settings.mode, settings.stale_seconds),
                         ("COM7", 115200, "no_ai", 2.5))

    def test_frozen_ini_is_loaded_beside_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "visualize_doa.exe"
            exe.with_suffix(".ini").write_text("[radar]\nport=COM7\n", encoding="utf-8")
            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", str(exe)):
                self.assertEqual(visual.load_settings().port, "COM7")

    def test_missing_ini_uses_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(visual.load_settings(Path(folder) / "missing.ini"), visual.Settings())

    def test_invalid_ini_is_reported(self):
        for content in ("not an ini file", "[other]\nport=COM7\n", "[radar]\nbaud=fast\n",
                        "[radar]\nbaud=0\n", "[radar]\nmode=unknown\n",
                        "[radar]\nport=\n", "[radar]\nstale_seconds=nan\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "visualize_doa.ini"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    visual.load_settings(path)

    def test_executable_error_is_visible_without_a_console(self):
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "argv", ["visualize_doa.exe"]), \
             patch("tkinter.messagebox.showerror") as dialog, redirect_stdout(io.StringIO()):
            visual.report_error("Cổng COM đang được sử dụng")
        dialog.assert_called_once_with("Radar DOA", "Cổng COM đang được sử dụng")

    def test_saved_configuration_is_loaded_on_next_launch(self):
        settings = visual.Settings(port="COM8", baud=115200, mode="no_ai", stale_seconds=2.5)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "visualize_doa.ini"
            visual.save_settings(settings, path)
            self.assertEqual(visual.load_settings(path), settings)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_failed_save_preserves_previous_config_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "visualize_doa.ini"
            visual.save_settings(visual.Settings(), path)
            previous = path.read_bytes()
            with patch.object(Path, "replace", side_effect=OSError("read only")):
                with self.assertRaises(OSError):
                    visual.save_settings(visual.Settings(port="COM8"), path)
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(list(Path(folder).iterdir()), [path])


class RadarAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "visualize_doa.ini"
        self.settings = visual.Settings(settle_seconds=0)
        self.viewer = FakeViewer(3)
        self.uarts, self.calls = [], []
        self.now = 10.0
        self.events = [b"DOA,1,90\n"]
        self.error = None
        def factory(port, baud, **kwargs):
            self.calls.append((port, baud, kwargs))
            if self.uarts:
                self.assertTrue(self.uarts[-1].closed)
            if self.error:
                raise self.error
            uart = FakeSerial(self.events)
            self.uarts.append(uart)
            return uart
        self.app = visual.RadarApp(self.settings, serial_factory=factory,
            viewer_factory=lambda _: self.viewer, clock=lambda: self.now,
            sleep=lambda _: None, config_path=self.path)
        self.addCleanup(self.app.disconnect)

    def connect(self, settings=None, persist=False):
        with redirect_stdout(io.StringIO()):
            return self.app.connect(settings or self.settings, persist=persist)

    def test_apply_saves_and_reopens_with_new_port_baud_and_mode(self):
        self.connect()
        self.app.poll()
        self.app.parser.feed(b"DOA,1,2")
        changed = replace(self.settings, port="COM8", baud=115200, mode="no_ai", stale_seconds=2.5)
        with redirect_stdout(io.StringIO()):
            self.viewer.on_apply(changed)
        self.assertEqual([call[:2] for call in self.calls], [(self.settings.port, self.settings.baud), ("COM8", 115200)])
        self.assertEqual(visual.load_settings(self.path), replace(changed, settle_seconds=1.0))
        self.assertEqual(self.viewer.settings, changed)
        self.assertEqual(self.app.parser.buffer, bytearray())
        self.assertTrue(self.viewer.connected)
        self.assertTrue(self.uarts[0].closed)
        self.assertFalse(self.uarts[1].closed)
        self.app.poll()
        self.assertTrue(self.uarts[1].reset)
        self.assertEqual(self.viewer.frames[-1], doa.Frame((90,)))

    def test_disconnect_releases_com_and_can_connect_again(self):
        self.connect()
        self.viewer.on_disconnect()
        self.assertIsNone(self.app.uart)
        self.assertTrue(self.uarts[0].closed)
        self.assertFalse(self.viewer.connected)
        self.assertFalse(self.viewer.closed)
        self.assertTrue(self.connect())

    def test_invalid_input_keeps_existing_connection_and_config(self):
        self.connect(persist=True)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.app.connect(replace(self.settings, baud=0), persist=True)
        self.assertFalse(self.uarts[0].closed)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(self.calls), 1)

    def test_save_error_keeps_existing_connection(self):
        self.connect()
        with patch.object(visual, "save_settings", side_effect=OSError("read only")):
            with self.assertRaises(OSError):
                self.app.connect(replace(self.settings, port="COM8"), persist=True)
        self.assertFalse(self.uarts[0].closed)
        self.assertEqual(len(self.calls), 1)

    def test_unavailable_port_can_be_corrected_without_restarting(self):
        self.error = OSError("Port unavailable")
        self.assertFalse(self.connect())
        self.assertFalse(self.viewer.closed)
        self.assertFalse(self.viewer.connected)
        self.assertIn("Chọn lại COM", self.viewer.message)
        self.error = None
        self.assertTrue(self.connect(replace(self.settings, port="COM8")))
        self.assertEqual(self.app.status, "closed")

    def test_uart_read_or_reset_error_keeps_app_open_and_allows_retry(self):
        for reset_error in (False, True):
            with self.subTest(reset_error=reset_error):
                self.events = [OSError("lost")]
                self.connect()
                uart = self.uarts[-1]
                if reset_error:
                    uart.reset_input_buffer = lambda: (_ for _ in ()).throw(OSError("lost"))
                with redirect_stdout(io.StringIO()):
                    self.app.poll()
                self.assertTrue(uart.closed)
                self.assertIsNone(self.app.uart)
                self.assertFalse(self.viewer.closed)
                self.assertIn("Mất kết nối", self.viewer.message)
                self.events = [b"DOA,1,270\n"]
                self.assertTrue(self.connect())
                self.app.poll()
                self.assertEqual(self.viewer.frames[-1], doa.Frame((270,)))

    def test_settle_wait_keeps_gui_responsive_without_sleeping(self):
        self.connect(replace(self.settings, settle_seconds=1.0))
        self.app.poll()
        self.assertFalse(self.uarts[-1].reset)
        self.assertEqual(self.viewer.frames, [])
        self.now += 1
        self.app.poll()
        self.assertTrue(self.uarts[-1].reset)
        self.assertEqual(self.viewer.frames, [doa.Frame((90,))])

    def test_uart_reads_are_nonblocking_and_skip_empty_buffer(self):
        self.events = []
        self.connect()
        self.assertEqual(self.calls[-1][2]["timeout"], 0)
        self.app.poll()
        self.assertEqual(self.uarts[-1].read_sizes, [])
        self.assertEqual(self.viewer.frame_count, 0)

    def test_burst_larger_than_old_read_size_displays_latest_frame_in_one_poll(self):
        self.events = [b"DOA,1,0\n" * 5000 + b"DOA,1,270\n"]
        self.connect()
        self.app.poll()
        self.assertEqual(self.viewer.frame_count, 5001)
        self.assertEqual(self.viewer.frames, [doa.Frame((270,))])
        self.assertEqual(self.uarts[-1].in_waiting, 0)

    def test_read_budget_keeps_partial_line_and_drains_remainder_next_poll(self):
        self.events = [b"DOA,1,10\n" * 10000 + b"DOA,1,270\n"]
        self.connect()
        self.app.poll()
        self.assertEqual(self.uarts[-1].read_sizes, [visual.MAX_READ_BYTES])
        self.assertTrue(self.app.parser.buffer)
        self.assertGreater(self.uarts[-1].in_waiting, 0)
        self.app.poll()
        self.assertEqual(self.viewer.frame_count, 10001)
        self.assertEqual(self.viewer.frames[-1], doa.Frame((270,)))
        self.assertEqual(self.uarts[-1].in_waiting, 0)

    def test_invalid_doa_is_logged_without_becoming_a_frame(self):
        self.events = [b"DOA,1,999\nDOA,1,90\n"]
        self.connect()
        self.app.poll()
        self.assertEqual(self.viewer.frame_count, 1)
        self.assertIn("Bỏ 1 dòng DOA không hợp lệ.", self.viewer.log)


class RadarWidgetTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        try:
            self.viewer = visual.LiveRadar(visual.Settings(), hidden=True, clock=lambda: self.now)
        except RuntimeError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.viewer.close)
        self.viewer.root.update_idletasks()

    def draw(self, frame):
        self.viewer.update_frame(frame)
        self.viewer._redraw()

    def test_three_sources_and_zero_frame_clear_needles(self):
        self.draw(doa.Frame((0, 90, 270)))
        self.assertEqual(len(self.viewer.canvas.find_withtag("prediction")), 6)
        self.draw(doa.Frame(()))
        self.assertEqual(len(self.viewer.canvas.find_withtag("prediction")), 0)
        self.assertIn("DOA,0", self.viewer.angles_text.get())

    def test_no_record_button_or_ground_truth_lines(self):
        self.viewer._redraw()
        self.assertFalse(hasattr(self.viewer, "start_button"))
        self.assertFalse(hasattr(self.viewer, "begin_recording"))
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        buttons = [child.cget("text") for child in descendants(self.viewer.root)
                   if child.winfo_class() == "Button"]
        self.assertEqual(buttons, ["Đóng"])
        self.assertEqual(len(self.viewer.canvas.find_withtag("truth")), 0)

    def test_configuration_controls_apply_all_values(self):
        self.viewer.port_var.set(" COM8 ")
        self.viewer.baud_var.set("115200")
        self.viewer.mode_var.set("NOAI")
        self.viewer.stale_var.set("2,5")
        applied = []
        self.viewer.on_apply = applied.append
        self.viewer.apply_button.invoke()
        self.assertEqual(applied, [visual.Settings(port="COM8", baud=115200,
                                                   mode="no_ai", stale_seconds=2.5)])

    def test_bad_input_shows_error_and_does_not_apply(self):
        self.viewer.baud_var.set("fast")
        applied = []
        self.viewer.on_apply = applied.append
        with patch("tkinter.messagebox.showerror") as dialog:
            self.viewer.apply_button.invoke()
        self.assertEqual(applied, [])
        dialog.assert_called_once()

    def test_refresh_ports_keeps_manual_selection(self):
        self.viewer.port_var.set("COM8")
        self.viewer.port_lister = lambda: ["COM13", "COM2", "COM13"]
        self.viewer.refresh_ports()
        self.assertEqual(self.viewer.port_combo.cget("values"), ("COM2", "COM13"))
        self.assertEqual(self.viewer.port_var.get(), "COM8")

    def test_reconnect_clears_previous_needles_and_updates_labels(self):
        self.draw(doa.Frame((90,)))
        self.viewer.set_settings(visual.Settings(port="COM8", baud=115200, mode="no_ai"))
        self.viewer.clear_frame("Đã đổi kết nối")
        self.viewer.set_connected(True)
        self.viewer._redraw()
        self.assertIsNone(self.viewer.last_frame)
        self.assertEqual(len(self.viewer.canvas.find_withtag("prediction")), 0)
        self.assertEqual(self.viewer.title_text.get(), "Direction of Arrival · NOAI")
        self.assertIn("COM8", self.viewer.connection_text.get())
        self.assertEqual(str(self.viewer.disconnect_button.cget("state")), "normal")
        self.viewer.set_connected(False)
        self.assertEqual(str(self.viewer.disconnect_button.cget("state")), "disabled")

    def test_stale_frame_clears_needles_then_new_frame_recovers(self):
        self.draw(doa.Frame((90,)))
        self.now += 2
        self.viewer.pump()
        self.assertIsNone(self.viewer.last_frame)
        self.assertEqual(len(self.viewer.canvas.find_withtag("prediction")), 0)
        self.draw(doa.Frame((270,)))
        self.assertIn("270°", self.viewer.angles_text.get())
        self.assertEqual(len(self.viewer.canvas.find_withtag("prediction")), 2)

    def test_close_is_idempotent(self):
        self.viewer.close()
        self.viewer.close()
        self.assertFalse(self.viewer.pump())

    def test_log_shows_all_received_angles_including_zero_source_frames(self):
        self.viewer.clear_log()
        self.viewer.receive_frames([doa.Frame((90,)), doa.Frame(()), doa.Frame((0, 180, 270))])
        self.viewer.pump()
        log = self.viewer.log_text.get("1.0", "end")
        self.assertIn("#000001 | DOA,1,90", log)
        self.assertIn("#000002 | DOA,0", log)
        self.assertIn("#000003 | DOA,3,0,180,270", log)
        self.assertEqual(self.viewer.total_frames, 3)
        self.assertEqual(self.viewer.last_frame, doa.Frame((0, 180, 270)))
        self.assertEqual(str(self.viewer.log_text.cget("state")), "disabled")

    def test_log_buffer_and_widget_keep_only_recent_lines(self):
        self.viewer.clear_log()
        for i in range(visual.MAX_LOG_LINES + 300):
            self.viewer.add_log(f"event {i}")
        self.assertEqual(len(self.viewer._pending_log), visual.MAX_LOG_LINES)
        self.viewer.pump()
        text = self.viewer.log_text.get("1.0", "end-1c")
        self.assertEqual(len(text.splitlines()), visual.MAX_LOG_LINES)
        self.assertNotIn("event 299\n", text)
        self.assertIn("event 1299\n", text)
        self.now += visual.LOG_INTERVAL + 0.01
        for i in range(1300, 1600):
            self.viewer.add_log(f"event {i}")
        self.viewer.pump()
        text = self.viewer.log_text.get("1.0", "end-1c")
        self.assertEqual(len(text.splitlines()), visual.MAX_LOG_LINES)
        self.assertNotIn("event 599\n", text)
        self.assertIn("event 1599\n", text)
        self.viewer.clear_log()
        self.assertEqual(self.viewer.log_text.get("1.0", "end-1c"), "")

    def test_log_can_stop_auto_scrolling_without_stopping_receive(self):
        self.viewer.auto_scroll.set(False)
        self.viewer.receive_frames([doa.Frame((90,))])
        with patch.object(self.viewer.log_text, "see") as scroll:
            self.viewer.pump()
        scroll.assert_not_called()
        self.assertEqual(self.viewer.total_frames, 1)

    def test_fast_burst_counts_all_frames_and_bounds_pending_log(self):
        frames = [doa.Frame((0,))] * 5000 + [doa.Frame((270,))]
        self.viewer.receive_frames(frames)
        self.assertEqual(self.viewer.total_frames, 5001)
        self.assertEqual(len(self.viewer._pending_log), visual.MAX_LOG_LINES)
        self.assertIn("#005001 | DOA,1,270", self.viewer._pending_log[-1])
        self.now += 0.5
        self.viewer.pump()
        self.assertIn("5001 frame", self.viewer.metrics_text.get())
        self.assertIn("10002.0 frame/s", self.viewer.metrics_text.get())

    def test_radar_reuses_grid_and_needles_when_angles_change(self):
        self.draw(doa.Frame((90,)))
        grid = self.viewer.canvas.find_withtag("grid")
        needles = self.viewer.canvas.find_withtag("prediction")
        for angle in range(0, 360, 10):
            self.draw(doa.Frame((angle,)))
        self.assertEqual(self.viewer.canvas.find_withtag("grid"), grid)
        self.assertEqual(self.viewer.canvas.find_withtag("prediction"), needles)
        self.assertEqual(len(self.viewer.canvas.find_all()), len(grid) + 2)

    def test_radar_draws_new_frame_before_old_50ms_limit(self):
        self.viewer.update_frame(doa.Frame((0,)))
        self.viewer.pump()
        self.now += 0.02
        self.viewer.update_frame(doa.Frame((90,)))
        self.viewer.pump()
        self.assertIn("90°", self.viewer.angles_text.get())
        self.assertFalse(self.viewer._dirty)

    def test_same_angles_refresh_timestamp_without_redrawing(self):
        self.draw(doa.Frame((90,)))
        self.now += 0.1
        self.viewer.update_frame(doa.Frame((90,)))
        self.assertFalse(self.viewer._dirty)
        self.assertEqual(self.viewer.last_rx, self.now)


if __name__ == "__main__":
    unittest.main()
