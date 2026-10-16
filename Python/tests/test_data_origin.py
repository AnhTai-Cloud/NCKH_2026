"""Keep simulated CSVs traceable through loading, filtering, and reporting."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from Python import analyze_doa as analysis
from Python import measure_doa as doa
from Python import process_doa as process


class DataOriginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"

    def make_csv(self, name, origins=None, detected=((0,),)):
        path = self.root / "1sourceNOAI" / "0.1m" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(doa.csv_fields(1) + (["data_origin"] if origins is not None else []))
            for i, angles in enumerate(detected):
                writer.writerow(doa.csv_row(i+1, (0,), .1, angles) + ([origins[i]] if origins is not None else []))
        return path

    def test_measured_and_synthetic_stay_separate_in_both_reports(self):
        self.make_csv("01_measured.csv")
        synthetic = self.make_csv("02_replaced.csv", ["SYNTHETIC"], ((90,),))
        self.assertEqual(process.load_measurement(synthetic, self.root).data_origin, "SYNTHETIC")
        with redirect_stdout(io.StringIO()):
            records, errors, _ = analysis.load_records(analysis.Settings(data_root=self.root,
                report_root=self.root / "_reports", open_report=False))
            summary, report = doa.analyze(doa.Settings(action="analyze", output_root=self.root,
                report_root=self.root / "_reports", analyze_folders=(self.root / "1sourceNOAI",)))
        self.assertEqual(errors, [])
        self.assertEqual({r.dataset for r in records}, {"RAW", "SYNTHETIC"})
        _, _, distances = analysis.summarize(records, 15)
        self.assertEqual(len(distances), 2)
        self.assertEqual({r["data_origin"] for r in distances}, {"MEASURED", "SYNTHETIC"})
        with summary.open(encoding="utf-8-sig", newline="") as handle:
            totals = [r for r in csv.DictReader(handle) if r["source_file"] == "OVERALL"]
        self.assertEqual(len(totals), 2)
        self.assertEqual({r["data_origin"]: float(r["recall"]) for r in totals}, {"MEASURED": 1, "SYNTHETIC": 0})
        self.assertIn("Mô phỏng", report.read_text(encoding="utf-8"))
        self.assertNotIn("SYNTHETIC", report.read_text(encoding="utf-8"))

    def test_filter_preserves_origin_and_filtered_dataset(self):
        path = self.make_csv("01_simulated.csv", ["SYNTHETIC"]*5, ((3,), (), (), (), (90,)))
        with redirect_stdout(io.StringIO()):
            session, summaries = process.process_data(process.Settings(data_root=self.root,
                output_root=self.root / "_processed", min_empty_run=3))
            records, _, _ = analysis.load_records(analysis.Settings(data_mode="compare", data_root=self.root,
                report_root=self.root / "_reports", processed_session=str(session), open_report=False))
        self.assertEqual(summaries[0]["data_origin"], "SYNTHETIC")
        self.assertEqual({r.dataset for r in records}, {"SYNTHETIC", "SYNTHETIC_FILTERED"})
        self.assertTrue(all(row["data_origin"] == "SYNTHETIC" for record in records for row in record.rows))
        self.assertEqual(process.load_measurement(path, self.root).data_origin, "SYNTHETIC")

    def test_invalid_or_mixed_origin_is_rejected(self):
        for origins in ([""], ["unknown"], ["SYNTHETIC", "MEASURED"]):
            with self.subTest(origins=origins):
                path = self.make_csv("01_invalid.csv", origins, ((0,),)*len(origins))
                with self.assertRaises(ValueError):
                    doa.score_csv(path, doa.Settings(action="analyze"))
                with self.assertRaises(ValueError):
                    process.load_measurement(path, self.root)

    def register_origin(self, path, origin="SYNTHETIC"):
        (self.root / "_data_sources.json").write_text(json.dumps({"version": 1, "files": {
            path.relative_to(self.root).as_posix(): {"data_origin": origin,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}}), encoding="utf-8")

    def test_origin_in_separate_file_keeps_original_csv_header_and_groups(self):
        self.make_csv("01_measured.csv")
        simulated = self.make_csv("02_simulated.csv", detected=((90,),))
        self.register_origin(simulated)
        measurement = process.load_measurement(simulated, self.root)
        self.assertEqual(measurement.header, doa.csv_fields(1))
        self.assertEqual(measurement.data_origin, "SYNTHETIC")
        self.assertEqual(doa.score_csv(simulated, doa.Settings(action="analyze"))[0]["data_origin"], "SYNTHETIC")
        records, errors, _ = analysis.load_records(analysis.Settings(data_root=self.root,
            report_root=self.root / "_reports", open_report=False))
        self.assertEqual(errors, [])
        self.assertEqual({record.dataset for record in records}, {"RAW", "SYNTHETIC"})
        _, _, distances = analysis.summarize(records, 15)
        self.assertIn("Mô phỏng", analysis.results_table(distances))
        self.assertNotIn("SYNTHETIC", analysis.results_table(distances))

    def test_filter_keeps_separate_file_origin(self):
        path = self.make_csv("01_simulated.csv", detected=((3,), (), (), (), (90,)))
        self.register_origin(path)
        with redirect_stdout(io.StringIO()):
            session, summaries = process.process_data(process.Settings(data_root=self.root,
                output_root=self.root / "_processed", min_empty_run=3))
            records, errors, _ = analysis.load_records(analysis.Settings(data_mode="compare", data_root=self.root,
                report_root=self.root / "_reports", processed_session=str(session), open_report=False))
        self.assertEqual(errors, [])
        self.assertEqual(summaries[0]["data_origin"], "SYNTHETIC")
        self.assertEqual({record.dataset for record in records}, {"SYNTHETIC", "SYNTHETIC_FILTERED"})
        self.assertTrue(all(record.measurement.header == doa.csv_fields(1) for record in records))

    def test_processed_native_csv_is_not_grouped_with_raw_captures(self):
        self.make_csv("01_measured.csv")
        processed = self.make_csv("02_processed.csv", detected=((90,),))
        self.register_origin(processed, "PROCESSED")
        measurement = process.load_measurement(processed, self.root)
        self.assertEqual(measurement.header, doa.csv_fields(1))
        self.assertEqual(measurement.data_origin, "PROCESSED")
        metadata, _ = doa.score_csv(processed, doa.Settings(action="analyze"))
        self.assertEqual(metadata["data_origin"], "PROCESSED")
        records, errors, _ = analysis.load_records(analysis.Settings(data_root=self.root,
            report_root=self.root / "_reports", open_report=False))
        self.assertEqual(errors, [])
        self.assertEqual({record.dataset for record in records}, {"RAW", "PROCESSED"})
        _, _, distances = analysis.summarize(records, 15)
        self.assertEqual({row["data_origin"] for row in distances}, {"MEASURED", "PROCESSED"})
        self.assertIn("Hậu xử lý", analysis.results_table(distances))

    def test_stale_separate_file_origin_is_rejected_by_both_readers(self):
        path = self.make_csv("01_simulated.csv")
        self.register_origin(path)
        path.write_bytes(path.read_bytes()+b"\r\n")
        with self.assertRaisesRegex(ValueError, "CSV khác"):
            process.load_measurement(path, self.root)
        with self.assertRaisesRegex(ValueError, "CSV khác"):
            doa.score_csv(path, doa.Settings(action="analyze"))

    def test_conflicting_inline_and_separate_file_origins_are_rejected(self):
        path = self.make_csv("01_conflicting.csv", ["MEASURED"])
        self.register_origin(path)
        with self.assertRaisesRegex(ValueError, "Nguồn trong CSV"):
            process.load_measurement(path, self.root)
        with self.assertRaisesRegex(ValueError, "Nguồn trong CSV"):
            doa.score_csv(path, doa.Settings(action="analyze"))


if __name__ == "__main__":
    unittest.main()
