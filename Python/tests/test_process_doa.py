"""Kiểm thử bộ lọc bằng CSV giả trong thư mục tạm, không thay đổi data thật."""
from __future__ import annotations

import csv
import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from Python import measure_doa as doa
from Python import process_doa as process


class EmptyRunTests(unittest.TestCase):
    def rows(self, counts):
        return [{"sample": str(i+1), "detected_count": str(count),
                 "raw_angles": "0" if count else ""} for i, count in enumerate(counts)]

    def test_short_runs_of_one_or_two_stay(self):
        rows = self.rows([0, 1, 0, 0, 1, 0])
        kept, runs = process.filter_empty_runs(rows, 3)
        self.assertEqual(kept, rows)
        self.assertEqual(runs, [])

    def test_three_ten_and_more_than_ten_are_all_removed(self):
        for length in (3, 10, 11, 100):
            with self.subTest(length=length):
                rows = self.rows([1] + [0]*length + [1])
                original = [dict(row) for row in rows]
                kept, runs = process.filter_empty_runs(rows, 3)
                self.assertEqual([r["sample"] for r in kept], ["1", str(length+2)])
                self.assertEqual(runs, [process.EmptyRun(2, length+1, length)])
                self.assertEqual(rows, original)

    def test_leading_and_trailing_empty_runs_removed(self):
        kept, runs = process.filter_empty_runs(self.rows([0]*3 + [1] + [0]*4), 3)
        self.assertEqual([r["sample"] for r in kept], ["4"])
        self.assertEqual(runs, [process.EmptyRun(1, 3, 3), process.EmptyRun(5, 8, 4)])

    def test_nonempty_frame_breaks_run(self):
        rows = self.rows([0, 0, 1, 0, 0])
        kept, runs = process.filter_empty_runs(rows, 3)
        self.assertEqual(kept, rows)
        self.assertEqual(runs, [])

    def test_threshold_ten_keeps_nine(self):
        kept, runs = process.filter_empty_runs(self.rows([0]*9 + [1] + [0]*10), 10)
        self.assertEqual(len(kept), 10)
        self.assertEqual(runs, [process.EmptyRun(11, 20, 10)])

    def test_all_empty_or_no_empty(self):
        self.assertEqual(process.filter_empty_runs(self.rows([0]*5), 3),
                         ([], [process.EmptyRun(1, 5, 5)]))
        self.assertEqual(process.filter_empty_runs(self.rows([1]*5), 3)[1], [])

    def test_invalid_threshold_rejected(self):
        for minimum in (0, -1, True, 3.5):
            with self.assertRaises(ValueError):
                process.filter_empty_runs([], minimum)


class CsvProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.settings = process.Settings(data_root=self.root, output_root=self.root / "_processed")

    def make_csv(self, detected, truth=(0,), mode="no_ai", distance=0.1, name="01_test.csv"):
        branch = f"{len(truth)}source{'AI' if mode == 'ai' else 'NOAI'}"
        path = self.root / branch / f"{distance:g}m" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(doa.csv_fields(len(truth)))
            for i, angles in enumerate(detected, 1):
                writer.writerow(doa.csv_row(i, truth, distance, angles))
        return path

    def run_filter(self, settings=None):
        with redirect_stdout(io.StringIO()):
            return process.process_data(settings or self.settings)

    def test_output_keeps_header_raw_values_samples_and_raw_bytes(self):
        source = self.make_csv([(359,), (), (), (), (180,)])
        original = source.read_bytes()
        run_root, summary = self.run_filter()
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(summary[0]["source_sha256"], hashlib.sha256(original).hexdigest())
        output = Path(summary[0]["filtered_file"])
        self.assertTrue(output.is_relative_to(run_root))
        with output.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, doa.csv_fields(1))
            kept = list(reader)
        original_rows = process.load_measurement(source, self.root).rows
        self.assertEqual(kept, [original_rows[0], original_rows[4]])
        self.assertEqual([r["sample"] for r in kept], ["1", "5"])
        self.assertEqual([r["raw_angles"] for r in kept], ["359", "180"])
        self.assertEqual(summary[0]["frames_removed"], 3)

    def test_report_exposes_before_after_recall_and_removed_sample_ranges(self):
        self.make_csv([(0,), (), (), (), (180,)])
        run_root, summary = self.run_filter()
        self.assertEqual(summary[0]["recall_all_frames"], 0.2)
        self.assertEqual(summary[0]["recall_retained_frames_doa_selected"], 0.5)
        self.assertEqual((summary[0]["tp_before"], summary[0]["tp_retained"]), (1, 1))
        self.assertEqual((summary[0]["fn_before"], summary[0]["fn_retained"]), (4, 1))
        with (run_root / "removed_runs.csv").open(newline="", encoding="utf-8-sig") as handle:
            removed = list(csv.DictReader(handle))
        self.assertEqual((removed[0]["start_sample"], removed[0]["end_sample"], removed[0]["frame_count"]),
                         ("2", "4", "3"))
        self.assertIn("KHÔNG thay thế recall_all_frames", (run_root / "README.md").read_text(encoding="utf-8"))

    def test_dry_run_never_creates_files_or_folders(self):
        self.make_csv([(0,), (), (), ()])
        with patch.object(process, "write_table", side_effect=AssertionError("No file writes")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("No folder writes")):
            run_root, summaries = self.run_filter(replace(self.settings, save_output=False))
        self.assertIsNone(run_root)
        self.assertEqual(summaries[0]["frames_removed"], 3)
        self.assertFalse(self.settings.output_root.exists())

    def test_all_removed_has_header_and_undefined_retained_recall(self):
        self.make_csv([()]*5)
        _, summary = self.run_filter()
        self.assertEqual(summary[0]["frames_retained"], 0)
        self.assertIsNone(summary[0]["recall_retained_frames_doa_selected"])
        self.assertEqual(summary[0]["recall_all_frames"], 0)
        with Path(summary[0]["filtered_file"]).open(newline="", encoding="utf-8-sig") as handle:
            self.assertEqual(len(list(csv.reader(handle))), 1)

    def test_wrong_angle_and_missing_extra_sources_are_kept(self):
        self.make_csv([(180,), (0,), (0, 90, 180), (), (), ()], truth=(0, 90))
        _, summaries = self.run_filter(replace(self.settings, source_counts=(2,)))
        self.assertEqual(summaries[0]["frames_retained"], 3)
        self.assertEqual(summaries[0]["tp_before"], summaries[0]["tp_retained"])
        self.assertEqual(summaries[0]["fp_before"], summaries[0]["fp_retained"])

    def test_modes_and_distances_selected_without_reading_legacy_noise_or_processed(self):
        raw = self.make_csv([(0,)], distance=0.1)
        self.make_csv([(0,)], distance=0.2)
        self.make_csv([(0,)], mode="ai")
        self.make_csv([()], truth=())
        for folder in (self.root / "0.1m", self.root / "_processed" / "1sourceNOAI",
                       self.root / "_archive", self.root / "_reports"):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "ignore.csv").write_text("not,a,raw,CSV\n", encoding="utf-8")
        _, summary = self.run_filter(replace(self.settings, distances=(0.1,)))
        self.assertEqual([row["source_file"] for row in summary], [str(raw.resolve())])
        _, both = self.run_filter(replace(self.settings, mode="all", distances=(0.1,), save_output=False))
        self.assertEqual({row["mode"] for row in both}, {"ai", "no_ai"})

    def test_invalid_rows_are_errors_not_assumed_silence(self):
        for change in ({"sample": "2"}, {"detected_count": "0"}, {"raw_angles": ""},
                       {"raw_angles": "360"}, {"raw_angles": "0;"}):
            source = self.make_csv([(0,)])
            with source.open(newline="", encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            row.update(change)
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=doa.csv_fields(1))
                writer.writeheader()
                writer.writerow(row)
            run_root, summaries = self.run_filter()
            self.assertIsNone(run_root)
            self.assertEqual(summaries[0]["status"], "error")

    def test_empty_header_and_noise_rejected(self):
        source = self.make_csv([])
        with self.assertRaisesRegex(ValueError, "chưa có dữ liệu"):
            process.load_measurement(source, self.root)
        noise = self.make_csv([()], truth=())
        with self.assertRaises(ValueError):
            process.load_measurement(noise, self.root)

    def test_repeat_run_does_not_overwrite_previous_output(self):
        self.make_csv([(0,), (), (), ()])
        with patch.object(process, "datetime") as timestamp:
            timestamp.now.return_value.strftime.return_value = "same_timestamp"
            first_root, first = self.run_filter()
            saved = Path(first[0]["filtered_file"]).read_bytes()
            second_root, _ = self.run_filter()
        self.assertNotEqual(first_root, second_root)
        self.assertEqual(Path(first[0]["filtered_file"]).read_bytes(), saved)

    def test_failed_filtered_write_still_reports_error_without_successful_files(self):
        self.make_csv([(0,), (), (), ()])
        original_writer = process.write_table
        def fail_filtered(path, header, rows):
            if Path(path).name == "01_test.csv":
                raise OSError("simulated write failure")
            return original_writer(path, header, rows)
        with patch.object(process, "write_table", side_effect=fail_filtered):
            run_root, summaries = self.run_filter()
        self.assertEqual(summaries[0]["status"], "error")
        with (run_root / "filter_summary.csv").open(newline="", encoding="utf-8-sig") as handle:
            report = list(csv.DictReader(handle))
        self.assertIn("simulated write failure", report[0]["error"])

    def test_raw_analyze_excludes_processed_even_with_data_root_selected(self):
        self.make_csv([(0,), (), (), (), (0,)])
        self.run_filter()
        settings = doa.Settings(action="analyze", output_root=self.root,
                                report_root=self.root / "_reports", analyze_folders=(self.root,))
        messages = io.StringIO()
        with redirect_stdout(messages):
            summary_path, _ = doa.analyze(settings)
        self.assertNotIn("Không đọc được", messages.getvalue())
        with summary_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual({int(row["frames"]) for row in rows}, {5})

    def test_invalid_settings(self):
        for change in ({"source_counts": (0,)}, {"source_counts": ()}, {"mode": "noise"},
                       {"min_empty_run": 0}, {"min_empty_run": True}, {"distances": (float("nan"),)},
                       {"output_root": self.root / "1sourceNOAI"}, {"save_output": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.settings, **change).validate()

    def test_direct_file_import_for_run_button(self):
        path = Path(process.__file__).resolve()
        code = ("import sys, runpy; "
                f"sys.path.insert(0, {str(path.parent)!r}); "
                f"module=runpy.run_path({str(path)!r}, run_name='smoke_test'); "
                "assert callable(module['main'])")
        result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()
