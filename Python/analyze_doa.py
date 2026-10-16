"""PHÂN TÍCH VÀ VẼ BIỂU ĐỒ CSV DOA ĐÃ THU — BẤM RUN, KHÔNG MỞ UART.

CÁCH DÙNG
  1. Thu xong dữ liệu. Chỉnh khối CẤU HÌNH bên dưới rồi bấm Run.
  2. Kết quả ở data/_reports/analysis_<thời điểm>/index.html.
     Trình duyệt tự mở báo cáo nếu OPEN_REPORT=True. Không cần Internet.
  3. Mỗi biểu đồ có file SVG riêng (ảnh vector, phóng to không vỡ), dùng để
     chèn vào báo cáo. Kèm CSV thống kê theo file, góc và khoảng cách.

Ý NGHĨA CẤU HÌNH
  DATA_MODE="raw": chỉ dữ liệu gốc, tính recall trên TẤT CẢ frame đã thu.
  DATA_MODE="filtered": chỉ bản lọc đã lưu bởi process_doa.py.
  DATA_MODE="compare": so sánh raw và filtered trên CÙNG các file nguồn.
     Hai chế độ sau yêu cầu chạy process_doa.py trước; không tự lọc ngầm.
  PROCESSED_SESSION="": tự chọn phiên lọc hoàn tất mới nhất.
     Muốn phiên cụ thể: nhập đường dẫn folder trong data/_processed.
  MODE="no_ai": NOAI; "ai": AI; "all": cả hai. Không tự bật/tắt AI trên mạch.
  SOURCE_COUNTS=(1,): một nguồn; (1, 2, 3): mọi số nguồn có tiếng nói.
  DISTANCES_M=(): mọi khoảng cách; (0.1,): chỉ 0.1m; (0.1, 0.2): hai khoảng.
  DETAIL_FILE="": vẽ thêm diễn biến frame của file đầu tiên được chọn.
     Muốn file cụ thể: "1sourceNOAI/0.2m/01_00dis02.csv", tính từ data/.
  TOLERANCE_DEG: ngưỡng ghép một-một để tính TP/FP/FN, recall/precision/F1.
     Mặc định cùng ngưỡng với file đo, không làm đẹp hay thay đổi góc raw.
  OPEN_REPORT=True: mở HTML sau khi xong; False: chỉ lưu, tự mở index.html.

CHỈ SỐ VÀ BIỂU ĐỒ
  Recall = TP/(TP+FN), precision = TP/(TP+FP), F1; không bỏ frame DOA,0.
  MAE/RMSE/median/P90 equal-count: ghép góc tối thiểu sai số trên frame phát
     hiện ĐÚNG số nguồn. Tính sai số vòng 0..180°, KHÔNG cắt ở ngưỡng TP.
  Matched MAE: chỉ cặp TP trong ngưỡng; khác MAE equal-count, luôn ghi rõ.
  Nhóm lặp cùng điều kiện cộng TP/FP/FN rồi tính tỷ lệ, không lấy trung bình
     phần trăm giữa file 600 và 1800 frame. Các frame không độc lập hoàn toàn;
     chương trình không tự gán khoảng tin cậy hay kiểm định thống kê.
  Biểu đồ: recall/precision/F1 theo khoảng cách; MAE/RMSE theo khoảng cách;
     recall và MAE theo góc; góc thật so với trung bình vòng góc dự đoán;
     góc raw theo sample để xem frame rỗng và khoảng bị loại.
  Biểu đồ theo góc chỉ cho một nguồn; nhiều nguồn được nhóm theo tổ hợp
     góc trong CSV, không gán recall tổng của tổ hợp cho một góc riêng.
  Đường nối chỉ hỗ trợ đọc xu hướng giữa các góc đã đo, không thêm mẫu đo.

GIỚI HẠN / TRUY VẾT
  Mọi nguồn khai báo được giả định hoạt động ở mọi frame. Recall ở đây là
     DOA theo nhãn góc, không phải recall classifier tiếng người/nhiễu.
  Filtered là tập frame lựa chọn theo đầu ra DOA, KHÔNG phải nhãn khoảng
     nghỉ độc lập; không dùng thay recall raw hoặc so trực tiếp với paper.
  So sánh kiểm tra SHA256 nguồn và các dòng giữ lại, không ghép file đã
     thu lại/đổi nội dung. File không có bản lọc tương ứng bị loại khỏi CẢ
     hai vế so sánh và được liệt kê rõ trong analysis_errors.csv.
  Lọc frame rỗng không thay đổi MAE equal-count của các góc đã phát hiện.
  CSV/bản lọc gốc không bị sửa; mỗi Run tạo một folder báo cáo mới.
  Không đọc data/0.1m cũ, _archive, _reports hay nhập lẫn các phiên lọc.
  Chỉ dùng thư viện chuẩn Python; không cần matplotlib/pandas/Excel.
"""

from __future__ import annotations

import csv
import itertools
import math
import statistics
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path

if __package__:
    from . import process_doa as process
    from .measure_doa import Stats, circular_error, configure_terminal, TOLERANCE_DEG
else:
    import process_doa as process
    from measure_doa import Stats, circular_error, configure_terminal, TOLERANCE_DEG

# ======================= CẤU HÌNH: SỬA TẠI ĐÂY =======================
DATA_MODE = "raw"        # "raw", "filtered", "compare" (cần chạy process_doa trước)
PROCESSED_SESSION = ""   # "": phiên lọc hoàn tất mới nhất; hoặc đường dẫn folder
MODE = "no_ai"           # "no_ai", "ai", "all"; nhãn đọc data, không đổi firmware
SOURCE_COUNTS = (1,)     # (1,) một nguồn; (1, 2, 3) mọi trường hợp có tiếng nói
DISTANCES_M = ()         # () mọi khoảng cách; (0.1,) chỉ 0.1m; đơn vị mét
DETAIL_FILE = ""         # "": file đầu tiên; hoặc đường dẫn CSV tương đối từ data/
OPEN_REPORT = True       # Tự mở HTML bằng trình duyệt sau khi lưu kết quả
# TOLERANCE_DEG được lấy từ measure_doa.py; sửa ở đó để các công cụ đồng nhất.

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
REPORT_ROOT = DATA_ROOT / "_reports"
POPULATION_NOTE = ("RAW: mọi frame, giả định các nguồn luôn hoạt động. FILTERED: chỉ frame giữ lại theo DOA; "
                   "không phải recall tiếng nói có nhãn độc lập. MAE/RMSE chỉ tính frame đúng số nguồn, không cắt ngưỡng TP. "
                   "Dữ liệu mô phỏng tách riêng khỏi số đo trong tổng hợp và biểu đồ.")


@dataclass(frozen=True)
class Settings:
    data_mode: str = DATA_MODE
    processed_session: str = PROCESSED_SESSION
    mode: str = MODE
    source_counts: tuple[int, ...] = SOURCE_COUNTS
    distances: tuple[float, ...] = DISTANCES_M
    detail_file: str = DETAIL_FILE
    open_report: bool = OPEN_REPORT
    tolerance: float = TOLERANCE_DEG
    data_root: Path = DATA_ROOT
    report_root: Path = REPORT_ROOT

    def validate(self):
        if self.data_mode not in ("raw", "filtered", "compare"):
            raise ValueError('DATA_MODE phải là "raw", "filtered" hoặc "compare".')
        process.Settings(mode=self.mode, source_counts=self.source_counts, distances=self.distances,
                         tolerance=self.tolerance, data_root=self.data_root,
                         output_root=Path(self.data_root) / "_processed").validate()
        if type(self.open_report) is not bool:
            raise ValueError("OPEN_REPORT phải là True hoặc False.")
        if not Path(self.report_root).resolve().is_relative_to(Path(self.data_root).resolve() / "_reports"):
            raise ValueError("Báo cáo phải ở trong data/_reports, không ghi vào nhánh raw.")


@dataclass
class Record:
    measurement: process.Measurement
    dataset: str
    rows: list[dict[str, str]]
    min_empty_run: int | None = None


@dataclass
class Aggregate:
    stats: Stats = field(default_factory=Stats)
    equal_errors: list[int] = field(default_factory=list)
    bearing_cos: float = 0.0
    bearing_sin: float = 0.0
    bearing_count: int = 0
    files: int = 0

    def add(self, record, tolerance):
        self.files += 1
        truth = record.measurement.truth
        for row in record.rows:
            detected = tuple(int(a) for a in row["raw_angles"].split(";") if a.strip())
            self.stats.add_frame(truth, detected, tolerance)
            if len(detected) == len(truth):
                paired = min(itertools.permutations(detected),
                             key=lambda angles: sum(circular_error(a, t) for a, t in zip(angles, truth)))
                self.equal_errors.extend(circular_error(a, t) for a, t in zip(paired, truth))
                if len(truth) == 1:
                    theta = math.radians(paired[0])
                    self.bearing_cos += math.cos(theta)
                    self.bearing_sin += math.sin(theta)
                    self.bearing_count += 1

    def metrics(self, include_bearing=False):
        errors = sorted(self.equal_errors)
        position = (len(errors)-1) * 0.9 if errors else 0
        low, high = math.floor(position), math.ceil(position)
        mean_bearing = None
        if (include_bearing and self.bearing_count
                and math.hypot(self.bearing_cos, self.bearing_sin) > 1e-12 * self.bearing_count):
            mean_bearing = math.degrees(math.atan2(self.bearing_sin, self.bearing_cos)) % 360
            if math.isclose(mean_bearing, 360, rel_tol=0, abs_tol=1e-9):
                mean_bearing = 0.0
        return {"files": self.files, **self.stats.metrics(), "equal_count_error_pairs": len(errors),
                "mae_equal_count_deg": statistics.fmean(errors) if errors else None,
                "rmse_equal_count_deg": math.sqrt(statistics.fmean(e*e for e in errors)) if errors else None,
                "median_equal_count_deg": statistics.median(errors) if errors else None,
                "p90_equal_count_deg": errors[low] + (errors[high]-errors[low])*(position-low) if errors else None,
                "mean_bearing_deg": mean_bearing}


def select_processed_session(settings):
    root = Path(settings.data_root).resolve() / "_processed"
    if settings.processed_session:
        selected = Path(settings.processed_session).resolve()
        if not selected.is_relative_to(root):
            raise ValueError("PROCESSED_SESSION phải nằm trong data/_processed.")
    else:
        candidates = [p for p in root.glob("*") if p.is_dir()
                      and (p / "filter_summary.csv").is_file() and (p / "README.md").is_file()]
        if not candidates:
            raise RuntimeError("Chưa có phiên lọc hoàn tất. Chạy process_doa.py trước hoặc DATA_MODE='raw'.")
        selected = max(candidates, key=lambda p: (p.stat().st_mtime_ns, p.name))
    if not (selected / "filter_summary.csv").is_file() or not (selected / "README.md").is_file():
        raise ValueError("Phiên lọc chưa hoàn tất/thiếu summary hoặc README.")
    return selected


def read_manifest(session):
    entries = {}
    with (session / "filter_summary.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != "ok":
                continue
            source = Path(row["source_file"]).resolve()
            if source in entries:
                raise ValueError("Phiên lọc có source_file trùng, không ghép tùy tiện.")
            entries[source] = row
    return entries


def validated_filtered_rows(measurement, entry, session):
    if entry["source_sha256"] != measurement.sha256:
        raise ValueError("SHA256 nguồn khác lúc lọc: nguồn đã thay đổi, cần chạy process_doa.py lại.")
    path = Path(entry["filtered_file"]).resolve()
    if not path.is_relative_to(session.resolve()):
        raise ValueError("filtered_file nằm ngoài phiên đã chọn.")
    minimum = int(entry["min_empty_run"])
    expected, _ = process.filter_empty_runs(measurement.rows, minimum)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != measurement.header:
            raise ValueError("Header bản lọc khác CSV nguồn.")
        rows = list(reader)
    if rows != expected:
        raise ValueError("Bản lọc không khớp quy tắc/dòng nguồn; không so sánh dữ liệu đã bị sửa.")
    return rows, minimum


def load_records(settings):
    settings.validate()
    selector = process.Settings(mode=settings.mode, source_counts=settings.source_counts,
                                data_root=settings.data_root, output_root=Path(settings.data_root) / "_processed")
    session = select_processed_session(settings) if settings.data_mode != "raw" else None
    manifest = read_manifest(session) if session is not None else {}
    records, errors = [], []
    for path in process.find_inputs(selector):
        try:
            measurement = process.load_measurement(path, settings.data_root)
            if settings.distances and not any(math.isclose(measurement.distance, d, rel_tol=0, abs_tol=1e-9)
                                              for d in settings.distances):
                continue
            filtered, minimum = None, None
            if session is not None:
                if measurement.path not in manifest:
                    raise ValueError("Không có bản lọc hợp lệ tương ứng trong phiên đã chọn; bỏ cả hai vế.")
                filtered, minimum = validated_filtered_rows(measurement, manifest[measurement.path], session)
            if settings.data_mode != "filtered":
                dataset = {"SYNTHETIC": "SYNTHETIC", "PROCESSED": "PROCESSED"}.get(measurement.data_origin, "RAW")
                records.append(Record(measurement, dataset, measurement.rows))
            if filtered is not None:
                dataset = {"SYNTHETIC": "SYNTHETIC_FILTERED", "PROCESSED": "PROCESSED_FILTERED"}.get(measurement.data_origin, "FILTERED")
                records.append(Record(measurement, dataset, filtered, minimum))
        except (ValueError, OSError, UnicodeError, KeyError) as exc:
            errors.append({"source_file": str(path), "error": str(exc)})
            print(f"Bỏ file: {path.name}: {exc}")
    if not records:
        raise RuntimeError("Không có dữ liệu hợp lệ phù hợp cấu hình; kiểm tra các cảnh báo/phiên lọc.")
    return records, errors, session


def summarize(records, tolerance):
    files, conditions, distances = [], {}, {}
    for record in records:
        m = record.measurement
        base = {"dataset": record.dataset, "data_origin": m.data_origin, "mode": m.mode, "n_sources": len(m.truth),
                "distance_m": m.distance, "true_angles": ";".join(map(str, m.truth)),
                "min_empty_run": record.min_empty_run, "tolerance_deg": tolerance}
        aggregate = Aggregate()
        aggregate.add(record, tolerance)
        files.append({"source_file": str(m.path), "source_sha256": m.sha256,
                      **base, **aggregate.metrics(include_bearing=True)})
        for groups, key in ((conditions, (record.dataset, m.mode, len(m.truth), m.distance, m.truth, record.min_empty_run)),
                            (distances, (record.dataset, m.mode, len(m.truth), m.distance, (), record.min_empty_run))):
            if key not in groups:
                groups[key] = ({**base, "true_angles": ";".join(map(str, key[4])) or "all_measured_angles"}, Aggregate())
            groups[key][1].add(record, tolerance)
    condition_rows = [{**base, **agg.metrics(include_bearing=True)} for base, agg in conditions.values()]
    distance_rows = [{**base, **agg.metrics()} for base, agg in distances.values()]
    return files, condition_rows, distance_rows


def dataset_label(dataset):
    return {"SYNTHETIC": "Mô phỏng", "SYNTHETIC_FILTERED": "Mô phỏng sau lọc",
            "PROCESSED": "Hậu xử lý", "PROCESSED_FILTERED": "Hậu xử lý sau lọc"}.get(dataset, dataset)


def label(row, with_distance=False):
    text = f"{dataset_label(row['dataset'])} · {'AI' if row['mode'] == 'ai' else 'NOAI'}"
    if row["dataset"].endswith("FILTERED"):
        text += f" ≥{row['min_empty_run']}f"
    if with_distance:
        text += f" · {row['distance_m']:g}m"
    return text


def make_series(rows, x_field, y_field, with_distance=False, bearing=False):
    groups = {}
    for row in rows:
        x = float(row[x_field])
        y = row[y_field]
        if bearing and y is not None:
            y = x + ((y-x+180) % 360 - 180)  # Chỉ tọa độ vẽ, không sửa góc CSV.
        groups.setdefault(label(row, with_distance), []).append((x, y))
    return [(name, sorted(points)) for name, points in sorted(groups.items())]


COLORS = ("#2563eb", "#ea580c", "#059669", "#9333ea", "#db2777", "#0891b2", "#854d0e", "#475569")


def line_chart(title, x_label, y_label, series, *, y_bounds=None, points_only=False,
               diagonal=False, empty_samples=()):
    """SVG chuẩn, không JavaScript/thư viện ngoài; thiếu dữ liệu không vẽ thành zero."""
    width, plot_top, plot_bottom = 920, 55, 345
    left, right = 76, 892
    legend_rows = math.ceil(len(series) / 3)
    height = 423 + 25 * legend_rows + (20 if empty_samples else 0)
    all_x = [x for _, points in series for x, _ in points] + list(empty_samples)
    valid = [(x, y) for _, points in series for x, y in points if y is not None]
    x_min, x_max = (min(all_x), max(all_x)) if all_x else (0, 1)
    if x_min == x_max:
        x_min, x_max = x_min-0.5, x_max+0.5
    if y_bounds is not None:
        y_min, y_max = y_bounds
        y_ticks = [y_min + (y_max-y_min)*i/5 for i in range(6)]
    else:
        values = [y for _, y in valid] + ([x_min, x_max] if diagonal else [])
        y_min, y_max = (min(0, min(values)), max(values)) if values else (0, 1)
        pad = max(1, (y_max-y_min)*0.08)
        y_min, y_max = (y_min-pad if y_min < 0 else y_min), y_max+pad
        rough_step = (y_max-y_min)/5
        scale = 10 ** math.floor(math.log10(rough_step))
        step = next(factor*scale for factor in (1, 2, 2.5, 5, 10) if factor*scale >= rough_step)
        y_min, y_max = math.floor(y_min/step)*step, math.ceil(y_max/step)*step
        y_ticks = [y_min + i*step for i in range(round((y_max-y_min)/step)+1)]
    observed_x = sorted(set(all_x))
    x_ticks = observed_x if 0 < len(observed_x) <= 12 else [x_min+(x_max-x_min)*i/5 for i in range(6)]
    px = lambda x: left + (x-x_min)/(x_max-x_min)*(right-left)
    py = lambda y: plot_bottom - (y-y_min)/(y_max-y_min)*(plot_bottom-plot_top)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
             f'<title>{escape(title)}</title>',
             f'<desc>{escape(POPULATION_NOTE)}</desc>',
             f'<rect width="{width}" height="{height}" fill="white"/>',
             '<g font-family="Arial, sans-serif" font-size="13" fill="#334155">',
             f'<text x="{left}" y="28" font-size="18" font-weight="bold">{escape(title)}</text>']
    for x in x_ticks:
        parts += [f'<path d="M {px(x):.2f} {plot_top} V {plot_bottom}" stroke="#e2e8f0"/>',
                  f'<text x="{px(x):.2f}" y="{plot_bottom+23}" text-anchor="middle">{x:.3g}</text>']
    for y in y_ticks:
        parts += [f'<path d="M {left} {py(y):.2f} H {right}" stroke="#e2e8f0"/>',
                  f'<text x="{left-9}" y="{py(y)+4:.2f}" text-anchor="end">{y:.3g}</text>']
    parts += [f'<path d="M {left} {plot_top} V {plot_bottom} H {right}" fill="none" stroke="#64748b"/>',
              f'<text x="{(left+right)/2}" y="{plot_bottom+48}" text-anchor="middle">{escape(x_label)}</text>',
              f'<text transform="translate(19 {(plot_top+plot_bottom)/2}) rotate(-90)" text-anchor="middle">{escape(y_label)}</text>']
    if diagonal:
        parts.append(f'<path d="M {px(x_min):.2f} {py(x_min):.2f} L {px(x_max):.2f} {py(x_max):.2f}" stroke="#64748b" stroke-dasharray="6 4"/>')
        parts.append(f'<text x="{right}" y="43" text-anchor="end" font-size="12">Nét đứt xám: lý tưởng y=x</text>')
    if not valid:
        parts.append(f'<text x="{(left+right)/2}" y="200" text-anchor="middle">Không có giá trị hợp lệ (N/A), không thay bằng 0.</text>')
    for index, (name, points) in enumerate(series):
        color = COLORS[index % len(COLORS)]
        dash = ' stroke-dasharray="6 4"' if "FILTERED" in name else ""
        segment = []
        def flush():
            if len(segment) > 1 and (not points_only or name.startswith("Góc thật ")):
                parts.append(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
            segment.clear()
        for x, y in points:
            if y is None:
                flush()
                continue
            segment.append(f"{px(x):.2f},{py(y):.2f}")
            tooltip = escape(f"{name}; x={x:g}; y={y:.4g}")
            parts.append(f'<circle cx="{px(x):.2f}" cy="{py(y):.2f}" r="3.1" fill="{color}" opacity="0.8"><title>{tooltip}</title></circle>')
        flush()
        lx, ly = left + (index % 3)*280, 412 + (index // 3)*25
        parts += [f'<path d="M {lx} {ly-4} h 22" stroke="{color}" stroke-width="3"{dash}/>',
                  f'<text x="{lx+29}" y="{ly}" font-size="12">{escape(name)}</text>']
    if empty_samples:
        for sample in empty_samples:
            parts.append(f'<path d="M {px(sample):.2f} {plot_bottom+3} v 7" stroke="#dc2626" stroke-width="2"/>')
        parts.append(f'<text x="{left}" y="{height-10}" fill="#b91c1c" font-size="12">Vạch đỏ dưới trục: DOA,0 (không phải góc 0°).</text>')
    parts.append("</g></svg>")
    return "\n".join(parts)


def create_charts(records, conditions, distances, settings):
    charts = []
    for n in sorted({row["n_sources"] for row in distances}):
        distance_rows = [row for row in distances if row["n_sources"] == n]
        for metric, title, axis, bounds in (
                ("recall", "Recall", "Recall (%)", (0, 100)),
                ("precision", "Precision", "Precision (%)", (0, 100)),
                ("f1", "F1", "F1 (%)", (0, 100)),
                ("mae_equal_count_deg", "MAE đúng số nguồn", "MAE vòng (°)", None),
                ("rmse_equal_count_deg", "RMSE đúng số nguồn", "RMSE vòng (°)", None)):
            if bounds:
                title += f" (±{settings.tolerance:g}°)"
            series = make_series(distance_rows, "distance_m", metric)
            if bounds:
                series = [(name, [(x, y*100 if y is not None else None) for x, y in points]) for name, points in series]
            charts.append((f"{n}source_{metric}_distance.svg", f"{title} theo khoảng cách · {n} nguồn",
                           line_chart(f"{title} theo khoảng cách · {n} nguồn", "Khoảng cách (m)", axis, series, y_bounds=bounds)))
    single = [dict(row, angle_deg=int(row["true_angles"])) for row in conditions if row["n_sources"] == 1]
    if single:
        for metric, title, axis, bounds in (
                ("recall", "Recall theo góc", "Recall (%)", (0, 100)),
                ("mae_equal_count_deg", "MAE theo góc", "MAE vòng (°)", None),
                ("mean_bearing_deg", "Góc thật và góc dự đoán trung bình vòng", "Góc dự đoán TB vòng (°)", None)):
            if bounds:
                title += f" (±{settings.tolerance:g}°)"
            series = make_series(single, "angle_deg", metric, with_distance=True, bearing=metric == "mean_bearing_deg")
            if bounds:
                series = [(name, [(x, y*100 if y is not None else None) for x, y in points]) for name, points in series]
            charts.append((f"1source_{metric}_angle.svg", title,
                           line_chart(title, "Góc thật đã đo (°)", axis, series, y_bounds=bounds, diagonal=metric == "mean_bearing_deg")))
    chosen = records[0].measurement.path
    if settings.detail_file:
        candidate = Path(settings.detail_file)
        chosen = (candidate if candidate.is_absolute() else Path(settings.data_root) / candidate).resolve()
        if not any(record.measurement.path == chosen for record in records):
            raise ValueError("DETAIL_FILE không thuộc các file hợp lệ đã chọn.")
    for record in records:
        if record.measurement.path != chosen:
            continue
        points, empty = [], []
        for row in record.rows:
            sample = int(row["sample"])
            angles = [int(a) for a in row["raw_angles"].split(";") if a.strip()]
            points.extend((sample, angle) for angle in angles)
            if not angles:
                empty.append(sample)
        series = [(f"{dataset_label(record.dataset)}: góc raw", points)]
        if record.rows:
            lo, hi = int(record.rows[0]["sample"]), int(record.rows[-1]["sample"])
            series.extend((f"Góc thật {angle}°", [(lo, angle), (hi, angle)]) for angle in record.measurement.truth)
        title = f"{dataset_label(record.dataset)} · {chosen.name} · {record.measurement.distance:g}m"
        # Mọi điểm, không downsample. Sample bản lọc có khoảng trống đúng dữ liệu gốc.
        charts.append((f"detail_{record.dataset.lower()}.svg", title,
                       line_chart(title, "Sample gốc (frame đã thu)", "Góc raw (°)", series,
                                  y_bounds=(0, 360), points_only=True, empty_samples=empty)))
    return charts


def value_text(value, percent=False):
    if value is None:
        return "N/A"
    return f"{value*100:.2f}%" if percent else f"{value:.2f}"


def results_table(rows):
    columns = [("dataset", "Tập frame"), ("mode", "Mode"), ("n_sources", "Nguồn"),
               ("distance_m", "Mét"), ("files", "File"), ("frames", "Frame"),
               ("recall", "Recall"), ("precision", "Precision"), ("f1", "F1"),
               ("mae_equal_count_deg", "MAE đúng số nguồn (°)"), ("rmse_equal_count_deg", "RMSE (°)")]
    output = ["<table><thead><tr>" + "".join(f"<th>{escape(title)}</th>" for _, title in columns) + "</tr></thead><tbody>"]
    for row in sorted(rows, key=lambda r: (r["n_sources"], r["distance_m"], r["mode"], r["dataset"])):
        cells = []
        for key, _ in columns:
            value = row[key]
            if key == "dataset":
                value = dataset_label(value)
            elif key in ("recall", "precision", "f1"):
                value = value_text(value, True)
            elif key.endswith("_deg"):
                value = value_text(value)
            cells.append(f"<td>{escape(str(value))}</td>")
        output.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(output) + "</tbody></table>"


def unique_report_folder(settings):
    base = "analysis_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    attempt = 1
    while True:
        name = base if attempt == 1 else f"{base}_{attempt:02d}"
        path = Path(settings.report_root) / name
        try:
            path.mkdir(parents=True, exist_ok=False)
            return path
        except FileExistsError:
            attempt += 1


def analyze_data(settings):
    records, errors, session = load_records(settings)
    files, conditions, distances = summarize(records, settings.tolerance)
    charts = create_charts(records, conditions, distances, settings)
    output = unique_report_folder(settings)
    for name, rows in (("per_file.csv", files), ("by_angle_configuration.csv", conditions), ("by_distance.csv", distances)):
        process.write_table(output / name, list(rows[0]), rows)
    process.write_table(output / "analysis_errors.csv", ["source_file", "error"], errors)
    cards = []
    for filename, title, svg in charts:
        with (output / filename).open("x", encoding="utf-8") as handle:
            handle.write(svg)
        cards.append(f'<section class="card"><h2>{escape(title)}</h2><a href="{filename}">Mở/lưu SVG</a>{svg}</section>')
    real_files = len({record.measurement.path for record in records})
    note = (f"{real_files} file nguồn hợp lệ; {len(errors)} file bị bỏ/có lỗi. "
            f"DATA_MODE={settings.data_mode}; MODE={settings.mode}; ngưỡng TP ±{settings.tolerance}°.")
    coverage = "; ".join(f"{row['distance_m']:g}m: {row['true_angles']}°" for row in conditions
                         if row["n_sources"] == 1 and row["dataset"] == records[0].dataset)
    session_text = str(session) if session is not None else "Không dùng phiên lọc"
    html = ("<!doctype html><html lang='vi'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Phân tích DOA</title>"
            "<style>body{font:15px Arial,sans-serif;color:#172033;background:#f1f5f9;margin:0}"
            "main{max-width:1400px;margin:auto;padding:24px}h1{margin:0 0 12px}h2{font-size:17px}"
            ".note{background:#fff7ed;border-left:4px solid #ea580c;padding:14px;line-height:1.5}"
            ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:18px}"
            ".card{background:white;padding:16px;border-radius:8px;margin:16px 0;overflow:auto}"
            "svg{width:100%;height:auto;display:block}table{border-collapse:collapse;white-space:nowrap;width:100%}"
            "th,td{border-bottom:1px solid #dbe3ee;padding:10px;text-align:right}th{background:#e2e8f0}"
            "a{color:#1d4ed8}small{line-height:1.5}"
            "@media(max-width:550px){main{padding:12px}.grid{grid-template-columns:1fr}}"
            "@media print{body{background:white}.grid{display:block}.card{break-inside:avoid}a{display:none}}"
            "</style></head><body><main><h1>Phân tích dữ liệu DOA</h1>"
            f"<p>{escape(note)}</p><p class='note'>{escape(POPULATION_NOTE)}</p>"
            f"<details><summary>Phạm vi và phiên lọc</summary><p>{escape(session_text)}</p><p>{escape(coverage or 'Nhiều nguồn: xem tổ hợp góc trong CSV.')}</p></details>"
            "<p><a href='per_file.csv'>Thống kê từng file</a> · <a href='by_angle_configuration.csv'>Theo góc/tổ hợp góc</a> · "
            "<a href='by_distance.csv'>Theo khoảng cách</a> · <a href='analysis_errors.csv'>File bị bỏ/lỗi</a></p>"
            f"<section class='card'><h2>Tổng hợp theo khoảng cách — cộng TP/FP/FN và frame</h2>{results_table(distances)}</section>"
            "<p><small>Chỉ các góc có CSV; điểm mô phỏng và số đo hiện có được ghi riêng. Đường nối không thêm dữ liệu. Góc TB là trung bình vòng trên frame đúng số nguồn; "
            "khi vẽ có thể dịch ±360° quanh góc thật để tránh nhảy 359°/0°, không sửa CSV. "
            "Góc raw 359° gần 0°; đồ thị theo frame vẫn hiển thị nguyên giá trị.</small></p>"
            f"<div class='grid'>{''.join(cards)}</div></main></body></html>")
    with (output / "index.html").open("x", encoding="utf-8") as handle:
        handle.write(html)
    report = ("# Phân tích DOA\n\n" + note + "\n\n" + POPULATION_NOTE + "\n\n"
              f"Phiên lọc: {session_text}.\n\n"
              "Mở index.html để xem biểu đồ. SVG riêng để chèn báo cáo; CSV để tính tiếp.\n"
              "per_file.csv có hash nguồn. analysis_errors.csv liệt kê file bị bỏ; không xem báo cáo thiếu file như toàn bộ bộ đo.\n"
              "MAE/RMSE dùng sai số vòng, ghép tối thiểu trên frame đúng số lượng. Matched MAE chỉ cặp TP trong ngưỡng.\n"
              "Trung bình góc là trung bình vòng, không lấy trung bình số học 359° và 1°.\n"
              "Tỷ lệ nhóm tính từ tổng TP/FP/FN, không lấy trung bình tỷ lệ file. Tổng hợp khoảng cách chỉ trên các góc đã đo.\n"
              "So sánh raw/filtered chỉ dùng các cặp nguồn hợp lệ; không tự lọc hoặc thay dữ liệu raw.\n"
              "Các nguồn được giả định luôn hoạt động; đây không phải recall classifier hay recall speech có nhãn thời gian.\n"
              "Không tự thêm kết quả AI khi chỉ có NOAI. Không sửa CSV nguồn, không mở COM.\n")
    with (output / "README.md").open("x", encoding="utf-8") as handle:
        handle.write(report)
    print(note)
    print(f"Đã xuất HTML, {len(charts)} biểu đồ SVG và CSV thống kê: {output}")
    if settings.open_report:
        try:
            if not webbrowser.open((output / "index.html").resolve().as_uri()):
                print("Không tự mở được trình duyệt. Mở index.html trong folder kết quả.")
        except webbrowser.Error:
            print("Không tự mở được trình duyệt. Mở index.html trong folder kết quả.")
    return output, distances, errors


def main():
    configure_terminal()
    try:
        _, _, errors = analyze_data(Settings())
        return 0 if not errors else 1
    except KeyboardInterrupt:
        print("\nĐã dừng. CSV nguồn không bị sửa; folder báo cáo có thể chưa hoàn tất.")
        return 1
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f"Lỗi: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
