import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from Python import remove_data_origin as remove


class RemoveDataOriginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.path = self.root / "1sourceAI" / "0.1m" / "01_00dis01.csv"
        self.path.parent.mkdir(parents=True)
        self.rows = [["sample", "data_origin", "raw_angles", "note"],
                     ["1", "SYNTHETIC", "0;15", 'Giữ "dấu phẩy", và xuống\ndòng'],
                     ["2", "SYNTHETIC", "", ""]]
        with self.path.open("w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle).writerows(self.rows)
        self.before = self.path.read_bytes()

    def test_values_backup_and_separate_source_file_are_preserved(self):
        result = remove.remove_data_origin(self.root)
        values = list(csv.reader(io.StringIO(self.path.read_text(encoding="utf-8-sig"), newline="")))
        self.assertEqual(values, [[row[0], *row[2:]] for row in self.rows])
        self.assertTrue(self.path.read_bytes().startswith(b"\xef\xbb\xbf"))
        entry = json.loads((self.root / "_data_sources.json").read_text(encoding="utf-8"))["files"][self.path.relative_to(self.root).as_posix()]
        self.assertEqual(entry["data_origin"], "SYNTHETIC")
        self.assertEqual(entry["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        with zipfile.ZipFile(result["backup"]) as backup:
            self.assertEqual(backup.read(self.path.relative_to(self.root).as_posix()), self.before)
        self.assertEqual(remove.remove_data_origin(self.root)["changed"], 0)

    def test_dry_run_does_not_write_anything(self):
        result = remove.remove_data_origin(self.root, dry_run=True)
        self.assertEqual(result["changed"], 1)
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertFalse((self.root / "_archive").exists())
        self.assertFalse((self.root / "_data_sources.json").exists())

    def test_internal_folders_are_untouched(self):
        archived = self.root / "_archive" / "01_old.csv"
        archived.parent.mkdir()
        archived.write_bytes(self.before)
        remove.remove_data_origin(self.root)
        self.assertEqual(archived.read_bytes(), self.before)

    def test_failure_writing_registry_restores_original_csv(self):
        real_write = remove.atomic_write
        def fail_registry(path, content):
            if path.name == "_data_sources.json":
                raise OSError("Registry write failed")
            return real_write(path, content)
        with patch.object(remove, "atomic_write", side_effect=fail_registry):
            with self.assertRaises(OSError):
                remove.remove_data_origin(self.root)
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertFalse((self.root / "_data_sources.json").exists())


if __name__ == "__main__":
    unittest.main()
