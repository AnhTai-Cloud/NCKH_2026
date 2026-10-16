"""TRỰC QUAN HÓA DOA TRỰC TIẾP TỪ STM32 — CHỈ XEM, KHÔNG THU CSV.

CÁCH DÙNG
  1. Nhấp đúp visualize_doa.exe hoặc chạy file Python để mở radar.
  2. Chọn cổng COM, baud, nhãn AI/NOAI và thời gian xóa kim trong app.
     Bấm Áp dụng & kết nối: lưu lựa chọn cho lần mở sau và kết nối lại.
     Quét cổng cập nhật danh sách COM; vẫn có thể nhập COM trực tiếp.
  3. Di chuyển nguồn âm, xem góc raw và các kim màu. Đóng cửa sổ để thoát.
  4. Muốn thu dữ liệu: đóng radar rồi chạy measure_doa.py.
     Không mở hai file hoặc app khác trên cùng COM cùng lúc.

Ý NGHĨA CẤU HÌNH
  PORT: cổng COM của STM32 trong Device Manager, ví dụ COM13.
  BAUD: baud UART, phải khớp firmware; không phải tần số lấy mẫu âm thanh.
  MODE: "ai" hoặc "no_ai", CHỈ là nhãn hiển thị; không bật/tắt AI trên mạch.
  STALE_SECONDS: mất frame DOA hợp lệ lâu hơn số giây này sẽ xóa kim cũ,
      tránh nhầm góc cũ là góc đang đo. Không tự đóng radar khi mất dữ liệu.

QUY ƯỚC VÀ FORMAT
  0° bên trái, 90° phía dưới, 180° bên phải, 270° phía trên.
  Chỉ đổi tọa độ vẽ, không mirror/bù/sửa giá trị góc nhận từ firmware.
  UART theo AI3: DOA,0 hoặc DOA,n,goc1,...,gocN; n=0..3, góc 0..359.
  DOA,0 xóa kim ngay; dòng hỏng và EVAL/binary không được coi là DOA,0.
  Mỗi frame có tối đa ba kim màu. Màu theo thứ tự góc trong frame UART,
      không phải ID nguồn ổn định qua các frame.
  Radar vẽ frame mới nhất, tối đa 60 lần/giây; đọc COM không chờ đủ buffer.
  Log trong cửa sổ ghi frame DOA và trạng thái kết nối; giữ 1000 dòng gần nhất.
  File này KHÔNG tạo thư mục/CSV, không tính recall, không đọc CSV đã lưu.
  Dùng chung bộ đọc format với measure_doa.py, nhưng không gọi hàm thu/đánh giá.

YÊU CẦU
  Python 3.10+, pyserial và Tkinter/Tcl-Tk (thường đi kèm bộ cài Python).
  Không cần matplotlib, không cần TFT, không cần sửa firmware để tách radar.
  STM32 phải gửi DOA: SEND_DOA_TEST_UART=1, SEND_EVAL_UART=0,
      SEND_DATASET_UART=0; AI_ENABLE phải khớp nhãn MODE đã chọn.
"""

from __future__ import annotations

import math
import sys
import tempfile
import time
from collections import deque
from configparser import ConfigParser, Error as ConfigError
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

if __package__:
    from .measure_doa import StreamParser, configure_terminal
else:  # Bấm Run trực tiếp file này trong IDE, không cần lệnh dạng module.
    from measure_doa import StreamParser, configure_terminal

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

# ======================= GIÁ TRỊ MẶC ĐỊNH KHI CHƯA CÓ INI =======================
PORT = "COM13"       # COM của mạch; đóng file thu dữ liệu/app khác dùng COM
BAUD = 921600        # Baud UART giống main.c, không phải sample rate
MODE = "ai"       # "ai" hoặc "no_ai": chỉ nhãn radar, không đổi firmware
STALE_SECONDS = 1.0  # Mất DOA hợp lệ quá 1 giây thì xóa kim cũ
DRAW_INTERVAL = 1 / 60
LOG_INTERVAL = 0.1
MAX_LOG_LINES = 1000
MAX_READ_BYTES = 65536
POLL_INTERVAL = 0.005


@dataclass(frozen=True)
class Settings:
    port: str = PORT
    baud: int = BAUD
    mode: str = MODE
    stale_seconds: float = STALE_SECONDS
    settle_seconds: float = 1.0

    def validate(self):
        if not isinstance(self.port, str) or not self.port.strip():
            raise ValueError("PORT phải là cổng COM của mạch.")
        if type(self.baud) is not int or self.baud <= 0:
            raise ValueError("BAUD phải là số nguyên dương, khớp UART firmware.")
        if self.mode not in ("ai", "no_ai"):
            raise ValueError('MODE phải là "ai" hoặc "no_ai".')
        if not math.isfinite(self.stale_seconds) or self.stale_seconds <= 0:
            raise ValueError("STALE_SECONDS phải hữu hạn và >0.")
        if not math.isfinite(self.settle_seconds) or self.settle_seconds < 0:
            raise ValueError("Thời gian chờ khởi động không hợp lệ.")


def settings_path():
    source = sys.executable if getattr(sys, "frozen", False) else __file__
    return Path(source).resolve().with_suffix(".ini")


def load_settings(path=None):
    """Đọc cấu hình đã lưu cạnh EXE/file Python, không phụ thuộc thư mục mở app."""
    defaults = Settings()
    path = settings_path() if path is None else Path(path)
    if not path.exists():
        return defaults
    config = ConfigParser()
    try:
        with path.open(encoding="utf-8-sig") as handle:
            config.read_file(handle)
        section = config["radar"]
        settings = Settings(
            port=section.get("port", defaults.port).strip(),
            baud=section.getint("baud", defaults.baud),
            mode=section.get("mode", defaults.mode).strip(),
            stale_seconds=section.getfloat("stale_seconds", defaults.stale_seconds))
    except (ConfigError, KeyError, ValueError) as exc:
        raise ValueError(f"Cấu hình {path.name} không hợp lệ: {exc}") from exc
    settings.validate()
    return settings


def save_settings(settings, path):
    settings.validate()
    config = ConfigParser()
    config["radar"] = {"port": settings.port, "baud": str(settings.baud),
                       "mode": settings.mode, "stale_seconds": str(settings.stale_seconds)}
    # Ghi file tạm rồi thay thế để một lần lưu hỏng không làm mất cấu hình cũ.
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name + ".", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            config.write(handle)
        except BaseException:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def report_error(message):
    print(f"Lỗi: {message}")
    if getattr(sys, "frozen", False) and "--self-test" not in sys.argv:
        from tkinter import messagebox
        messagebox.showerror("Radar DOA", str(message))


def radar_point(angle, center_x, center_y, radius):
    """Tọa độ màn hình: 0 trái, 90 dưới, 180 phải, 270 trên; góc raw giữ nguyên."""
    theta = math.radians(angle)
    return center_x - radius * math.cos(theta), center_y + radius * math.sin(theta)


class LiveRadar:
    """Radar chỉ xem: không nút thu, không ghép góc thật, không ghi dữ liệu."""
    COLORS = ("#ff5b55", "#05baff", "#ffd536")

    def __init__(self, settings, hidden=False, clock=time.monotonic, port_lister=None):
        settings.validate()
        try:
            import tkinter as tk
            from tkinter import ttk
        except ImportError as exc:
            raise RuntimeError("Python này thiếu Tkinter. Dùng bộ cài Python có Tcl/Tk.") from exc
        self.tk, self.settings, self.clock = tk, settings, clock
        self.on_apply, self.on_disconnect = None, None
        self.port_lister = port_lister or (lambda: [p.device for p in list_ports.comports()] if list_ports else [])
        self._open, self._dirty, self._last_draw = True, True, -math.inf
        self._grid_size, self._prediction_items = None, []
        self._pending_log = deque(maxlen=MAX_LOG_LINES)
        self._log_lines, self._last_log_flush = 0, -math.inf
        self.total_frames, self._rate_frames, self._rate_started = 0, 0, clock()
        self._frame_rate, self._last_metrics = 0.0, -math.inf
        self.last_frame, self.last_rx = None, None
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            raise RuntimeError(f"Không mở được radar Tkinter: {exc}") from exc
        if hidden:
            self.root.withdraw()
        self.root.title("DOA – trực quan hóa UART")
        width = min(900, self.root.winfo_screenwidth() - 80)
        height = min(880, self.root.winfo_screenheight() - 100)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(780, width), min(740, height))
        self.root.configure(bg="#101827")
        mode = "AI" if settings.mode == "ai" else "NOAI"
        self.title_text = tk.StringVar(value=f"Direction of Arrival · {mode}")
        self.connection_text = tk.StringVar(value="CHƯA KẾT NỐI")
        tk.Label(self.root, textvariable=self.title_text, bg="#101827",
                 fg="#f1f5f9", font=("Segoe UI", 17, "bold")).pack(pady=(12, 4))
        tk.Label(self.root, textvariable=self.connection_text,
                 bg="#101827", fg="#cbd5e1", font=("Segoe UI", 11)).pack()
        controls = tk.Frame(self.root, bg="#101827")
        controls.pack(fill="x", padx=18, pady=(10, 3))
        self.port_var = tk.StringVar(value=settings.port)
        self.baud_var = tk.StringVar(value=str(settings.baud))
        self.mode_var = tk.StringVar(value=mode)
        self.stale_var = tk.StringVar(value=f"{settings.stale_seconds:g}")
        for column, text in enumerate(("Cổng COM", "Baud UART", "Nhãn chế độ", "Xóa kim sau (giây)")):
            tk.Label(controls, text=text, bg="#101827", fg="#cbd5e1",
                     font=("Segoe UI", 10)).grid(row=0, column=column, sticky="w", padx=6, pady=3)
            controls.columnconfigure(column, weight=1)
        self.port_combo = ttk.Combobox(controls, textvariable=self.port_var, width=17,
                                       font=("Segoe UI", 10))
        self.baud_combo = ttk.Combobox(controls, textvariable=self.baud_var, width=15,
            values=(9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 1000000),
            font=("Segoe UI", 10))
        self.mode_combo = ttk.Combobox(controls, textvariable=self.mode_var, width=12,
                                       values=("AI", "NOAI"), state="readonly", font=("Segoe UI", 10))
        self.stale_entry = ttk.Entry(controls, textvariable=self.stale_var, width=15,
                                    font=("Segoe UI", 10))
        for column, widget in enumerate((self.port_combo, self.baud_combo, self.mode_combo, self.stale_entry)):
            widget.grid(row=1, column=column, sticky="ew", padx=6, pady=(0, 6))
        actions = tk.Frame(controls, bg="#101827")
        actions.grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=3)
        ttk.Button(actions, text="Quét cổng", command=self.refresh_ports).pack(side="left", padx=(0, 8))
        self.apply_button = ttk.Button(actions, text="Áp dụng & kết nối", command=self.apply_configuration)
        self.apply_button.pack(side="left", padx=(0, 8))
        self.disconnect_button = ttk.Button(actions, text="Ngắt kết nối", state="disabled",
                                             command=lambda: self.on_disconnect() if self.on_disconnect else None)
        self.disconnect_button.pack(side="left")
        tk.Label(controls, text="AI/NOAI là nhãn hiển thị, phải khớp cấu hình trên mạch.",
                 bg="#101827", fg="#94a3b8", font=("Segoe UI", 9)).grid(
                     row=3, column=0, columnspan=4, sticky="w", padx=6, pady=(3, 0))
        tk.Label(self.root, text="Màu: góc phát hiện · Chỉ xem, không lưu dữ liệu",
                 bg="#101827", fg="#94a3b8", font=("Segoe UI", 10)).pack(pady=3)
        # Chừa chỗ cho trạng thái/nút Đóng trước khi radar và log giãn ra.
        footer = tk.Frame(self.root, bg="#101827")
        footer.pack(side="bottom", fill="x")
        panes = tk.PanedWindow(self.root, orient="vertical", bg="#101827",
                               sashwidth=6, sashrelief="flat", borderwidth=0)
        panes.pack(fill="both", expand=True, padx=12, pady=8)
        radar_pane = tk.Frame(panes, bg="#0f172a")
        self.canvas = tk.Canvas(radar_pane, bg="#0f172a", width=750, height=400,
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        panes.add(radar_pane, minsize=200, stretch="always")
        self.canvas.bind("<Configure>", lambda event: self._mark_dirty())
        log_pane = tk.Frame(panes, bg="#101827")
        log_toolbar = tk.Frame(log_pane, bg="#101827")
        log_toolbar.pack(fill="x", pady=(2, 4))
        tk.Label(log_toolbar, text="Log nhận dữ liệu · 1000 dòng gần nhất", bg="#101827",
                 fg="#cbd5e1", font=("Segoe UI", 10)).pack(side="left")
        self.auto_scroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_toolbar, text="Tự cuộn", variable=self.auto_scroll).pack(side="right", padx=8)
        ttk.Button(log_toolbar, text="Xóa log", command=self.clear_log).pack(side="right")
        log_body = tk.Frame(log_pane, bg="#101827")
        log_body.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_body, height=6, bg="#0b1220", fg="#dbeafe",
            font=("Consolas", 9), wrap="word", state="disabled", relief="flat",
            padx=8, pady=5, selectbackground="#334155")
        scrollbar = ttk.Scrollbar(log_body, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        panes.add(log_pane, minsize=100, stretch="never")
        self.metrics_text = tk.StringVar(value="Đã nhận: 0 frame · Tốc độ: 0 frame/s")
        tk.Label(footer, textvariable=self.metrics_text, bg="#101827", fg="#94a3b8",
                 font=("Segoe UI", 10)).pack(pady=2)
        self.angles_text = tk.StringVar(value="Chưa nhận được frame DOA")
        tk.Label(footer, textvariable=self.angles_text, bg="#101827", fg="#f1f5f9",
                 font=("Segoe UI", 11)).pack(pady=3)
        self.state_text = tk.StringVar(value="Chọn cấu hình rồi bấm Áp dụng & kết nối")
        tk.Label(footer, textvariable=self.state_text, bg="#101827", fg="#a7f3d0",
                 wraplength=730, font=("Segoe UI", 11)).pack(padx=10, pady=5)
        self.close_button = tk.Button(footer, text="Đóng", command=self.close,
                                     font=("Segoe UI", 11), padx=16, pady=7)
        self.close_button.pack(pady=(4, 12))
        self.root.bind("<Escape>", lambda event: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_ports()
        self.add_log("Radar sẵn sàng. Chọn cấu hình để kết nối.")

    def refresh_ports(self):
        try:
            ports = sorted(set(self.port_lister()), key=lambda port: (len(port), port))
            self.port_combo.configure(values=ports)
        except OSError as exc:
            self.set_status(f"Không quét được cổng COM: {exc}. Có thể nhập COM trực tiếp.")

    def settings_from_controls(self):
        try:
            settings = replace(self.settings, port=self.port_var.get().strip(),
                baud=int(self.baud_var.get().strip()),
                mode={"AI": "ai", "NOAI": "no_ai"}[self.mode_var.get()],
                stale_seconds=float(self.stale_var.get().strip().replace(",", ".")))
        except (ValueError, KeyError) as exc:
            raise ValueError("Baud phải là số nguyên; thời gian xóa kim phải là số dương; chọn AI hoặc NOAI.") from exc
        settings.validate()
        return settings

    def apply_configuration(self):
        try:
            candidate = self.settings_from_controls()
            if self.on_apply:
                self.on_apply(candidate)
        except (ValueError, OSError) as exc:
            self.add_log(f"Lỗi cấu hình: {exc}")
            from tkinter import messagebox
            messagebox.showerror("Cấu hình radar", str(exc), parent=self.root)

    def set_settings(self, settings):
        self.settings = settings
        self.title_text.set(f"Direction of Arrival · {'AI' if settings.mode == 'ai' else 'NOAI'}")

    def set_status(self, message):
        if self._open:
            if self.state_text.get() != message:
                self.add_log(message)
            self.state_text.set(message)

    def set_connected(self, connected):
        if not self._open:
            return
        text = (f"{self.settings.port} · {self.settings.baud} baud" if connected else "CHƯA KẾT NỐI")
        self.connection_text.set(text)
        self.disconnect_button.configure(state="normal" if connected else "disabled")
        if connected:
            self.total_frames, self._rate_frames, self._rate_started = 0, 0, self.clock()
            self._frame_rate = 0.0
            self._last_metrics = -math.inf

    def clear_frame(self, message):
        self.last_frame, self.last_rx, self._dirty = None, None, True
        if self._open:
            self.angles_text.set("Chưa nhận được frame DOA")
            self.set_status(message)

    def _mark_dirty(self):
        self._dirty = True

    def add_log(self, message, timestamp=None):
        if self._open:
            stamp = timestamp or datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._pending_log.append(f"[{stamp}] {message}\n")

    def clear_log(self):
        self._pending_log.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._log_lines = 0

    def _flush_log(self, now):
        if not self._pending_log or now - self._last_log_flush < LOG_INTERVAL:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", "".join(self._pending_log))
        self._log_lines += len(self._pending_log)
        self._pending_log.clear()
        excess = self._log_lines - MAX_LOG_LINES
        if excess > 0:
            self.log_text.delete("1.0", f"{excess + 1}.0")
            self._log_lines = MAX_LOG_LINES
        self.log_text.configure(state="disabled")
        if self.auto_scroll.get():
            self.log_text.see("end")
        self._last_log_flush = now

    def receive_frames(self, frames):
        """Log các frame đã nhận, nhưng radar chỉ hiển thị frame mới nhất."""
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        first = self.total_frames + 1
        self.total_frames += len(frames)
        self._rate_frames += len(frames)
        # Với một burst lớn chỉ cần định dạng phần còn nằm trong log giới hạn.
        start = max(0, len(frames) - MAX_LOG_LINES)
        for index in range(start, len(frames)):
            frame = frames[index]
            raw = f"DOA,{len(frame.angles)}" + "".join(f",{angle}" for angle in frame.angles)
            self.add_log(f"#{first + index:06d} | {raw}", stamp)
        self.update_frame(frames[-1])

    def update_frame(self, frame):
        self._dirty = self._dirty or frame != self.last_frame
        self.last_frame, self.last_rx = frame, self.clock()

    def _update_frame_text(self):
        frame = self.last_frame
        if frame is None:
            return
        text = "Không phát hiện nguồn (DOA,0)" if not frame.angles else "  |  ".join(
            f"Nguồn {i+1}: {a}°" for i, a in enumerate(frame.angles))
        state = f"ĐANG NHẬN — {len(frame.angles)} nguồn · Chỉ xem, không tạo CSV"
        if self.angles_text.get() != text:
            self.angles_text.set(text)
        if self.state_text.get() != state:
            self.state_text.set(state)

    def _redraw(self):
        canvas = self.canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        cx, cy, radius = width / 2, height / 2, max(20, min(width, height) / 2 - 43)
        if self._grid_size != (width, height):
            canvas.delete("grid")
            for fraction in (0.25, 0.5, 0.75, 1):
                r = radius * fraction
                canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#334155", width=1, tags="grid")
            for angle in range(0, 360, 30):
                x, y = radar_point(angle, cx, cy, radius)
                canvas.create_line(cx, cy, x, y, fill="#334155", tags="grid")
                x, y = radar_point(angle, cx, cy, radius + 23)
                canvas.create_text(x, y, text=f"{angle}°", fill="#e2e8f0",
                                   font=("Segoe UI", 11), tags="grid")
            canvas.create_oval(cx-3, cy-3, cx+3, cy+3, fill="#e2e8f0", outline="", tags="grid")
            self._grid_size = (width, height)
        angles = self.last_frame.angles if self.last_frame is not None else ()
        while len(self._prediction_items) > len(angles):
            for item in self._prediction_items.pop():
                canvas.delete(item)
        while len(self._prediction_items) < len(angles):
            color = self.COLORS[len(self._prediction_items)]
            arrow = canvas.create_line(0, 0, 0, 0, fill=color, width=3, arrow="last", tags="prediction")
            dot = canvas.create_oval(0, 0, 0, 0, fill=color, outline=color, tags="prediction")
            self._prediction_items.append((arrow, dot))
        for angle, (arrow, dot) in zip(angles, self._prediction_items):
            x, y = radar_point(angle, cx, cy, radius * 0.96)
            canvas.coords(arrow, cx, cy, x, y)
            canvas.coords(dot, x-4, y-4, x+4, y+4)
        canvas.tag_raise("prediction")
        self._update_frame_text()
        self._dirty = False

    def pump(self):
        if not self._open:
            return False
        try:
            now = self.clock()
            if (self.last_rx is not None and self.last_frame is not None
                    and now - self.last_rx > self.settings.stale_seconds):
                self.last_frame, self._dirty = None, True
                self.angles_text.set("Mất dữ liệu DOA — đã xóa kim cũ")
                self.set_status("CHỜ UART — kiểm tra nguồn/cáp/COM/format DOA")
            if self._dirty and now - self._last_draw >= DRAW_INTERVAL:
                self._redraw()
                self._last_draw = now
            self._flush_log(now)
            if now - self._last_metrics >= 0.5:
                elapsed = now - self._rate_started
                if elapsed >= 0.5:
                    self._frame_rate = self._rate_frames / elapsed
                    self._rate_frames, self._rate_started = 0, now
                age = "" if self.last_rx is None else f" · Frame gần nhất: {max(0, now - self.last_rx)*1000:.0f} ms"
                self.metrics_text.set(f"Đã nhận: {self.total_frames} frame · Tốc độ: {self._frame_rate:.1f} frame/s{age}")
                self._last_metrics = now
            self.root.update()
        except self.tk.TclError:
            self._open = False
        return self._open

    def close(self):
        if self._open:
            self._open = False
            try:
                self.root.destroy()
            except self.tk.TclError:
                pass


class RadarApp:
    """Giữ cửa sổ mở khi đổi cấu hình, ngắt kết nối hoặc lỗi COM."""
    def __init__(self, settings, serial_factory=None, viewer_factory=None,
                 clock=time.monotonic, sleep=time.sleep, config_path=None):
        settings.validate()
        if serial_factory is None:
            if serial is None:
                raise RuntimeError("Chưa có pyserial. Cài một lần: python -m pip install pyserial")
            serial_factory = serial.Serial
        self.settings, self.serial_factory = settings, serial_factory
        self.clock, self.sleep, self.config_path = clock, sleep, config_path
        self.uart, self.parser, self.status = None, StreamParser(), "closed"
        self.viewer = (viewer_factory or LiveRadar)(settings)
        self.viewer.on_apply = lambda candidate: self.connect(candidate, persist=True)
        self.viewer.on_disconnect = self.disconnect

    def disconnect(self, message="Đã ngắt kết nối. Có thể đổi cấu hình hoặc dùng COM để thu dữ liệu."):
        uart, self.uart = self.uart, None
        if uart is not None:
            try:
                uart.close()
            except OSError as exc:
                print(f"Lỗi khi đóng UART: {exc}")
        self.parser = StreamParser()
        self.viewer.set_connected(False)
        self.viewer.clear_frame(message)

    def connect(self, settings, persist=False):
        settings.validate()
        if persist and self.config_path is not None:
            # Lưu thất bại thì giữ kết nối/cấu hình đang chạy để người dùng xử lý.
            save_settings(settings, self.config_path)
        self.disconnect()
        self.settings = settings
        self.viewer.set_settings(settings)
        try:
            self.uart = self.serial_factory(settings.port, settings.baud, timeout=0)
        except OSError as exc:
            self.status = "serial_error"
            self.viewer.set_status(f"Không mở được {settings.port}: {exc}. Chọn lại COM rồi bấm Áp dụng & kết nối.")
            print(f"Lỗi UART: {exc}")
            return False
        self.status = "closed"
        self.ready_at = self.clock() + settings.settle_seconds
        self.reset_done, self.received_any, self.warned_eval = False, False, False
        self.last_notice = self.ready_at
        self.viewer.set_connected(True)
        self.viewer.set_status(f"Đã kết nối {settings.port} · {settings.baud} baud · "
                               f"{'AI' if settings.mode == 'ai' else 'NOAI'} — chờ frame DOA")
        print(f"Radar trực tiếp: {settings.port}, {settings.baud} baud, MODE={settings.mode}.")
        return True

    def poll(self):
        if self.uart is None or self.clock() < self.ready_at:
            return
        try:
            if not self.reset_done:
                self.uart.reset_input_buffer()
                self.reset_done = True
            now = self.clock()
            if not self.received_any and now - self.last_notice >= 5:
                message = "Chờ DOA: kiểm tra COM/baud, SEND_DOA_TEST_UART=1 và flash firmware."
                self.viewer.set_status(message)
                print(message)
                self.last_notice = now
            waiting = self.uart.in_waiting
            data = self.uart.read(min(waiting, MAX_READ_BYTES)) if waiting else b""
            invalid_before = self.parser.invalid_lines
            frames = []
            for offset in range(0, len(data), 4096):
                frames.extend(self.parser.feed(data[offset:offset + 4096]))
            if self.parser.invalid_lines > invalid_before:
                self.viewer.add_log(f"Bỏ {self.parser.invalid_lines - invalid_before} dòng DOA không hợp lệ.")
            if self.parser.wrong_protocol_lines and not self.warned_eval:
                message = "Đang nhận EVAL, không phải AI3 DOA. Kiểm tra SEND_EVAL_UART=0."
                self.viewer.set_status(message)
                print(message)
                self.warned_eval = True
            if frames:
                self.received_any = True
                self.viewer.receive_frames(frames)
        except OSError as exc:
            self.status = "serial_error"
            self.disconnect(f"Mất kết nối: {exc}. Kiểm tra cáp/mạch rồi bấm Áp dụng & kết nối.")
            print(f"Lỗi UART: {exc}. Không tạo CSV.")

    def run(self, auto_connect=True):
        try:
            if auto_connect:
                self.connect(self.settings)
            while self.viewer.pump():
                self.poll()
                self.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            self.status = "interrupted"
        finally:
            self.disconnect()
            self.viewer.close()
        return self.status


def run_visualizer(settings, serial_factory=None, viewer_factory=None,
                   clock=time.monotonic, sleep=time.sleep, config_path=None):
    """Chỉ đọc UART và cấu hình app; không gọi bất kỳ hàm tạo/ghi CSV nào."""
    app = RadarApp(settings, serial_factory, viewer_factory, clock, sleep, config_path)
    return app.run()


def main():
    configure_terminal()
    try:
        config_error = None
        try:
            settings = load_settings()
        except (ValueError, OSError) as exc:
            settings, config_error = Settings(), str(exc)
        if "--self-test" in sys.argv:
            # Kiểm tra bản đóng gói/Tk/DOA/cấu hình mà không mở COM thật.
            if serial is None:
                raise RuntimeError("Bản đóng gói thiếu pyserial.")
            settings = replace(settings, settle_seconds=0)
            viewer = LiveRadar(settings, hidden=True)
            try:
                for frame in StreamParser().feed(b"DOA,1,90\nDOA,3,0,180,270\nDOA,0\n"):
                    viewer.update_frame(frame)
                    viewer._redraw()
                    if len(viewer.canvas.find_withtag("prediction")) != 2 * len(frame.angles):
                        raise RuntimeError("Kiểm tra kim radar thất bại.")
                    if not viewer.pump():
                        raise RuntimeError("Cửa sổ radar đóng trong khi kiểm tra.")
                class ProbeUART:
                    closed = False
                    in_waiting = 10
                    def reset_input_buffer(self):
                        pass
                    def read(self, size):
                        return b"DOA,1,270\n"
                    def close(self):
                        self.closed = True
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "visualize_doa.ini"
                    ports = []
                    def factory(*args, **kwargs):
                        uart = ProbeUART()
                        ports.append(uart)
                        return uart
                    app = RadarApp(settings, serial_factory=factory,
                        viewer_factory=lambda _: viewer, config_path=path)
                    try:
                        viewer.port_var.set("COM98")
                        viewer.baud_var.set("115200")
                        viewer.mode_var.set("NOAI")
                        viewer.stale_var.set("2.5")
                        viewer.on_apply(viewer.settings_from_controls())
                        expected = Settings(port="COM98", baud=115200, mode="no_ai", stale_seconds=2.5)
                        if load_settings(path) != expected:
                            raise RuntimeError("Kiểm tra lưu/đọc cấu hình thất bại.")
                        app.poll()
                        if viewer.last_frame.angles != (270,):
                            raise RuntimeError("Kiểm tra UART giả thất bại.")
                        viewer._flush_log(viewer.clock() + LOG_INTERVAL)
                        if "DOA,1,270" not in viewer.log_text.get("1.0", "end"):
                            raise RuntimeError("Kiểm tra log trong app thất bại.")
                        viewer.port_var.set("COM97")
                        viewer.on_apply(viewer.settings_from_controls())
                        if not ports[0].closed or viewer.last_frame is not None:
                            raise RuntimeError("Kiểm tra đổi COM thất bại.")
                        viewer.on_disconnect()
                        if not ports[1].closed or not viewer._open:
                            raise RuntimeError("Kiểm tra ngắt kết nối thất bại.")
                    finally:
                        app.disconnect()
            finally:
                viewer.close()
            return 0
        app = RadarApp(settings, config_path=settings_path())
        if config_error:
            app.viewer.set_status(f"{config_error}. Chỉnh cấu hình trong app rồi bấm Áp dụng & kết nối.")
        status = app.run(auto_connect=config_error is None)
        return 0 if status in ("closed", "interrupted") else 1
    except KeyboardInterrupt:
        print("\nĐã dừng radar, không tạo CSV.")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        report_error(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
