"""Kiểm thử phân tích/biểu đồ offline bằng CSV giả, không mở COM/trình duyệt."""
from __future__ import annotations

import csv
import io
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from Python import analyze_doa as analysis
from Python import measure_doa as doa
from Python import process_doa as process


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.settings = analysis.Settings(data_root=self.root, report_root=self.root / "_reports", open_report=False)

    def make_csv(self, detected, truth=(0,), distance=0.1, mode="no_ai", name="01_test.csv"):
        path = self.root / f"{len(truth)}source{'AI' if mode == 'ai' else 'NOAI'}" / f"{distance:g}m" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(doa.csv_fields(len(truth)))
            for sample, angles in enumerate(detected, 1):
                writer.writerow(doa.csv_row(sample, truth, distance, angles))
        return path

    def load(self, settings=None):
        with redirect_stdout(io.StringIO()):
            return analysis.load_records(settings or self.settings)

    def aggregate(self, records):
        aggregate = analysis.Aggregate()
        for record in records:
            aggregate.add(record, self.settings.tolerance)
        return aggregate

    def filter_data(self):
        with redirect_stdout(io.StringIO()):
            return process.process_data(process.Settings(data_root=self.root,
                                        output_root=self.root / "_processed"))[0]

    def run_analysis(self, settings=None):
        with redirect_stdout(io.StringIO()):
            return analysis.analyze_data(settings or self.settings)

    def test_empty_and_wrong_frames_count_as_fn_but_mae_not_clipped(self):
        self.make_csv([(0,), (), (180,)])
        records, _, _ = self.load()
        metrics = self.aggregate(records).metrics()
        self.assertAlmostEqual(metrics["recall"], 1/3)
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (1, 1, 2))
        self.assertEqual(metrics["mae_equal_count_deg"], 90)
        self.assertEqual(metrics["matched_mae_deg"], 0)
        self.assertAlmostEqual(metrics["rmse_equal_count_deg"], (180**2/2)**0.5)

    def test_repeated_files_are_frame_weighted_not_mean_of_percentages(self):
        self.make_csv([(0,)], name="01.csv")
        self.make_csv([()]*9, name="02.csv")
        _, _, distances = analysis.summarize(self.load()[0], 15)
        self.assertEqual(distances[0]["recall"], 0.1)
        self.assertEqual((distances[0]["files"], distances[0]["frames"]), (2, 10))
        self.assertIsNone(distances[0]["mean_bearing_deg"])

    def test_circular_mean_of_359_and_1_is_zero_not_180(self):
        self.make_csv([(359,), (1,)])
        metrics = self.aggregate(self.load()[0]).metrics(include_bearing=True)
        self.assertAlmostEqual(metrics["mean_bearing_deg"], 0)
        self.assertEqual(metrics["mae_equal_count_deg"], 1)

    def test_opposite_bearings_have_no_unique_mean(self):
        self.make_csv([(0,), (180,)])
        metrics = self.aggregate(self.load()[0]).metrics(include_bearing=True)
        self.assertIsNone(metrics["mean_bearing_deg"])

    def test_processed_comparison_keeps_same_pairs_and_original_samples(self):
        source = self.make_csv([(0,), (), (), (), (180,)])
        session = self.filter_data()
        records, errors, selected = self.load(replace(self.settings, data_mode="compare"))
        self.assertEqual(selected, session)
        self.assertEqual(errors, [])
        self.assertEqual([r.dataset for r in records], ["RAW", "FILTERED"])
        self.assertEqual([r["sample"] for r in records[1].rows], ["1", "5"])
        files, _, _ = analysis.summarize(records, 15)
        self.assertEqual([row["recall"] for row in files], [0.2, 0.5])
        self.assertEqual([row["mae_equal_count_deg"] for row in files], [90, 90])
        self.assertEqual(records[1].measurement.path, source.resolve())

    def test_new_source_without_processed_pair_excluded_from_both_sides(self):
        paired = self.make_csv([(0,)])
        self.filter_data()
        self.make_csv([(0,)], name="02_new.csv")
        records, errors, _ = self.load(replace(self.settings, data_mode="compare"))
        self.assertEqual(len(records), 2)
        self.assertEqual({r.measurement.path for r in records}, {paired.resolve()})
        self.assertEqual(len(errors), 1)

    def test_changed_raw_sha_rejects_comparison_pair(self):
        changed = self.make_csv([(0,)], name="01.csv")
        self.make_csv([(0,)], name="02.csv")
        self.filter_data()
        self.make_csv([(1,)], name="01.csv")
        records, errors, _ = self.load(replace(self.settings, data_mode="compare"))
        self.assertEqual(len(records), 2)
        self.assertNotIn(changed.resolve(), {r.measurement.path for r in records})
        self.assertIn("SHA256", errors[0]["error"])

    def test_tampered_filtered_rows_rejected(self):
        self.make_csv([(0,), (), (), ()])
        session = self.filter_data()
        manifest = analysis.read_manifest(session)
        entry = next(iter(manifest.values()))
        path = Path(entry["filtered_file"])
        with path.open(newline="", encoding="utf-8-sig") as handle:
            row = next(csv.DictReader(handle))
        row["raw_angles"] = "180"
        process.write_table(session / "tampered.csv", doa.csv_fields(1), [row])
        entry["filtered_file"] = str(session / "tampered.csv")
        measurement = process.load_measurement(next(iter(manifest)), self.root)
        with self.assertRaisesRegex(ValueError, "không khớp"):
            analysis.validated_filtered_rows(measurement, entry, session)

    def test_no_filtered_session_does_not_silently_filter_or_fallback(self):
        self.make_csv([(0,)])
        with self.assertRaisesRegex(RuntimeError, "process_doa.py"):
            self.load(replace(self.settings, data_mode="compare"))

    def test_all_filtered_away_returns_na_not_perfect_recall(self):
        self.make_csv([()]*5)
        self.filter_data()
        records, _, _ = self.load(replace(self.settings, data_mode="filtered"))
        metrics = self.aggregate(records).metrics()
        self.assertEqual(metrics["frames"], 0)
        self.assertIsNone(metrics["recall"])
        self.assertIsNone(metrics["mae_equal_count_deg"])
        output, _, _ = self.run_analysis(replace(self.settings, data_mode="filtered"))
        self.assertIn("N/A", (output / "index.html").read_text(encoding="utf-8"))

    def test_modes_distances_and_source_counts_not_mixed(self):
        self.make_csv([(0,)], distance=0.1)
        self.make_csv([()], distance=0.2)
        self.make_csv([()], mode="ai")
        self.make_csv([(0, 90), (), (90,)], truth=(0, 90))
        records, _, _ = self.load(replace(self.settings, mode="all", source_counts=(1, 2)))
        _, conditions, distances = analysis.summarize(records, 15)
        self.assertEqual(len(distances), 4)
        multi = next(row for row in conditions if row["n_sources"] == 2)
        self.assertEqual(multi["true_angles"], "0;90")
        self.assertEqual(multi["recall"], 0.5)
        self.assertIsNone(multi["mean_bearing_deg"])
        self.assertEqual(len(self.load(replace(self.settings, distances=(0.2,)))[0]), 1)

    def test_invalid_file_is_reported_without_discarding_valid_files(self):
        self.make_csv([(0,)])
        bad = self.make_csv([], name="02_empty.csv")
        output, distances, errors = self.run_analysis()
        self.assertEqual(distances[0]["frames"], 1)
        self.assertEqual(errors[0]["source_file"], str(bad.resolve()))
        self.assertTrue((output / "analysis_errors.csv").is_file())

    def test_all_outputs_valid_xml_and_raw_is_unchanged_no_browser_open(self):
        raw = self.make_csv([(359,), (), (1,), (180,)])
        original = raw.read_bytes()
        with patch.object(analysis.webbrowser, "open") as browser:
            output, _, _ = self.run_analysis()
            browser.assert_not_called()
        self.assertEqual(raw.read_bytes(), original)
        plots = list(output.glob("*.svg"))
        self.assertEqual(len(plots), 9)
        for plot in plots:
            tree = ET.fromstring(plot.read_text(encoding="utf-8"))
            self.assertEqual(tree.tag, "{http://www.w3.org/2000/svg}svg")
        html = (output / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("<svg "), 9)
        self.assertIn("FILTERED", html)
        self.assertIn("không phải recall tiếng nói", html)
        for filename in ("per_file.csv", "by_angle_configuration.csv", "by_distance.csv", "README.md"):
            self.assertTrue((output / filename).is_file())

    def test_duplicate_report_timestamp_uses_new_folder(self):
        self.make_csv([(0,)])
        with patch.object(analysis, "datetime") as timestamp:
            timestamp.now.return_value.strftime.return_value = "same_stamp"
            first, _, _ = self.run_analysis()
            second, _, _ = self.run_analysis()
        self.assertNotEqual(first, second)

    def test_invalid_detail_file_no_partial_report_folder(self):
        self.make_csv([(0,)])
        with self.assertRaisesRegex(ValueError, "DETAIL_FILE"):
            self.run_analysis(replace(self.settings, detail_file="not_here.csv"))
        self.assertFalse(self.settings.report_root.exists())

    def test_invalid_settings_and_output_to_raw_rejected(self):
        for change in ({"data_mode": "wrong"}, {"source_counts": (0,)}, {"mode": "wrong"},
                       {"tolerance": 181}, {"open_report": 1}, {"report_root": self.root / "1sourceNOAI"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.settings, **change).validate()

    def test_direct_file_import_with_run_button_layout(self):
        path = Path(analysis.__file__).resolve()
        code = ("import sys, runpy; "
                f"sys.path.insert(0, {str(path.parent)!r}); "
                f"module=runpy.run_path({str(path)!r}, run_name='smoke_test'); "
                "assert callable(module['main'])")
        result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))


class SvgTests(unittest.TestCase):
    def test_missing_value_is_not_a_zero_or_connected_across_gap(self):
        svg = analysis.line_chart("Title <test>", "x", "y", [("A&B", [(0, 1), (1, None), (2, 2)])])
        tree = ET.fromstring(svg)
        namespace = {"s": "http://www.w3.org/2000/svg"}
        self.assertEqual(len(tree.findall(".//s:circle", namespace)), 2)
        self.assertEqual(len(tree.findall(".//s:polyline", namespace)), 0)
        self.assertIn("Title &lt;test&gt;", svg)
        self.assertNotIn("nan", svg.lower())

    def test_mean_bearing_plot_wrap_is_display_only(self):
        row = {"dataset": "RAW", "mode": "no_ai", "angle": 0, "mean_bearing_deg": 359}
        series = analysis.make_series([row], "angle", "mean_bearing_deg", bearing=True)
        self.assertEqual(series[0][1], [(0.0, -1.0)])
        self.assertEqual(row["mean_bearing_deg"], 359)

    def test_detail_truth_line_and_empty_markers_not_fake_angle_zero(self):
        svg = analysis.line_chart("Frames", "sample", "angle",
            [("RAW", [(1, 0), (3, 90)]), ("Góc thật 0°", [(1, 0), (3, 0)])],
            y_bounds=(0, 359), points_only=True, empty_samples=[2])
        tree = ET.fromstring(svg)
        namespace = {"s": "http://www.w3.org/2000/svg"}
        self.assertEqual(len(tree.findall(".//s:polyline", namespace)), 1)
        self.assertIn("DOA,0 (không phải góc 0°)", svg)


if __name__ == "__main__":
    unittest.main()
