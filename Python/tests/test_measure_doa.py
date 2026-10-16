"""Kiểm thử UART/CSV AI3 và nhập terminal; dùng dữ liệu giả, không cần mạch."""
from __future__ import annotations
import csv
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from Python import measure_doa as doa


class FakeSerial:
    def __init__(self, events):
        self.events, self.closed, self.reset = iter(events), False, False
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.closed = True
    def reset_input_buffer(self):
        self.reset = True
    def read(self, size):
        event = next(self.events, b"")
        if isinstance(event, BaseException):
            raise event
        return event


class FakeClock:
    def __init__(self, step=0.01):
        self.value, self.step = 0.0, step
    def __call__(self):
        self.value += self.step
        return self.value


class ProtocolAndMetricTests(unittest.TestCase):
    def test_doa_zero_and_three(self):
        self.assertEqual(doa.parse_line("DOA,0"), doa.Frame(()))
        self.assertEqual(doa.parse_line("DOA,3,0,90,359"), doa.Frame((0, 90, 359)))

    def test_invalid_lines_and_eval_are_not_frames(self):
        for line in ("DOA,4,0,1,2,3", "DOA,1", "DOA,0,0", "DOA,1,-1",
                     "DOA,1,360", "DOA,x", "EVAL,0", "Boot", "DOA,1,0.5"):
            with self.subTest(line=line):
                self.assertIsNone(doa.parse_line(line))

    def test_fragments_banners_and_invalid_line(self):
        parser = doa.StreamParser()
        self.assertEqual(parser.feed(b"Boot\r\nDOA,1,9"), [])
        self.assertEqual(parser.feed(b"0\r\nDOA,0\nDOA,1,999\n"),
                         [doa.Frame((90,)), doa.Frame(())])
        self.assertEqual(parser.invalid_lines, 1)

    def test_wrong_protocol_is_counted_but_not_accepted(self):
        parser = doa.StreamParser()
        self.assertEqual(parser.feed(b"EVAL,0\nDOA,0\n"), [doa.Frame(())])
        self.assertEqual(parser.wrong_protocol_lines, 1)

    def test_oversize_buffer_recovers(self):
        parser = doa.StreamParser()
        parser.feed(b"x" * 5000)
        self.assertEqual(parser.feed(b"tail\nDOA,0\n"), [doa.Frame(())])

    def test_circular_wrap(self):
        self.assertEqual(doa.circular_error(350, 0), 10)
        self.assertEqual(doa.circular_error(1, 359), 2)

    def test_optimal_matching_not_greedy(self):
        pairs = doa.match_sources((0, 20), (10, 350), 15)
        self.assertEqual({(t, d) for t, d, _ in pairs}, {(0, 1), (1, 0)})

    def test_missing_frame_is_false_negative(self):
        stats = doa.Stats()
        stats.add_frame((0, 90), (0, 90), 15)
        stats.add_frame((0, 90), (), 15)
        self.assertEqual((stats.tp, stats.fp, stats.fn), (2, 0, 2))
        self.assertEqual(stats.metrics()["recall"], 0.5)

    def test_extra_prediction_is_false_positive(self):
        stats = doa.Stats()
        stats.add_frame((0,), (0, 90), 15)
        self.assertEqual((stats.tp, stats.fp, stats.fn), (1, 1, 0))

    def test_correct_count_is_not_recall(self):
        stats = doa.Stats()
        stats.add_frame((0,), (180,), 15)
        self.assertEqual(stats.metrics()["count_accuracy"], 1)
        self.assertEqual(stats.metrics()["recall"], 0)
        self.assertIsNone(stats.metrics()["matched_mae_deg"])

    def test_noise_recall_undefined(self):
        stats = doa.Stats()
        stats.add_frame((), (), 15)
        stats.add_frame((), (90,), 15)
        self.assertIsNone(stats.metrics()["recall"])
        self.assertEqual(stats.metrics()["noise_fp_rate"], 0.5)

    def test_ai3_header_exact(self):
        self.assertEqual(doa.csv_fields(2),
                         ["sample", "distance_cm", "detected_count", "raw_angles",
                          "true_angle_1", "true_angle_2", "detected_angle_1",
                          "detected_angle_2", "error_1", "error_2", "mean_error"])

    def test_csv_pairing_and_cm_exact_ai3(self):
        row = doa.csv_row(1, (0, 90), 0.2, (91, 359))
        self.assertEqual(row, [1, 20.0, 2, "91;359", 0, 90, 359, 91, 1, 1, "1.00"])

    def test_csv_errors_remain_blank_when_missing_or_extra(self):
        for detected in ((), (0,), (0, 90, 180)):
            row = doa.csv_row(1, (0, 90), 0.1, detected)
            self.assertEqual(row[6:], ["", "", "", "", ""])

    def test_csv_error_not_clipped_by_recall_threshold(self):
        row = doa.csv_row(1, (0,), 0.1, (180,))
        self.assertEqual(row[-2:], [180, "180.00"])


class CollectionAndInputTests(unittest.TestCase):
    def setUp(self):
        # Kiểm tra mốc 65% độc lập với cấu hình đo mà người dùng đang chỉnh.
        retry_defaults = patch.multiple(doa, TARGET_RECALL=0.65, MAX_EXTRA_MEASUREMENTS=3)
        retry_defaults.start()
        self.addCleanup(retry_defaults.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = doa.Settings(output_root=self.root / "data",
            report_root=self.root / "data" / "_reports",
            analyze_folders=(self.root / "data",),
            mode="no_ai", frames=3, discard=0, timeout=1, settle_seconds=0)

    def collect(self, events, settings=None, clock=None):
        uart = FakeSerial(events)
        with redirect_stdout(io.StringIO()):
            result = doa.collect(settings or self.settings,
                serial_factory=lambda *a, **k: uart, clock=clock or FakeClock(),
                sleep=lambda _: None)
        self.assertTrue(uart.closed)
        self.assertTrue(uart.reset)
        return result

    def prompt(self, answers):
        answers = iter(answers)
        with redirect_stdout(io.StringIO()):
            return doa.prompt_measurement(self.settings, lambda _: next(answers))

    def test_terminal_single_source_and_meters(self):
        settings = self.prompt(["359", "0.2"])
        self.assertEqual(settings.true_angles, (359,))
        self.assertEqual(settings.distance, 0.2)

    def test_terminal_multi_source_sorted(self):
        settings = self.prompt(["180;0;90", "0.3"])
        self.assertEqual(settings.true_angles, (0, 90, 180))

    def test_terminal_accepts_comma_separator_and_decimal_comma(self):
        settings = self.prompt(["0,90", "0,2"])
        self.assertEqual((settings.true_angles, settings.distance), ((0, 90), 0.2))

    def test_terminal_invalid_angles_retry(self):
        settings = self.prompt(["360", "-1", "0;0", "0;90;180;270", "", "90;", "90", "0.1"])
        self.assertEqual(settings.true_angles, (90,))

    def test_terminal_invalid_distance_retry(self):
        settings = self.prompt(["0", "nan", "inf", "-0.1", "0", "abc", "0.3"])
        self.assertEqual(settings.distance, 0.3)

    def test_terminal_default_distance_and_quit(self):
        self.assertEqual(self.prompt(["0", ""]).distance, 0.1)
        self.assertIsNone(self.prompt(["q"]))
        self.assertIsNone(self.prompt(["0", "q"]))

    def test_terminal_eof_does_not_create_file(self):
        def eof(_):
            raise EOFError()
        self.assertIsNone(doa.prompt_measurement(self.settings, eof))
        self.assertFalse(self.settings.output_root.exists())

    def test_direct_run_with_legacy_windows_encoding_can_quit(self):
        result = subprocess.run([sys.executable, "-B", str(Path(doa.__file__))],
            input=b"q\n", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"}, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertIn("Góc thật", result.stdout.decode("utf-8"))

    def test_terminal_noise(self):
        self.assertEqual(self.prompt(["noise", "0.1"]).true_angles, ())

    def test_repeated_session_two_prompts_no_restart(self):
        answers = iter(["0", "0.2", "90", "", "q"])
        measured = []
        def collector(settings):
            measured.append(settings)
            return doa.CollectionResult(Path("fake.csv"), doa.Stats(frames=3, tp=3), "complete")
        with redirect_stdout(io.StringIO()):
            code = doa.measure_session(self.settings, lambda _: next(answers), collector)
        self.assertEqual(code, 0)
        self.assertEqual([s.true_angles for s in measured], [(0,), (90,)])
        self.assertEqual([s.distance for s in measured], [0.2, 0.2])

    def test_session_retries_until_a_run_reaches_65_percent_or_three_extras(self):
        cases = (
            ("first_at_threshold", (65,), 1),
            ("first_above_threshold", (90,), 1),
            ("first_extra_passes", (0, 65), 2),
            ("second_extra_passes", (20, 40, 70), 3),
            ("third_extra_passes", (20, 40, 60, 65), 4),
            ("all_below_threshold", (0, 30, 50, 64), 4),
        )
        for name, recalls, expected_runs in cases:
            with self.subTest(name=name):
                settings = replace(self.settings, frames=100,
                                   output_root=self.root / name / "data")
                answers = iter(["90", "0.2", "q"])
                recalls = iter(recalls)
                results, measured = [], []
                def collector(current):
                    measured.append(current)
                    correct = next(recalls)
                    events = [b"DOA,1,90\n" * correct + b"DOA,1,270\n" * (100 - correct)]
                    result = self.collect(events, current)
                    results.append(result)
                    return result
                with redirect_stdout(io.StringIO()):
                    code = doa.measure_session(settings, lambda _: next(answers), collector)
                self.assertEqual(code, 0)
                self.assertEqual(len(results), expected_runs)
                self.assertTrue(all(s == measured[0] for s in measured))
                self.assertEqual((measured[0].true_angles, measured[0].distance), ((90,), 0.2))
                self.assertEqual([r.path.name for r in results],
                                 [f"{i:02d}_90dis02.csv" for i in range(1, expected_runs + 1)])
                for result in results:
                    _, stored_stats = doa.score_csv(result.path, settings)
                    self.assertEqual(stored_stats.frames, 100)
                    self.assertEqual(stored_stats.metrics(), result.stats.metrics())

    def test_session_does_not_round_recall_up_to_threshold(self):
        answers = iter(["0", "0.1", "q"])
        stats = iter((doa.Stats(frames=2000, tp=1299, fn=701),
                      doa.Stats(frames=2000, tp=1300, fn=700)))
        measured = []
        def collector(current):
            measured.append(current)
            return doa.CollectionResult(Path("fake.csv"), next(stats), "complete")
        with redirect_stdout(io.StringIO()):
            code = doa.measure_session(self.settings, lambda _: next(answers), collector)
        self.assertEqual(code, 0)
        self.assertEqual(len(measured), 2)

    def test_session_uses_nonempty_recall_even_when_raw_recall_is_low(self):
        answers = iter(["0", "0.1", "q"])
        settings = replace(self.settings, frames=100)
        results = []
        def collector(current):
            result = self.collect([b"DOA,1,0\n" * 10 + b"DOA,0\n" * 90], current)
            results.append(result)
            return result
        messages = io.StringIO()
        with redirect_stdout(messages):
            code = doa.measure_session(settings, lambda _: next(answers), collector)
        self.assertEqual(code, 0)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].stats.metrics()["recall"], 0.1)
        self.assertEqual(results[0].display_stats.metrics()["recall"], 1)
        self.assertIn("Recall (bỏ frame rỗng)=100.00%", messages.getvalue())

    def test_session_all_empty_source_retries_without_claiming_perfect_recall(self):
        answers = iter(["0", "0.1", "q"])
        results = []
        def collector(current):
            result = self.collect([b"DOA,0\n" * 3], current)
            results.append(result)
            return result
        messages = io.StringIO()
        with redirect_stdout(messages):
            code = doa.measure_session(self.settings, lambda _: next(answers), collector)
        self.assertEqual(code, 0)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r.display_stats.frames == 0 for r in results))
        self.assertTrue(all(r.display_stats.metrics()["recall"] is None for r in results))
        self.assertIn("Recall=N/A vì chưa có frame có góc", messages.getvalue())
        self.assertNotIn("đạt ngưỡng", messages.getvalue())

    def test_session_noise_does_not_retry_undefined_recall(self):
        answers = iter(["noise", "0.1", "q"])
        results = []
        def collector(current):
            result = self.collect([b"DOA,0\nDOA,1,90\nDOA,0\n"], current)
            results.append(result)
            return result
        with redirect_stdout(io.StringIO()):
            code = doa.measure_session(self.settings, lambda _: next(answers), collector)
        self.assertEqual(code, 0)
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].stats.metrics()["recall"])

    def test_session_new_angles_have_their_own_retry_budget(self):
        answers = iter(["0", "0.2", "90", "", "q"])
        measured = []
        def collector(current):
            measured.append(current)
            return doa.CollectionResult(Path("fake.csv"), doa.Stats(frames=3, fn=3), "complete")
        with redirect_stdout(io.StringIO()):
            code = doa.measure_session(self.settings, lambda _: next(answers), collector)
        self.assertEqual(code, 0)
        self.assertEqual([s.true_angles for s in measured], [(0,)] * 4 + [(90,)] * 4)
        self.assertEqual([s.distance for s in measured], [0.2] * 8)

    def test_session_incomplete_extra_measurement_stops_and_keeps_all_csvs(self):
        for event, expected_status in ((None, "timeout"),
                                       (KeyboardInterrupt(), "interrupted"),
                                       (OSError("lost"), "serial_error")):
            with self.subTest(status=expected_status):
                settings = replace(self.settings,
                                   output_root=self.root / expected_status / "data")
                answers = iter(["0", "0.1"])
                events = iter(([b"DOA,0\n" * 3],
                               [b"DOA,0\n"] + ([] if event is None else [event])))
                results = []
                def collector(current):
                    result = self.collect(next(events), current, clock=FakeClock(0.1))
                    results.append(result)
                    return result
                with redirect_stdout(io.StringIO()):
                    code = doa.measure_session(settings, lambda _: next(answers), collector)
                self.assertEqual(code, 1)
                self.assertEqual([r.status for r in results], ["complete", expected_status])
                self.assertEqual([r.path.name for r in results], ["01_00dis01.csv", "02_00dis01.csv"])
                self.assertEqual([doa.score_csv(r.path, settings)[1].frames for r in results], [3, 1])

    def test_doa_all_frames_and_round_trip(self):
        result = self.collect([b"DOA,1,0\nDOA,0\nDOA,2,0,90\n"])
        self.assertEqual(result.status, "complete")
        self.assertEqual((result.stats.tp, result.stats.fp, result.stats.fn), (2, 1, 1))
        self.assertEqual(result.path.name, "01_00dis01.csv")
        self.assertEqual(result.path.parent.name, "0.1m")
        self.assertEqual(result.path.parent.parent.name, "1sourceNOAI")
        with result.path.open(newline="", encoding="utf-8") as h:
            reader = csv.DictReader(h)
            self.assertEqual(reader.fieldnames, doa.csv_fields(1))
            rows = list(reader)
        self.assertEqual(rows[1]["raw_angles"], "")
        self.assertEqual(rows[1]["detected_count"], "0")
        metadata, stats = doa.score_csv(result.path, self.settings)
        self.assertEqual(stats.metrics(), result.stats.metrics())
        self.assertEqual(metadata["mode"], "no_ai")

    def test_post_measurement_summary_excludes_only_empty_frames(self):
        for mode in ("ai", "no_ai"):
            with self.subTest(mode=mode):
                uart = FakeSerial([b"DOA,1,359\nDOA,0\nDOA,1,180\n"])
                messages = io.StringIO()
                settings = replace(self.settings, mode=mode)
                with redirect_stdout(messages):
                    result = doa.collect(settings, serial_factory=lambda *a, **k: uart,
                                         clock=FakeClock(), sleep=lambda _: None)
                self.assertEqual(result.stats.metrics()["recall"], 1 / 3)
                self.assertEqual(result.display_stats.metrics()["recall"], 0.5)
                self.assertEqual(result.display_stats.metrics()["f1"], 0.5)
                self.assertIn("Recall (bỏ frame rỗng)=50.00%", messages.getvalue())
                self.assertIn("Có góc=2", messages.getvalue())
                self.assertIn("Frame rỗng bỏ khỏi chỉ số=1", messages.getvalue())
                _, stored = doa.score_csv(result.path, settings)
                self.assertEqual(stored.metrics(), result.stats.metrics())
                self.assertEqual(stored.frames, 3)

    def test_nonempty_multi_source_frame_still_counts_missing_source(self):
        settings = replace(self.settings, true_angles=(0, 90))
        result = self.collect([b"DOA,2,0,90\nDOA,0\nDOA,1,0\n"], settings)
        self.assertEqual(result.stats.metrics()["recall"], 0.5)
        self.assertEqual((result.display_stats.frames, result.display_stats.tp,
                          result.display_stats.fp, result.display_stats.fn), (2, 3, 0, 1))
        self.assertEqual(result.display_stats.metrics()["recall"], 0.75)
        _, stored = doa.score_csv(result.path, settings)
        self.assertEqual(stored.frames, 3)
        self.assertEqual(stored.fn, 3)

    def test_ai_folder_and_no_hidden_mirror(self):
        settings = replace(self.settings, mode="ai", true_angles=(90,), frames=1, distance=0.2)
        result = self.collect([b"DOA,1,90\n"], settings)
        self.assertEqual(result.path.parent.parent.name, "1sourceAI")
        self.assertEqual(result.path.name, "01_90dis02.csv")
        self.assertEqual(result.stats.tp, 1)
        with result.path.open(newline="", encoding="utf-8") as h:
            self.assertEqual(next(csv.DictReader(h))["raw_angles"], "90")

    def test_filename_matches_ai3_for_three_sorted_angles(self):
        settings = replace(self.settings, true_angles=(180, 90, 0), frames=1, distance=0.3)
        result = self.collect([b"DOA,3,0,90,180\n"], settings)
        self.assertEqual(result.path.name, "01_00_90_180dis03.csv")

    def test_arbitrary_distance_preserved_despite_rounded_dis_code(self):
        result = self.collect([b"DOA,1,0\n"],
                              replace(self.settings, frames=1, distance=0.15))
        self.assertEqual(result.path.parent.name, "0.15m")
        with result.path.open(newline="", encoding="utf-8") as h:
            self.assertEqual(float(next(csv.DictReader(h))["distance_cm"]), 15)

    def test_eval_ignored_not_double_counted(self):
        result = self.collect([b"EVAL,1,0,1000,1\nDOA,0\nDOA,1,0\n"],
                              replace(self.settings, frames=2))
        self.assertEqual((result.stats.frames, result.stats.tp, result.stats.fn), (2, 1, 1))

    def test_warmup_discard(self):
        result = self.collect([b"DOA,0\nDOA,1,0\n"], replace(self.settings, frames=1, discard=1))
        self.assertEqual(result.stats.fn, 0)

    def test_timeout_keeps_header_without_fake_frames(self):
        result = self.collect([], clock=FakeClock(0.25))
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.stats.frames, 0)
        self.assertIsNone(result.stats.metrics()["recall"])
        self.assertTrue(result.path.is_file())

    def test_interrupt_and_uart_error_keep_data(self):
        for event, status in ((KeyboardInterrupt(), "interrupted"), (OSError("lost"), "serial_error")):
            result = self.collect([b"DOA,0\n", event])
            self.assertEqual(result.status, status)
            _, stats = doa.score_csv(result.path, self.settings)
            self.assertEqual((stats.frames, stats.fn), (1, 1))

    def test_runs_never_overwrite(self):
        settings = replace(self.settings, frames=1)
        first = self.collect([b"DOA,1,0\n"], settings)
        before = first.path.read_bytes()
        second = self.collect([b"DOA,0\n"], settings)
        self.assertEqual(first.path.read_bytes(), before)
        self.assertEqual(second.path.name, "02_00dis01.csv")

    def test_noise_round_trip_ai3_no_extra_columns(self):
        settings = replace(self.settings, true_angles=(), frames=2)
        result = self.collect([b"DOA,0\nDOA,1,0\n"], settings)
        self.assertEqual(result.path.parent.parent.name, "0sourceNOAI")
        metadata, stats = doa.score_csv(result.path, settings)
        self.assertEqual(metadata["n_sources"], 0)
        self.assertEqual(stats.metrics()["noise_fp_rate"], 0.5)
        self.assertIsNone(stats.metrics()["recall"])
        self.assertIsNone(result.nonempty_stats)
        self.assertEqual(result.display_stats.metrics()["noise_fp_rate"], 0.5)

    def test_missing_count_and_sample_gaps_rejected(self):
        result = self.collect([b"DOA,1,0\n"], replace(self.settings, frames=1))
        for changes in ({"detected_count": "2"}, {"sample": "2"}):
            with result.path.open(newline="", encoding="utf-8") as h:
                row = next(csv.DictReader(h))
            row.update(changes)
            with result.path.open("w", newline="", encoding="utf-8") as h:
                writer = csv.DictWriter(h, fieldnames=doa.csv_fields(1))
                writer.writeheader()
                writer.writerow(row)
            with self.assertRaises(ValueError):
                doa.score_csv(result.path, self.settings)

    def test_unknown_mode_folder_and_legacy_filtered_csv_rejected(self):
        path = self.root / "unknown.csv"
        with path.open("w", newline="", encoding="utf-8") as h:
            writer = csv.writer(h)
            writer.writerow(doa.csv_fields(1))
            writer.writerow(doa.csv_row(1, (0,), 0.1, (0,)))
        with self.assertRaisesRegex(ValueError, "folder"):
            doa.score_csv(path, self.settings)
        with path.open("w", newline="", encoding="utf-8") as h:
            h.write("sample,true_angle,distance_m,detected_angle,error\n1,0,0.1,0,0\n")
        with self.assertRaisesRegex(ValueError, "header"):
            doa.score_csv(path, self.settings)

    def test_analyze_separates_ai_noai_and_ignores_repeated_paths(self):
        settings = replace(self.settings, frames=1)
        self.collect([b"DOA,1,0\n"], settings)
        self.collect([b"DOA,0\n"], replace(settings, mode="ai"))
        settings = replace(settings, action="analyze",
                           analyze_folders=(settings.output_root,
                                            settings.output_root / "1sourceAI"))
        with redirect_stdout(io.StringIO()):
            summary, report = doa.analyze(settings)
        with summary.open(newline="", encoding="utf-8-sig") as h:
            rows = list(csv.DictReader(h))
        self.assertEqual(len(rows), 4)
        grouped = {row["mode"]: row for row in rows if row["source_file"] == "OVERALL"}
        self.assertEqual(float(grouped["no_ai"]["recall"]), 1)
        self.assertEqual(float(grouped["ai"]["recall"]), 0)
        self.assertTrue(report.is_file())

    def test_analyze_does_not_require_uart_config(self):
        replace(self.settings, action="analyze", port="", baud=0, frames=0, distance=0).validate()

    def test_analyze_never_reads_its_own_reports_or_archives(self):
        self.collect([b"DOA,1,0\n"], replace(self.settings, frames=1))
        archived = self.settings.output_root / "_archive"
        archived.mkdir()
        (archived / "ignore.csv").write_text("not,a,measurement\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            doa.analyze(replace(self.settings, action="analyze"))
        messages = io.StringIO()
        with redirect_stdout(messages):
            summary, _ = doa.analyze(replace(self.settings, action="analyze"))
        self.assertNotIn("Không đọc được", messages.getvalue())
        with summary.open(newline="", encoding="utf-8-sig") as h:
            self.assertEqual(len(list(csv.DictReader(h))), 2)

    def test_all_default_outputs_inside_data_outside_python(self):
        settings = doa.Settings()
        for folder in (settings.output_root, settings.report_root, *settings.analyze_folders):
            self.assertTrue(folder.is_relative_to(doa.PROJECT_ROOT / "data"))
            self.assertFalse(folder.is_relative_to(doa.PROJECT_ROOT / "Python"))

    def test_invalid_settings(self):
        for changed in ({"true_angles": (0, 0)}, {"true_angles": (360,)},
                        {"distance": float("nan")}, {"distance": 1e308}, {"frames": 0}, {"discard": -1},
                        {"tolerance": 181}, {"output_root": doa.PROJECT_ROOT / "Python" / "data"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                replace(self.settings, **changed).validate()

    def test_measure_has_no_radar_or_preview_mode(self):
        self.assertFalse(hasattr(doa, "LiveRadar"))
        self.assertFalse(hasattr(self.settings, "show_live"))
        with self.assertRaisesRegex(ValueError, "visualize_doa.py"):
            replace(self.settings, action="preview").validate()

    def test_incomplete_measurement_ends_session_and_keeps_csv(self):
        inputs = iter(["0", "0.1"])
        messages = io.StringIO()
        with redirect_stdout(messages):
            code = doa.measure_session(self.settings, lambda _: next(inputs),
                lambda _: doa.CollectionResult(Path("partial.csv"), doa.Stats(), "timeout"))
        self.assertEqual(code, 1)
        self.assertIn("partial.csv", messages.getvalue())


if __name__ == "__main__":
    unittest.main()
