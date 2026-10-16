"""XỬ LÝ CSV DOA AI3: LỌC CHUỖI FRAME RỖNG NGHI LÀ KHOẢNG NGẮT NGHỈ.

CÁCH DÙNG
  1. Thu xong dữ liệu bằng measure_doa.py; không thay đổi cách thu trên STM32.
  2. Chỉnh khối CẤU HÌNH bên dưới rồi bấm Run, không phải nhập terminal.
  3. CSV gốc KHÔNG bị sửa. Mỗi lần Run tạo một phiên mới trong data/_processed.
     Phiên chứa CSV đã lọc, filter_summary.csv, removed_runs.csv và README.md.

Ý NGHĨA CẤU HÌNH
  MODE="no_ai": xử lý các nhánh NOAI; "ai": AI; "all": cả hai, không trộn.
  SOURCE_COUNTS=(1,): chỉ một nguồn; (1, 2, 3): mọi trường hợp có tiếng nói.
     Không xử lý 0source: các frame rỗng trong phép đo nhiễu phải được giữ.
  DISTANCES_M=(): mọi khoảng cách; (0.1,): chỉ 0.1m; (0.1, 0.2): hai khoảng.
  MIN_EMPTY_RUN=3: loại TOÀN BỘ chuỗi từ 3 frame rỗng LIÊN TIẾP trở lên.
     Chuỗi 3..10 hoặc dài hơn 10 đều bị loại. Muốn ngưỡng 10 thì sửa thành 10.
     Chuỗi ngắn hơn ngưỡng vẫn giữ, kể cả chuỗi ở đầu/cuối file.
  SAVE_OUTPUT=True: lưu bản lọc/nhật ký; False: chỉ xem kết quả, không ghi file.
  TOLERANCE_DEG: ngưỡng ghép góc để so sánh chỉ số trước/sau; KHÔNG dùng
     để chọn frame cần loại. Mặc định lấy cùng ngưỡng với measure_doa.py.

QUY TẮC LỌC
  Frame rỗng phải có detected_count=0 VÀ raw_angles trống (tương ứng DOA,0).
  Góc sai, thiếu/thừa nguồn nhưng còn ít nhất một dự đoán KHÔNG bị loại.
  File không đúng format AI3, thiếu/hỏng dòng, sample không liên tục hoặc
     nhãn thay đổi sẽ được báo lỗi, không tự giả thành khoảng nghỉ.
  Không thể lọc khoảng mất UART không có dòng CSV: dữ liệu hiện không có
     timestamp/số thứ tự DSP để biết bao nhiêu frame thực sự bị mất.
  Chỉ đọc các nhánh thu AI3, không đọc data/0.1m cũ, _archive hay _reports.

GIỚI HẠN QUAN TRỌNG CHO BÁO CÁO
  DOA,0 không chứng minh người nói đã nghỉ: có thể là bỏ sót tiếng nói.
  Bộ lọc này là heuristic theo đầu ra DOA, KHÔNG phải VAD/nhãn speech thật.
  filter_summary.csv ghi cả recall_all_frames và recall_retained_frames_doa_selected.
  Chỉ số sau lọc phụ thuộc lựa chọn frame theo đầu ra hệ thống; không dùng
     thay recall trên mọi frame hoặc so trực tiếp với paper có nhãn speech.
  Dùng cùng ngưỡng cho AI/NOAI vẫn không tạo ra nhãn hoạt động tiếng nói
     độc lập, vì mỗi hệ thống có thể loại một tập frame khác nhau.
  Muốn recall khi thực sự có tiếng nói: cần nhãn khoảng nghỉ từ âm thanh
     tham chiếu/VAD độc lập đã đồng bộ với thời điểm thu.

TRUY VẾT
  Giữ nguyên header AI3 và giá trị mọi cột của dòng giữ lại, kể cả sample gốc.
  sample có thể có khoảng trống sau lọc; KHÔNG đánh số lại để che frame đã loại.
  removed_runs.csv ghi sample bắt đầu/kết thúc và chiều dài từng đoạn đã loại.
  Không đưa bản lọc vào ACTION="analyze" của file đo (yêu cầu raw liên tục);
     chỉ số sau lọc xem trong filter_summary.csv của chính phiên xử lý.
  Dùng thư viện chuẩn Python, không cần mở COM, không cần pandas/Excel.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

if __package__:
    from .measure_doa import Stats, configure_terminal, csv_fields, csv_data_origin, file_data_origin, valid_csv_header, parse_line
    from .measure_doa import TOLERANCE_DEG as MEASURE_TOLERANCE
else:
    from measure_doa import Stats, configure_terminal, csv_fields, csv_data_origin, file_data_origin, valid_csv_header, parse_line
    from measure_doa import TOLERANCE_DEG as MEASURE_TOLERANCE

# ======================= CẤU HÌNH: SỬA TẠI ĐÂY =======================
MODE = "no_ai"           # "no_ai", "ai" hoặc "all"; không tự đổi firmware
SOURCE_COUNTS = (1,)     # (1,) một nguồn; (1, 2, 3) mọi số nguồn có tiếng nói
DISTANCES_M = ()         # () mọi khoảng cách; (0.1,) chỉ 0.1m; đơn vị mét
MIN_EMPTY_RUN = 3        # Loại chuỗi DOA,0 liên tiếp có độ dài >= giá trị này
SAVE_OUTPUT = True      # False: chỉ xem thống kê, KHÔNG tạo thư mục/file
TOLERANCE_DEG = MEASURE_TOLERANCE  # Chỉ tính chỉ số; không chọn frame theo sai số

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
OUTPUT_ROOT = DATA_ROOT / "_processed"  # Tách khỏi CSV raw và báo cáo raw


@dataclass(frozen=True)
class Settings:
    mode: str = MODE
    source_counts: tuple[int, ...] = SOURCE_COUNTS
    distances: tuple[float, ...] = DISTANCES_M
    min_empty_run: int = MIN_EMPTY_RUN
    save_output: bool = SAVE_OUTPUT
    tolerance: float = TOLERANCE_DEG
    data_root: Path = DATA_ROOT
    output_root: Path = OUTPUT_ROOT

    def validate(self):
        if self.mode not in ("no_ai", "ai", "all"):
            raise ValueError('MODE phải là "no_ai", "ai" hoặc "all".')
        if not self.source_counts or any(type(n) is not int or n not in (1, 2, 3)
                                         for n in self.source_counts):
            raise ValueError("SOURCE_COUNTS chỉ gồm 1, 2, 3; không lọc phép đo chỉ nhiễu.")
        if type(self.min_empty_run) is not int or self.min_empty_run < 1:
            raise ValueError("MIN_EMPTY_RUN phải là số nguyên >=1.")
        if type(self.save_output) is not bool:
            raise ValueError("SAVE_OUTPUT phải là True hoặc False.")
        if any(not math.isfinite(d) or d <= 0 for d in self.distances):
            raise ValueError("DISTANCES_M phải hữu hạn và >0 mét.")
        if not math.isfinite(self.tolerance) or not 0 <= self.tolerance <= 180:
            raise ValueError("TOLERANCE_DEG phải hữu hạn trong 0..180.")
        if not Path(self.output_root).resolve().is_relative_to(Path(self.data_root).resolve() / "_processed"):
            raise ValueError("Đầu ra phải ở trong data/_processed, không ghi lên nhánh raw.")


@dataclass(frozen=True)
class EmptyRun:
    start_sample: int
    end_sample: int
    frame_count: int


@dataclass
class Measurement:
    path: Path
    header: list[str]
    rows: list[dict[str, str]]
    truth: tuple[int, ...]
    distance: float
    mode: str
    sha256: str
    data_origin: str = "MEASURED"


def load_measurement(path, data_root):
    """Đọc một lần, kiểm tra CSV raw và tạo hash để truy vết đúng bản đầu vào."""
    path = Path(path).resolve()
    relative = path.relative_to(Path(data_root).resolve())
    content = path.read_bytes()
    content_sha256 = hashlib.sha256(content).hexdigest()
    registered_origin = file_data_origin(path, data_root, content_sha256)
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    header = reader.fieldnames or []
    n = sum(k.startswith("true_angle_") for k in header)
    if n not in (1, 2, 3) or not valid_csv_header(header, n):
        raise ValueError(f"{path.name}: cần header AI3 của 1..3 nguồn; không lọc CSV cũ/nhiễu.")
    branch = relative.parts[0]
    if branch not in (f"{n}sourceAI", f"{n}sourceNOAI"):
        raise ValueError(f"{path.name}: số nguồn/mode không khớp nhánh data raw.")
    rows, truth, distance, origin = [], None, None, None
    for line_number, row in enumerate(reader, 2):
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Thiếu/thừa cột.")
            if int(row["sample"]) != len(rows) + 1:
                raise ValueError("sample phải liên tục từ 1; không tự nối qua frame bị mất.")
            current_truth = tuple(int(row[f"true_angle_{i+1}"]) for i in range(n))
            if any(not 0 <= a < 360 for a in current_truth) or len(set(current_truth)) != n:
                raise ValueError("Góc thật ngoài miền hoặc bị trùng.")
            current_distance = float(row["distance_cm"]) / 100
            current_origin = csv_data_origin(row, registered_origin or "MEASURED")
            if registered_origin is not None and current_origin != registered_origin:
                raise ValueError("Nguồn trong CSV khác tệp nguồn dữ liệu.")
            if not math.isfinite(current_distance) or current_distance <= 0:
                raise ValueError("Khoảng cách không hợp lệ.")
            raw = row["raw_angles"].strip()
            frame = parse_line(f"DOA,{row['detected_count']}" + ("," + raw.replace(";", ",") if raw else ""))
            if frame is None:
                raise ValueError("detected_count/raw_angles hỏng hoặc không khớp.")
            if truth is not None and (current_truth != truth or current_distance != distance or current_origin != origin):
                raise ValueError("Nhãn góc/khoảng cách thay đổi trong cùng file.")
            truth, distance, origin = current_truth, current_distance, current_origin
            rows.append(row)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"{path.name}, dòng {line_number}: {exc}") from exc
    if not rows:
        raise ValueError(f"{path.name}: chỉ có header, chưa có dữ liệu để xử lý.")
    return Measurement(path, header, rows, truth, distance,
                       "ai" if branch == f"{n}sourceAI" else "no_ai",
                       content_sha256, origin)


def filter_empty_runs(rows, minimum):
    """Loại cả đoạn đủ ngưỡng; giữ thứ tự/sample gốc, không sửa giá trị dòng."""
    if type(minimum) is not int or minimum < 1:
        raise ValueError("Ngưỡng phải là số nguyên >=1.")
    kept, removed = [], []
    index = 0
    while index < len(rows):
        if int(rows[index]["detected_count"]) != 0 or rows[index]["raw_angles"].strip():
            kept.append(rows[index])
            index += 1
            continue
        start = index
        while (index < len(rows) and int(rows[index]["detected_count"]) == 0
               and not rows[index]["raw_angles"].strip()):
            index += 1
        if index - start >= minimum:
            removed.append(EmptyRun(int(rows[start]["sample"]),
                                    int(rows[index-1]["sample"]), index-start))
        else:
            kept.extend(rows[start:index])
    return kept, removed


def score_rows(rows, truth, tolerance):
    stats = Stats()
    for row in rows:
        detected = tuple(int(a) for a in row["raw_angles"].split(";") if a.strip())
        stats.add_frame(truth, detected, tolerance)
    return stats


def find_inputs(settings):
    modes = ("no_ai", "ai") if settings.mode == "all" else (settings.mode,)
    root = Path(settings.data_root).resolve()
    return sorted({path.resolve() for mode in modes for n in settings.source_counts
                   for path in (root / f"{n}source{'AI' if mode == 'ai' else 'NOAI'}").glob("**/*.csv")})


def write_table(path, header, rows):
    with Path(path).open("x", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def create_run_folder(settings):
    """Windows có thể trả cùng timestamp: thêm số phiên, không đè phiên trước."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base = f"empty_run_min{settings.min_empty_run}_{stamp}"
    attempt = 1
    while True:
        name = base if attempt == 1 else f"{base}_{attempt:02d}"
        folder = Path(settings.output_root) / name
        try:
            folder.mkdir(parents=True, exist_ok=False)
            return folder
        except FileExistsError:
            attempt += 1


def process_data(settings):
    settings.validate()
    paths = find_inputs(settings)
    if not paths:
        raise RuntimeError("Chưa có CSV raw AI3 trong nhánh MODE/SOURCE_COUNTS đã chọn.")
    print(f"Lọc chuỗi rỗng >= {settings.min_empty_run} frame; MODE={settings.mode}.")
    print("CẢNH BÁO: DOA,0 không xác nhận khoảng nghỉ. Recall sau lọc là chỉ số trên tập frame DOA được giữ.")
    summaries, audit, failures, run_root = [], [], 0, None
    for path in paths:
        try:
            measurement = load_measurement(path, settings.data_root)
            if settings.distances and not any(math.isclose(measurement.distance, d, rel_tol=0, abs_tol=1e-9)
                                              for d in settings.distances):
                continue
            kept, runs = filter_empty_runs(measurement.rows, settings.min_empty_run)
            before = score_rows(measurement.rows, measurement.truth, settings.tolerance)
            after = score_rows(kept, measurement.truth, settings.tolerance)
            filtered_path = None
            if settings.save_output:
                if run_root is None:
                    run_root = create_run_folder(settings)
                filtered_path = run_root / measurement.path.relative_to(Path(settings.data_root).resolve())
                filtered_path.parent.mkdir(parents=True, exist_ok=True)
                write_table(filtered_path, measurement.header, kept)
            summaries.append({
                "status": "ok", "source_file": str(path), "source_sha256": measurement.sha256,
                "filtered_file": str(filtered_path) if filtered_path is not None else "",
                "mode": measurement.mode, "data_origin": measurement.data_origin,
                "n_sources": len(measurement.truth),
                "true_angles": ";".join(map(str, measurement.truth)), "distance_m": measurement.distance,
                "min_empty_run": settings.min_empty_run, "tolerance_deg": settings.tolerance,
                "frames_before": before.frames, "frames_retained": after.frames,
                "frames_removed": before.frames - after.frames, "removed_runs": len(runs),
                "tp_before": before.tp, "fn_before": before.fn, "fp_before": before.fp,
                "tp_retained": after.tp, "fn_retained": after.fn, "fp_retained": after.fp,
                "recall_all_frames": before.metrics()["recall"],
                "recall_retained_frames_doa_selected": after.metrics()["recall"], "error": "",
            })
            audit.extend({"source_file": str(path), "start_sample": run.start_sample,
                          "end_sample": run.end_sample, "frame_count": run.frame_count,
                          "reason": "consecutive_empty_DOA_not_verified_silence"} for run in runs)
            relative = path.relative_to(Path(settings.data_root).resolve())
            print(f"{relative}: {before.frames} -> {after.frames} frame; loại {len(runs)} đoạn/{before.frames-after.frames} frame.")
        except (ValueError, OSError, UnicodeError) as exc:
            failures += 1
            summaries.append({"status": "error", "source_file": str(path), "error": str(exc)})
            print(f"KHÔNG xử lý: {exc}")
    if run_root is not None:
        successful = next((row for row in summaries if row["status"] == "ok"), None)
        header = list(successful) if successful is not None else ["status", "source_file", "error"]
        write_table(run_root / "filter_summary.csv", header, summaries)
        write_table(run_root / "removed_runs.csv",
                    ["source_file", "start_sample", "end_sample", "frame_count", "reason"], audit)
        note = ("# Lọc chuỗi frame DOA rỗng\n\n"
                f"Ngưỡng: >={settings.min_empty_run} frame liên tiếp; ghép góc ±{settings.tolerance}°.\n"
                f"Mode chọn: {settings.mode}; số nguồn: {settings.source_counts}; khoảng cách: {settings.distances or 'all'}.\n"
                f"Đã xử lý {sum(row['status'] == 'ok' for row in summaries)} file; lỗi {failures}. Xem filter_summary.csv.\n\n"
                "CSV gốc không bị sửa. Bản lọc giữ header AI3, góc raw và sample gốc, nên sample có thể có khoảng trống.\n"
                "removed_runs.csv ghi các khoảng sample bị loại; SHA256 nguồn trong filter_summary.csv giúp truy vết.\n\n"
                "DOA,0 không chứng minh khoảng nghỉ. Recall trên tập frame giữ lại bị điều kiện hóa theo đầu ra DOA,\n"
                "KHÔNG thay thế recall_all_frames, recall tiếng nói có nhãn hoặc kết quả paper.\n"
                "Đánh giá tiếng nói đúng cần nhãn hoạt động từ âm thanh tham chiếu/VAD độc lập, đồng bộ thời gian.\n"
                "Không đưa CSV lọc vào bộ analyze raw; chỉ số sau lọc nằm trong filter_summary.csv.\n")
        with (run_root / "README.md").open("x", encoding="utf-8") as handle:
            handle.write(note)
        print(f"Đã lưu bản xử lý riêng: {run_root}")
    elif not settings.save_output:
        print("Chỉ xem kết quả; KHÔNG tạo file/thư mục.")
    if not any(row["status"] == "ok" for row in summaries):
        print("Không có file được xử lý thành công: kiểm tra cảnh báo và khoảng cách đã chọn.")
    return run_root, summaries


def main():
    configure_terminal()
    try:
        _, summaries = process_data(Settings())
        return 0 if summaries and all(row["status"] == "ok" for row in summaries) else 1
    except KeyboardInterrupt:
        print("\nĐã dừng; dữ liệu raw không bị sửa. Phiên xử lý có thể chưa hoàn tất.")
        return 1
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Lỗi: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
