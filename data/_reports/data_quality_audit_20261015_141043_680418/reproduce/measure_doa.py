"""BỘ ĐO DOA THEO FORMAT AI3: BẤM RUN, NHẬP GÓC VÀ KHOẢNG CÁCH.

CÁCH DÙNG NHANH
  1. Sửa PORT, MODE, NUM_SAMPLES một lần trong khối CẤU HÌNH.
  2. Bấm Run. Nhập góc: 0 (một nguồn), 0;90 (hai), 0;90;180 (ba).
  3. Nhập khoảng cách bằng MÉT: 0.1, 0.2, 0.3... rồi Enter để bắt đầu thu.
  4. Recall hiển thị chỉ tính frame có góc, bỏ tất cả frame DOA,0.
     Recall dưới TARGET_RECALL thì tự đo thêm tối đa 3 lần cùng điều kiện.
     Một lần đạt ngưỡng thì dừng đo thêm; mỗi lần lưu một CSV riêng.
     Xong chương trình tự hỏi góc lần tiếp theo; q để thoát.
     Khoảng cách để trống = dùng lại khoảng cách lần trước.
  Không cần nhập lệnh dài, không cần sửa góc/khoảng cách trong code.

TRỰC QUAN HÓA LÀ FILE RIÊNG
  Mở visualize_doa.py rồi Run để xem radar UART, không lưu CSV.
  Đóng radar trước khi chạy file này: hai chương trình không dùng chung COM.
  File đo không mở cửa sổ, không có nút Thu và không cần Tkinter.
  Sau khi nhập góc/khoảng cách, làm sạch UART, bỏ DISCARD_FRAMES khởi động,
      rồi lưu TẤT CẢ frame hợp lệ như trước.

FORMAT ĐỒNG NHẤT VỚI AI3
  UART: DOA,0 hoặc DOA,n,goc1,...,gocN (n=0..3), kết thúc CR/LF.
  Giữ góc raw 0..359 như AI3; KHÔNG tự đảo, bù hay sửa góc để giảm sai số.
  CSV: sample,distance_cm,detected_count,raw_angles,
       true_angle_1..N,detected_angle_1..N,error_1..N,mean_error.
  raw_angles ngăn bằng dấu ;. Cột ghép/sai số chỉ có khi phát hiện ĐÚNG N
  nguồn, ghép hoán vị tối thiểu sai số như AI3; thiếu/thừa thì để trống.
  Mọi frame DOA hợp lệ vẫn được lưu, kể cả DOA,0. CSV không có cột AI giả.
  Terminal nhập mét, CSV distance_cm = mét * 100, đúng đơn vị AI3.

LƯU CỤ THỂ
  data/1sourceNOAI/0.1m/01_00dis01.csv
  data/2sourceAI/0.2m/01_00_90dis02.csv
  Tên file: <lần đo 2 chữ số>_<góc thật sắp tăng, ít nhất 2 chữ số>dis
            <khoảng cách theo bước 10 cm, ít nhất 2 chữ số>.csv
  dis01=0.1m; dis02=0.2m. Khoảng cách không tròn bước 0.1m được làm tròn
  mã dis giống AI3; folder/CSV luôn ghi khoảng cách thực, không mất độ chính xác.
  MODE chỉ đặt nhãn AI/NOAI, KHÔNG tự bật/tắt AI trên mạch.
  Chỉ nhiễu: nhập noise thay góc, lưu vào data/0sourceAI hoặc 0sourceNOAI.
  data/0.1m, 0.2m, 0.3m cũ được giữ nhưng đã lọc frame nên không tính recall.
  Báo cáo ở data/_reports/; bản sao trước khi dọn ở data/_archive/.

ĐÁNH GIÁ
  Sau mỗi lần thu: Recall/Precision/F1 tính trên frame có ít nhất một góc;
  frame rỗng vẫn lưu vào CSV. Không có frame có góc thì Recall=N/A.
  Đây là chỉ số trên frame có phát hiện, không phải nhãn tiếng nói/im lặng.
  ACTION="analyze" rồi Run để đọc lại CSV, không hỏi góc, không mở UART.
  Recall = TP/(TP+FN) trên MỌI frame, không bỏ frame rỗng như evaluator AI3 cũ.
  Ghép một-một trong ±TOLERANCE_DEG; tối đa TP trước, rồi tối thiểu sai số.
  Matched MAE chỉ tính cặp TP trong ngưỡng, KHÔNG phải mean_error của CSV.
  Không có TP thì Matched MAE=N/A; không có nguồn thật thì recall=N/A.
  Mọi nguồn khai báo được coi là hoạt động ở mọi frame. Podcast có khoảng
  im lặng cần nhãn theo thời gian riêng; chương trình chưa hỗ trợ nhãn đó.
  CSV đo không bị sửa khi analyze; các nhóm AI/NOAI/số nguồn/khoảng cách
  được tách riêng. Không quét probability vì DOA của AI3 không có trường này.

FIRMWARE GỐC FFT/B1/src/main.c
  AI_ENABLE=0: no_ai; AI_ENABLE=1 và USE_AI_FOR_PYTHON_TEST=1: ai.
  SEND_DOA_TEST_UART=1, SEND_EVAL_UART=0, SEND_DATASET_UART=0.
  Phải build/flash lại sau khi đổi firmware. Python không tự flash.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path

try:
    import serial
except ImportError:
    serial = None  # Phân tích offline vẫn chạy, chỉ thu UART mới cần pyserial.

# ======================= CẤU HÌNH: SỬA MỘT LẦN =======================
ACTION = "measure"  # "measure": thu CSV; "analyze": đánh giá CSV, không mở UART
PORT = "COM13"      # COM của mạch trong Device Manager; đóng app khác dùng COM
BAUD = 921600      # Baud UART phải giống main.c, KHÔNG phải sample rate âm thanh
MODE = "ai"      # "no_ai" -> folder NOAI; "ai" -> folder AI; khớp firmware
NUM_SAMPLES = 300 # Số FRAME hợp lệ mỗi file, gồm cả rỗng/thiếu/thừa nguồn
DISCARD_FRAMES = 30  # Bỏ frame khởi động; dùng cùng giá trị cho AI/NOAI
TIMEOUT_S = 180.0    # Giây tối đa mỗi lần đo; thiếu frame vẫn giữ CSV đã lưu
TOLERANCE_DEG = 15   # Ngưỡng ghép ±15°; dùng cùng ngưỡng để so sánh AI/NOAI

TARGET_RECALL = 0.95      # Recall trên frame có góc đạt 95% thì dừng đo thêm.
MAX_EXTRA_MEASUREMENTS = 6  # Sau lần đầu, tự đo thêm tối đa 6 lần.
    
# Không cấu hình góc/khoảng cách ở đây: chương trình hỏi trong terminal.
# Góc thật: nguyên 0..359, các nguồn không trùng góc; có thể cách bằng ; hoặc ,.
# Khoảng cách: số hữu hạn >0, đơn vị m, các nguồn cùng bán kính tới tâm mic.
# Quy ước bố trí: 0 trái, 90 dưới, 180 phải, 270 trên; đối chiếu raw trước đo.

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "data"  # TẤT CẢ CSV đo ở trong data/, ngoài Python
REPORT_ROOT = OUTPUT_ROOT / "_reports"  # Kết quả mới, không trộn CSV thu

# Analyze chỉ đọc nhánh AI3 mới, không đọc data/0.1m cũ đã lọc frame.
# Muốn một nhánh cụ thể: [OUTPUT_ROOT / "1sourceNOAI" / "0.2m"].
ANALYZE_FOLDERS = [
    OUTPUT_ROOT / f"{n}source{suffix}"
    for suffix in ("NOAI", "AI") for n in range(4)
]


@dataclass(frozen=True)
class Settings:
    action: str = ACTION
    port: str = PORT
    baud: int = BAUD
    mode: str = MODE
    frames: int = NUM_SAMPLES
    discard: int = DISCARD_FRAMES
    timeout: float = TIMEOUT_S
    tolerance: float = TOLERANCE_DEG
    output_root: Path = OUTPUT_ROOT
    report_root: Path = REPORT_ROOT
    analyze_folders: tuple[Path, ...] = tuple(ANALYZE_FOLDERS)
    true_angles: tuple[int, ...] = (0,)  # Nhận từ terminal, không sửa dòng này.
    distance: float = 0.1               # Nhận từ terminal, đơn vị mét.
    settle_seconds: float = 1.0

    def validate(self) -> None:
        if self.action not in ("measure", "analyze"):
            raise ValueError('ACTION phải là "measure" hoặc "analyze". Xem radar bằng visualize_doa.py.')
        if not math.isfinite(self.tolerance) or not 0 <= self.tolerance <= 180:
            raise ValueError("TOLERANCE_DEG phải hữu hạn trong 0..180.")
        for folder in (self.output_root, self.report_root):
            if Path(folder).resolve().is_relative_to(PROJECT_ROOT / "Python"):
                raise ValueError("CSV/báo cáo phải ở ngoài Python.")
        if self.action == "analyze":
            return
        if self.mode not in ("ai", "no_ai"):
            raise ValueError('MODE phải là "ai" hoặc "no_ai".')
        if len(self.true_angles) > 3 or any(type(a) is not int or not 0 <= a < 360 for a in self.true_angles):
            raise ValueError("Góc thật phải là 0..359; tối đa 3 nguồn.")
        if len(set(self.true_angles)) != len(self.true_angles):
            raise ValueError("Không khai báo các nguồn trùng góc.")
        if not math.isfinite(self.distance) or self.distance <= 0 or not math.isfinite(self.distance * 100):
            raise ValueError("Khoảng cách phải hữu hạn và >0 mét.")
        if type(self.frames) is not int or self.frames <= 0:
            raise ValueError("NUM_SAMPLES phải là số nguyên dương.")
        if type(self.discard) is not int or self.discard < 0:
            raise ValueError("DISCARD_FRAMES phải là số nguyên không âm.")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("TIMEOUT_S phải hữu hạn và >0.")
        if not math.isfinite(self.settle_seconds) or self.settle_seconds < 0:
            raise ValueError("Thời gian chờ khởi động không hợp lệ.")
        if type(self.baud) is not int or self.baud <= 0 or not self.port.strip():
            raise ValueError("PORT/BAUD không hợp lệ.")


@dataclass(frozen=True)
class Frame:
    angles: tuple[int, ...]


def parse_line(line: str) -> Frame | None:
    """Chỉ nhận đúng format DOA AI3; dòng hỏng không giả thành DOA,0."""
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 2 or parts[0] != "DOA":
        return None
    try:
        count = int(parts[1])
        angles = tuple(int(a) for a in parts[2:])
    except ValueError:
        return None
    if not 0 <= count <= 3 or len(angles) != count or any(not 0 <= a < 360 for a in angles):
        return None
    return Frame(angles)


class StreamParser:
    def __init__(self):
        self.buffer = bytearray()
        self.invalid_lines = 0
        self.wrong_protocol_lines = 0
        self.discard_until_newline = False

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        frames = []
        while b"\n" in self.buffer:
            line, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            if self.discard_until_newline:
                self.discard_until_newline = False
                continue
            try:
                decoded = line.decode("ascii").strip()
            except UnicodeDecodeError:
                self.invalid_lines += 1
                continue
            frame = parse_line(decoded)
            if frame is not None:
                frames.append(frame)
            elif decoded.startswith("DOA,"):
                self.invalid_lines += 1
            elif decoded.startswith("EVAL,"):
                self.wrong_protocol_lines += 1
        if len(self.buffer) > 4096:
            self.buffer.clear()
            self.discard_until_newline = True
            self.invalid_lines += 1
        return frames


def circular_error(measured: int, expected: int) -> int:
    difference = abs(measured - expected) % 360
    return min(difference, 360 - difference)


def match_sources(truth: tuple[int, ...], detected: tuple[int, ...], tolerance: float):
    """Đánh giá: tối đa TP trong ngưỡng, rồi tối thiểu sai số; không bỏ thiếu/thừa."""
    best, key = (), (0, 0)
    for assignment in itertools.product(range(-1, len(detected)), repeat=len(truth)):
        used = [d for d in assignment if d >= 0]
        if len(set(used)) != len(used):
            continue
        pairs = tuple((t, d, circular_error(truth[t], detected[d]))
                      for t, d in enumerate(assignment) if d >= 0)
        candidate = (-len(pairs), sum(error for _, _, error in pairs))
        if all(error <= tolerance for _, _, error in pairs) and candidate < key:
            best, key = pairs, candidate
    return best


@dataclass
class Stats:
    frames: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    count_correct: int = 0
    noise_frames: int = 0
    noise_fp_frames: int = 0
    errors: list[int] = field(default_factory=list)

    def add_frame(self, truth, detected, tolerance):
        pairs = match_sources(truth, detected, tolerance)
        self.frames += 1
        self.tp += len(pairs)
        self.fp += len(detected) - len(pairs)
        self.fn += len(truth) - len(pairs)
        self.count_correct += int(len(truth) == len(detected))
        self.errors.extend(error for _, _, error in pairs)
        if not truth:
            self.noise_frames += 1
            self.noise_fp_frames += int(bool(detected))

    def merge(self, other):
        for name in ("frames", "tp", "fp", "fn", "count_correct", "noise_frames", "noise_fp_frames"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.errors.extend(other.errors)

    def metrics(self):
        def ratio(n, d):
            return n / d if d else None
        return {
            "frames": self.frames, "tp": self.tp, "fp": self.fp, "fn": self.fn,
            "precision": ratio(self.tp, self.tp + self.fp),
            "recall": ratio(self.tp, self.tp + self.fn),
            "f1": ratio(2 * self.tp, 2 * self.tp + self.fp + self.fn),
            "matched_mae_deg": sum(self.errors) / len(self.errors) if self.errors else None,
            "count_accuracy": ratio(self.count_correct, self.frames),
            "noise_fp_rate": ratio(self.noise_fp_frames, self.noise_frames),
        }


def format_metric(value, percent=True):
    if value is None:
        return "N/A"
    return f"{value:.2%}" if percent else f"{value:.2f}°"


def print_summary(stats, nonempty_stats=None):
    selected = stats if nonempty_stats is None else nonempty_stats
    m = selected.metrics()
    if nonempty_stats is None:
        print(f"\nFrames={stats.frames} | TP={stats.tp} | FP={stats.fp} | FN={stats.fn}")
        recall_label = "Recall"
    else:
        print(f"\nFrames lưu CSV={stats.frames} | Có góc={selected.frames} | "
              f"Frame rỗng bỏ khỏi chỉ số={stats.frames - selected.frames}")
        print(f"TP={selected.tp} | FP={selected.fp} | FN={selected.fn} (trên frame có góc)")
        recall_label = "Recall (bỏ frame rỗng)"
    print(f"{recall_label}={format_metric(m['recall'])} | Precision={format_metric(m['precision'])} | F1={format_metric(m['f1'])}")
    print(f"Matched MAE (chỉ cặp TP trong ngưỡng)={format_metric(m['matched_mae_deg'], False)}")
    print(f"Đúng số lượng nguồn (không phải recall)={format_metric(m['count_accuracy'])}")
    if stats.noise_frames:
        print(f"Frame nhiễu có false positive={format_metric(m['noise_fp_rate'])}")


def csv_fields(n):
    """Header động giống AI3, không thêm cột protocol/probability hay metadata."""
    return (["sample", "distance_cm", "detected_count", "raw_angles"]
            + [f"true_angle_{i+1}" for i in range(n)]
            + [f"detected_angle_{i+1}" for i in range(n)]
            + [f"error_{i+1}" for i in range(n)] + ["mean_error"])


def valid_csv_header(header, n):
    """CSV thu nguyên bản hoặc CSV có cột truy vết nguồn dữ liệu."""
    fields = csv_fields(n)
    return header == fields or header == fields + ["data_origin"]


def csv_data_origin(row, default="MEASURED"):
    origin = row.get("data_origin", default)
    if origin not in ("MEASURED", "SYNTHETIC", "PROCESSED"):
        raise ValueError("data_origin phải là MEASURED, SYNTHETIC hoặc PROCESSED.")
    return origin


def file_data_origin(path, data_root=None, content_sha256=None):
    """Đọc nguồn từ tệp riêng khi CSV dùng header AI3 nguyên bản."""
    path = Path(path).resolve()
    if data_root is None:
        branches = {f"{n}source{mode}" for n in range(4) for mode in ("AI", "NOAI")}
        data_root = next((parent.parent for parent in path.parents if parent.name in branches), None)
        if data_root is None:
            return None
    root = Path(data_root).resolve()
    registry_path = root / "_data_sources.json"
    if not registry_path.is_file():
        return None
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("version") != 1 or not isinstance(registry.get("files"), dict):
        raise ValueError("Tệp nguồn dữ liệu không đúng định dạng.")
    entry = registry["files"].get(path.relative_to(root).as_posix())
    if entry is None:
        return None
    if not isinstance(entry, dict) or "data_origin" not in entry:
        raise ValueError("Mục nguồn dữ liệu không đúng định dạng.")
    origin = csv_data_origin(entry)
    checksum = content_sha256 or hashlib.sha256(path.read_bytes()).hexdigest()
    if entry.get("sha256") != checksum:
        raise ValueError("CSV khác bản đã ghi nguồn dữ liệu; cần cập nhật tệp nguồn trước khi đánh giá.")
    return origin


def data_origin_label(origin):
    return {"MEASURED": "Đo thực", "SYNTHETIC": "Mô phỏng", "PROCESSED": "Hậu xử lý"}[origin]


def csv_row(sample, truth, distance_m, detected):
    """Cột ghép/error theo AI3: chỉ có khi số dự đoán = số nguồn thật."""
    paired, errors, mean_error = [""] * len(truth), [""] * len(truth), ""
    if truth and len(detected) == len(truth):
        paired = min(itertools.permutations(detected),
                     key=lambda order: sum(circular_error(a, t) for a, t in zip(order, truth)))
        errors = [circular_error(a, t) for a, t in zip(paired, truth)]
        mean_error = f"{sum(errors) / len(errors):.2f}"
    return [sample, distance_m * 100, len(detected), ";".join(map(str, detected)),
            *truth, *paired, *errors, mean_error]


def output_folder(settings):
    suffix = "AI" if settings.mode == "ai" else "NOAI"
    distance = f"{settings.distance:.15g}"
    folder = settings.output_root / f"{len(settings.true_angles)}source{suffix}" / f"{distance}m"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def open_new_csv(settings):
    folder = output_folder(settings)
    angles = "_".join(f"{a:02d}" for a in sorted(settings.true_angles)) or "noise"
    distance_code = int(round(settings.distance * 100 / 10))
    run = 1
    while True:
        path = folder / f"{run:02d}_{angles}dis{distance_code:02d}.csv"
        try:
            return path, path.open("x", newline="", encoding="utf-8")
        except FileExistsError:
            run += 1


@dataclass
class CollectionResult:
    path: Path
    stats: Stats
    status: str
    nonempty_stats: Stats | None = None

    @property
    def display_stats(self) -> Stats:
        return self.stats if self.nonempty_stats is None else self.nonempty_stats


def collect(settings, serial_factory=None, clock=time.monotonic, sleep=time.sleep):
    settings.validate()
    if serial_factory is None:
        if serial is None:
            raise RuntimeError("Chưa có pyserial. Cài một lần: python -m pip install pyserial")
        serial_factory = serial.Serial
    truth = tuple(sorted(settings.true_angles))
    stats, parser = Stats(), StreamParser()
    nonempty_stats = Stats() if truth else None
    discarded, warned_eval, status = 0, False, "complete"
    with ExitStack() as resources:
        uart = resources.enter_context(serial_factory(settings.port, settings.baud,
                                                      timeout=0.1))
        sleep(settings.settle_seconds)
        uart.reset_input_buffer()
        path, handle = open_new_csv(settings)
        resources.enter_context(handle)
        writer = csv.writer(handle)
        writer.writerow(csv_fields(len(truth)))
        handle.flush()
        print(f"\nMODE={settings.mode}; góc={list(truth)}; {settings.distance} m; {settings.frames} frame")
        print("MODE phải khớp firmware; góc raw không bị đảo/bù.")
        print(f"Bắt đầu lưu: {path}")
        started = last_notice = clock()
        received_any = False
        try:
            while stats.frames < settings.frames:
                now = clock()
                if now - started >= settings.timeout:
                    status = "timeout"
                    break
                if not received_any and now - last_notice >= 5:
                    print("Chờ DOA: kiểm tra COM/baud, SEND_DOA_TEST_UART=1, SEND_EVAL_UART=0 và flash.")
                    last_notice = now
                frames = parser.feed(uart.read(4096))
                if parser.wrong_protocol_lines and not warned_eval:
                    print("Đang nhận EVAL, không phải AI3 DOA. Build/flash cấu hình DOA trong main.c.")
                    warned_eval = True
                if frames:
                    received_any = True
                for frame in frames:
                    if discarded < settings.discard:
                        discarded += 1
                        continue
                    frame_stats = Stats()
                    frame_stats.add_frame(truth, frame.angles, settings.tolerance)
                    writer.writerow(csv_row(stats.frames + 1, truth, settings.distance, frame.angles))
                    handle.flush()
                    stats.merge(frame_stats)
                    if nonempty_stats is not None and frame.angles:
                        nonempty_stats.merge(frame_stats)
                    if stats.frames == 1 or stats.frames % 25 == 0 or stats.frames == settings.frames:
                        print(f"{stats.frames}/{settings.frames} | DOA,{len(frame.angles)} | {list(frame.angles)}")
                    if stats.frames >= settings.frames:
                        break
        except KeyboardInterrupt:
            status = "interrupted"
        except OSError as exc:
            status = "serial_error"
            print(f"Lỗi UART/ghi file: {exc}")
    print(f"\n{status}: giữ {stats.frames}/{settings.frames} frame tại {path}. Dòng hỏng={parser.invalid_lines}; bỏ khởi động={discarded}.")
    print_summary(stats, nonempty_stats)
    return CollectionResult(path, stats, status, nonempty_stats)


def prompt_measurement(settings, input_fn=None):
    """Chỉ hai lần nhập: danh sách góc + khoảng cách mét. q/EOF hủy, chưa tạo CSV."""
    input_fn = input if input_fn is None else input_fn
    while True:
        try:
            text = input_fn("\nGóc thật 0–359 (VD 0 hoặc 0;90; q thoát; noise chỉ nhiễu): ").strip()
        except EOFError:
            return None
        if text.lower() in ("q", "quit", "exit"):
            return None
        try:
            truth = () if text.lower() == "noise" else tuple(int(a.strip()) for a in text.replace(",", ";").split(";"))
            candidate = replace(settings, true_angles=truth)
            candidate.validate()
            break
        except ValueError as exc:
            print(f"Góc không hợp lệ: {exc}")
    while True:
        try:
            text = input_fn(f"Khoảng cách MÉT (VD 0.1, 0.2; Enter={settings.distance:g}; q thoát): ").strip()
        except EOFError:
            return None
        if text.lower() in ("q", "quit", "exit"):
            return None
        try:
            distance = settings.distance if not text else float(text.replace(",", "."))
            candidate = replace(candidate, distance=distance)
            candidate.validate()
            return replace(candidate, true_angles=tuple(sorted(truth)))
        except ValueError as exc:
            print(f"Khoảng cách không hợp lệ: {exc}")


def measure_session(settings, input_fn=None, collector=None):
    collector = collect if collector is None else collector
    settings.validate()
    print("DOA AI3 | Nhập góc/khoảng cách rồi thu; q để dừng. MODE không đổi firmware.")
    while True:
        current = prompt_measurement(settings, input_fn)
        if current is None:
            return 0
        for extra in range(MAX_EXTRA_MEASUREMENTS + 1):
            result = collector(current)
            if result.status != "complete":
                print(f"Giữ CSV tại {result.path}.")
                return 1
            recall = result.display_stats.metrics()["recall"]
            if recall is None and not current.true_angles:
                print("Recall=N/A; không tự đo thêm cho lượt không có recall.")
                break
            if recall is not None and recall >= TARGET_RECALL:
                print(f"Recall (bỏ frame rỗng)={format_metric(recall)} đạt ngưỡng "
                      f"{format_metric(TARGET_RECALL)}; dừng đo thêm.")
                break
            if extra == MAX_EXTRA_MEASUREMENTS:
                reason = ("vẫn chưa có frame có góc để tính recall" if recall is None else
                          f"recall vẫn dưới {format_metric(TARGET_RECALL)}")
                print(f"Đã đo thêm đủ {MAX_EXTRA_MEASUREMENTS} lần; {reason}.")
                break
            reason = ("Recall=N/A vì chưa có frame có góc" if recall is None else
                      f"Recall (bỏ frame rỗng)={format_metric(recall)} dưới {format_metric(TARGET_RECALL)}")
            print(f"{reason}; "
                  f"tự đo thêm lần {extra + 1}/{MAX_EXTRA_MEASUREMENTS} với cùng góc/khoảng cách.")
        settings = current  # Nhớ khoảng cách, không cần mở/chạy lại file cho lần đo sau.


def infer_mode(path):
    """CSV AI3 không có mode: chỉ suy từ folder chính xác, không gán NOAI tùy tiện."""
    for parent in path.parents:
        if parent.name in {f"{n}sourceNOAI" for n in range(4)}:
            return "no_ai"
        if parent.name in {f"{n}sourceAI" for n in range(4)}:
            return "ai"
    raise ValueError("Không có folder <N>sourceAI/NOAI để xác định chế độ.")


def score_csv(path, settings):
    stats, metadata = Stats(), None
    registered_origin = file_data_origin(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        n = sum(k.startswith("true_angle_") for k in header)
        if n > 3 or not valid_csv_header(header, n):
            raise ValueError(f"{path.name}: không đúng header CSV AI3; không đọc CSV cũ đã lọc frame.")
        mode = infer_mode(path)
        for line_number, row in enumerate(reader, 2):
            try:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError("Dòng thiếu/thừa cột.")
                sample = int(row["sample"])
                if sample != stats.frames + 1:
                    raise ValueError("sample không liên tục từ 1; không bỏ/mất frame mà không báo.")
                truth = tuple(int(row[f"true_angle_{i+1}"]) for i in range(n))
                detected = tuple(int(a) for a in row["raw_angles"].split(";") if a.strip())
                if len(detected) > 3 or any(not 0 <= a < 360 for a in (*truth, *detected)):
                    raise ValueError("Góc/số nguồn ngoài miền hợp lệ.")
                if len(set(truth)) != len(truth):
                    raise ValueError("Góc thật bị trùng.")
                if int(row["detected_count"]) != len(detected):
                    raise ValueError("detected_count không khớp raw_angles.")
                distance = float(row["distance_cm"]) / 100
                if not math.isfinite(distance) or distance <= 0:
                    raise ValueError("distance_cm không hợp lệ.")
                origin = csv_data_origin(row, registered_origin or "MEASURED")
                if registered_origin is not None and origin != registered_origin:
                    raise ValueError("Nguồn trong CSV khác tệp nguồn dữ liệu.")
                current = {"mode": mode, "data_origin": origin,
                           "n_sources": n, "true_angles": ";".join(map(str, truth)),
                           "distance_m": distance, "tolerance_deg": settings.tolerance}
                if metadata is not None and current != metadata:
                    raise ValueError("Góc/khoảng cách thay đổi trong cùng file.")
                metadata = current
                stats.add_frame(truth, detected, settings.tolerance)  # Kể cả DOA,0.
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"{path.name}, dòng {line_number}: {exc}") from exc
    if metadata is None:
        raise ValueError(f"{path.name}: chưa có frame.")
    return metadata, stats


def analyze(settings):
    settings.validate()
    paths = sorted({p.resolve() for folder in settings.analyze_folders
                    for p in Path(folder).glob("**/*.csv")
                    if not {"_reports", "_archive", "_processed"}.intersection(p.parts)})
    rows, groups, failures = [], {}, 0
    for path in paths:
        try:
            metadata, stats = score_csv(path, settings)
        except (ValueError, OSError) as exc:
            failures += 1
            print(f"Không đọc được: {exc}")
            continue
        rows.append({"source_file": str(path), **metadata, **stats.metrics()})
        grouped = {k: v for k, v in metadata.items() if k != "true_angles"}
        key = tuple(grouped.items())
        if key not in groups:
            groups[key] = (grouped, Stats())
        groups[key][1].merge(stats)
    if not rows:
        raise RuntimeError("Chưa có CSV AI3 hợp lệ. Thu mới trước hoặc kiểm tra ANALYZE_FOLDERS.")
    for grouped, stats in groups.values():
        rows.append({"source_file": "OVERALL", **grouped, "true_angles": "all", **stats.metrics()})
    settings.report_root.mkdir(parents=True, exist_ok=True)
    summary = settings.report_root / "measurement_summary.csv"
    with summary.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = settings.report_root / "measurement_report.md"
    lines = ["# Đánh giá DOA – CSV AI3", "",
             "Recall trên mọi frame, ghép một-một trong ngưỡng; frame rỗng vẫn tính FN. Góc raw giữ nguyên.",
             "Matched MAE chỉ tính cặp TP trong ngưỡng, không phải mean_error của CSV AI3 (chỉ frame đúng số lượng).",
             "Mọi nguồn khai báo được coi là hoạt động ở mọi frame; podcast có khoảng nghỉ cần nhãn speech riêng.",
             "Dữ liệu mô phỏng và số đo thực được tổng hợp riêng theo nguồn dữ liệu.",
             f"Ngưỡng ±{settings.tolerance}°. Đã đọc {len(paths)-failures} file; lỗi {failures}. CSV gốc không bị sửa.", "",
             "| File | Mode | Loại dữ liệu | Nguồn | Góc thật | Mét | TP | FP | FN | Recall | Precision | F1 | Matched MAE |",
             "|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {Path(row['source_file']).name} | {row['mode']} | {data_origin_label(row['data_origin'])} | {row['n_sources']} | {row['true_angles']} | {row['distance_m']} | {row['tp']} | {row['fp']} | {row['fn']} | {format_metric(row['recall'])} | {format_metric(row['precision'])} | {format_metric(row['f1'])} | {format_metric(row['matched_mae_deg'], False)} |")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nĐã xuất: {summary}\n{report}")
    if failures:
        print("Có file lỗi bị bỏ; kiểm tra cảnh báo trước khi dùng báo cáo như kết quả đầy đủ.")
    return summary, report


def configure_terminal():
    """Windows/IDE có thể dùng cp1252: bật UTF-8 để lời nhắc tiếng Việt không lỗi."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass  # StringIO/terminal đặc biệt vẫn dùng cơ chế sẵn có.


def main():
    configure_terminal()
    settings = Settings()
    try:
        if settings.action == "analyze":
            analyze(settings)
            return 0
        return measure_session(settings)
    except (KeyboardInterrupt, EOFError):
        print("\nĐã dừng; CSV đã thu không bị xóa.")
        return 1
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Lỗi: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
