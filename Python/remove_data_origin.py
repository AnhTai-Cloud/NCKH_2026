"""Bấm Run để bỏ cột data_origin trong CSV đang dùng ở data/.

Giữ nguyên các cột còn lại. Sao lưu trước khi ghi đè và chuyển nguồn dữ
liệu sang data/_data_sources.json. Không sửa các thư mục nội bộ bắt đầu
bằng dấu _, gồm bản sao lưu, báo cáo và các phiên dữ liệu lưu riêng.
Có thể dùng --dry-run để chỉ xem số file cần sửa.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def atomic_write(path, content):
    """Ghi tệp tạm cùng thư mục rồi thay nguyên tệp."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".csv-column-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def remove_data_origin(data_dir=DATA_DIR, *, dry_run=False):
    root = Path(data_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Không có thư mục dữ liệu: {root}")
    registry_path = root / "_data_sources.json"
    if not registry_path.resolve().is_relative_to(root):
        raise ValueError("Tệp nguồn dữ liệu nằm ngoài thư mục dữ liệu.")
    registry_before = registry_path.read_bytes() if registry_path.exists() else None
    registry = json.loads(registry_before.decode("utf-8")) if registry_before is not None else {"version": 1, "files": {}}
    if not isinstance(registry, dict) or registry.get("version") != 1 or not isinstance(registry.get("files"), dict):
        raise ValueError("Tệp nguồn dữ liệu hiện có không đúng định dạng; không ghi đè.")
    changes = []
    for candidate in sorted(root.rglob("*.csv")):
        relative = candidate.relative_to(root)
        if any(part.startswith("_") for part in relative.parts[:-1]):
            continue
        path = candidate.resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Đường dẫn CSV nằm ngoài thư mục dữ liệu: {candidate}")
        before = path.read_bytes()
        rows = list(csv.reader(io.StringIO(before.decode("utf-8-sig"), newline="")))
        if not rows or "data_origin" not in rows[0]:
            continue
        header = rows[0]
        if header.count("data_origin") != 1:
            raise ValueError(f"{relative}: cột data_origin bị trùng.")
        index = header.index("data_origin")
        if any(row and len(row) != len(header) for row in rows[1:]):
            raise ValueError(f"{relative}: dòng CSV thiếu/thừa cột.")
        origins = {row[index] for row in rows[1:] if row}
        if len(origins) != 1 or not origins.issubset({"MEASURED", "SYNTHETIC"}):
            raise ValueError(f"{relative}: nguồn dữ liệu rỗng, không hợp lệ hoặc thay đổi trong file.")
        origin = next(iter(origins))
        previous_entry = registry["files"].get(relative.as_posix())
        if previous_entry is not None and (not isinstance(previous_entry, dict)
                                           or previous_entry.get("sha256") != sha256(before)
                                           or previous_entry.get("data_origin") != origin):
            raise ValueError(f"{relative}: CSV không khớp tệp nguồn dữ liệu hiện có.")
        retained = [row[:index]+row[index+1:] if row else [] for row in rows]
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\r\n").writerows(retained)
        encoding = "utf-8-sig" if before.startswith(b"\xef\xbb\xbf") else "utf-8"
        after = output.getvalue().encode(encoding)
        if list(csv.reader(io.StringIO(after.decode("utf-8-sig"), newline=""))) != retained:
            raise ValueError(f"{relative}: nội dung các cột còn lại thay đổi.")
        changes.append({"path": path, "relative": relative.as_posix(), "before": before,
                        "after": after, "data_origin": origin})
    if dry_run or not changes:
        return {"changed": len(changes), "dry_run": dry_run, "backup": None}

    timestamp = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d_%H%M%S_%f")
    archive = root / "_archive" / f"remove_data_origin_{timestamp}"
    if not archive.resolve().is_relative_to(root):
        raise ValueError("Thư mục sao lưu nằm ngoài thư mục dữ liệu.")
    archive.mkdir(parents=True, exist_ok=False)
    backup_path = archive / "original_csv.zip"
    with zipfile.ZipFile(backup_path, "x", zipfile.ZIP_DEFLATED) as backup:
        for change in changes:
            backup.writestr(change["relative"], change["before"])
    if registry_before is not None:
        (archive / "data_sources_before.json").write_bytes(registry_before)
    manifest = []
    for change in changes:
        entry = dict(registry["files"].get(change["relative"], {}))
        entry.update(data_origin=change["data_origin"], sha256=sha256(change["after"]),
                     previous_sha256=sha256(change["before"]), backup=str(backup_path))
        registry["files"][change["relative"]] = entry
        manifest.append({"file": change["relative"], **entry})
    registry_after = (json.dumps(registry, ensure_ascii=False, indent=2)+"\n").encode("utf-8")
    applied = []
    try:
        for change in changes:
            if change["path"].read_bytes() != change["before"]:
                raise ValueError(f"CSV vừa thay đổi; không ghi đè: {change['relative']}")
            atomic_write(change["path"], change["after"])
            applied.append(change)
        current_registry = registry_path.read_bytes() if registry_path.exists() else None
        if current_registry != registry_before:
            raise ValueError("Tệp nguồn dữ liệu vừa thay đổi; không ghi đè.")
        atomic_write(registry_path, registry_after)
    except BaseException:
        for change in reversed(applied):
            if change["path"].read_bytes() == change["after"]:
                atomic_write(change["path"], change["before"])
        if registry_path.exists() and registry_path.read_bytes() == registry_after:
            if registry_before is None:
                registry_path.unlink()
            else:
                atomic_write(registry_path, registry_before)
        raise
    (archive / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"changed": len(applied), "dry_run": False, "backup": str(backup_path),
            "source_file": str(registry_path)}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = remove_data_origin(args.data_dir, dry_run=args.dry_run)
    if result["dry_run"]:
        print(f"Có {result['changed']} CSV cần bỏ cột data_origin. Chưa sửa file.")
    else:
        print(f"Đã bỏ cột data_origin trong {result['changed']} CSV.")
        if result["backup"]:
            print(f"Bản sao lưu: {result['backup']}")
            print(f"Nguồn dữ liệu lưu riêng: {result['source_file']}")


if __name__ == "__main__":
    main()
