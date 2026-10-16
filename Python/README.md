# Đo và đánh giá DOA theo format AI3

Chạy **remove_data_origin.py** để bỏ cột `data_origin` và đưa CSV về header
AI3 nguyên bản. Script sao lưu trước khi ghi đè và lưu nguồn mô phỏng riêng
trong `data/_data_sources.json`, kèm đường dẫn và SHA256 từng CSV.
Bộ đọc/đánh giá/lọc đọc tệp nguồn này, tổng hợp riêng với số đo thực.
Báo cáo hiển thị tên tiếng Việt “Mô phỏng” và “Đo thực”. Các CSV cũ có
cột nguồn vẫn đọc được. Khi chuyển CSV sang nơi khác, giữ kèm tệp nguồn.
Bộ thu UART vẫn ghi header AI3 nguyên bản; file mô phỏng không đổi cách thu.

Thu CSV/đánh giá: mở **measure_doa.py** rồi bấm Run. Sửa PORT, MODE và
NUM_SAMPLES một lần ở đầu file; góc và khoảng cách nhập trong terminal.
Xem góc trực tiếp: mở **visualize_doa.py** rồi bấm Run.
Lọc chuỗi frame rỗng sau khi thu: mở **process_doa.py** rồi bấm Run.
Phân tích và vẽ biểu đồ sau khi thu: mở **analyze_doa.py** rồi bấm Run.
Các file đều có hướng dẫn/cấu hình bằng tiếng Việt ngay đầu file.

## Radar riêng: chỉ trực quan hóa UART

Mở bản ứng dụng Windows bằng cách nhấp đúp **visualize_doa.exe** trong
thư mục Python. Không cần cài Python, mở IDE hay bấm Run; không hiện terminal.
Cấu hình mặc định: COM13, 921600 baud, nhãn AI. Chỉnh trực tiếp ở đầu cửa sổ:
cổng COM, baud UART, nhãn AI/NOAI và thời gian xóa kim khi mất dữ liệu.
Bấm **Quét cổng** để cập nhật danh sách COM; cũng có thể nhập COM trực tiếp.
Bấm **Áp dụng & kết nối** để lưu và kết nối lại ngay, không cần mở lại app.
Lựa chọn được nhớ trong visualize_doa.ini cạnh EXE/file Python cho lần mở sau.
Bấm **Ngắt kết nối** để giải phóng COM. Nếu COM không mở được hoặc mất kết nối,
cửa sổ vẫn mở để chọn lại cấu hình và kết nối lại. INI sai cũng có thể sửa
bằng các ô trong app. Có thể chép EXE và INI sang thư mục khác để dùng.

Log nhận dữ liệu nằm ngay dưới radar, có thời gian, số frame và dòng DOA
(kể cả DOA,0), cùng log kết nối/cảnh báo/lỗi. Giữ tối đa 1000 dòng gần nhất
để chạy lâu không nặng dần. **Xóa log** dọn màn hình; tắt **Tự cuộn** để đọc
log cũ. Kéo thanh chia giữa radar và log để đổi kích thước hai vùng.
Dòng thống kê hiển thị số frame đã nhận, tốc độ nhận và tuổi frame gần nhất.
Radar luôn vẽ frame mới nhất, tối đa 60 lần/giây; nền được giữ lại và chỉ
cập nhật kim. COM được đọc không chờ đủ buffer, ưu tiên dữ liệu mới nhất.
Log được cập nhật theo lô mỗi 0.1 giây; burst quá lớn chỉ giữ phần mới nhất.

Mở visualize_doa.py rồi Run cũng có cùng các ô cấu hình trong cửa sổ: radar mở
để xem dữ liệu DOA từ STM32. Không hỏi góc/khoảng cách, không có nút Thu,
không tạo thư mục/CSV hay tính recall. Đóng cửa sổ hoặc Esc để thoát.

Radar hiển thị 0° bên trái, 90° phía dưới, 180° bên phải, 270° phía trên.
Kim màu là các góc phát hiện theo thứ tự trong frame (không phải ID nguồn
ổn định). DOA,0 xóa kim; mất DOA hợp lệ quá STALE_SECONDS (mặc định 1 giây)
cũng xóa kim cũ. Chỉ đổi tọa độ vẽ, không đảo/bù/sửa giá trị góc raw.

Ngắt kết nối hoặc đóng radar trước khi chạy measure_doa.py để giải phóng COM; không chạy
hai file hoặc app UART khác cùng lúc trên cùng cổng. Khi thu, file đo chỉ
nhập góc/khoảng cách rồi bắt đầu lưu CSV, không mở cửa sổ/nút Thu nữa.
ACTION trong file đo chỉ còn "measure" và "analyze".
Radar dùng Tkinter/Tcl-Tk, không cần matplotlib. File đo không cần Tkinter.
MODE ở mỗi file chỉ là nhãn AI/NOAI, không tự thay đổi firmware.

## Xử lý khoảng rỗng nghi là ngắt nghỉ

process_doa.py chỉ xử lý CSV đã thu, không mở UART và không thay đổi firmware.
Cấu hình ở đầu file, không cần nhập terminal:

```python
MODE = "no_ai"          # "ai" hoặc "all" nếu cần nhánh khác
SOURCE_COUNTS = (1,)    # (1, 2, 3) để xử lý mọi trường hợp có nguồn
DISTANCES_M = ()        # () mọi khoảng cách; (0.1,) chỉ 0.1m
MIN_EMPTY_RUN = 3       # Chuỗi rỗng >=3 frame, không giới hạn tối đa
SAVE_OUTPUT = True     # False: chỉ xem kết quả, không tạo file
```

Frame rỗng: detected_count=0 và raw_angles trống. Loại toàn bộ chuỗi có độ
dài >=MIN_EMPTY_RUN, gồm cả chuỗi đầu/cuối file và dài hơn 10 frame. Chuỗi
ngắn hơn ngưỡng, góc sai hoặc frame thiếu/thừa nguồn nhưng còn phát hiện
ít nhất một nguồn vẫn được giữ. Không lọc phép đo chỉ nhiễu (0source).
Mất UART không có dòng CSV không được giả thành một chuỗi frame rỗng.

Bản lọc ở data/_processed/empty_run_min3_<thời điểm>/, giữ cấu trúc nhánh
AI/NOAI, khoảng cách, tên file và header AI3. Không ghi đè nguồn hoặc phiên
xử lý trước. sample gốc giữ nguyên để thấy các khoảng frame đã loại.
Mỗi phiên kèm filter_summary.csv, removed_runs.csv và README.md giải thích
quy tắc. File lỗi được cảnh báo và ghi trạng thái lỗi, không tự làm sạch.

**DOA,0 không chứng minh khoảng nghỉ**, có thể là bỏ sót tiếng nói. Đây là
heuristic theo DOA, không phải VAD hay nhãn speech độc lập. Summary giữ
recall_all_frames và ghi riêng recall_retained_frames_doa_selected, kèm
TP/FP/FN, số frame giữ/loại và SHA256 nguồn. Không thay recall toàn bộ bằng
recall sau lọc trong báo cáo hoặc so trực tiếp với paper có nhãn hoạt động
tiếng nói. Ngưỡng giống nhau cho AI/NOAI không bảo đảm tập frame giữ giống nhau.

ACTION="analyze" của file đo chỉ đánh giá raw; luôn bỏ qua _processed.
Xem chỉ số của bản lọc trong filter_summary.csv, không đưa bản lọc trở lại
nhánh raw (sample sau lọc không còn liên tục). Muốn recall khi có tiếng nói
thật cần nhãn khoảng nghỉ độc lập từ âm thanh tham chiếu đã đồng bộ thời gian.

## File phân tích và vẽ biểu đồ: analyze_doa.py

Không mở COM, không sửa CSV nguồn và không cần cài thư viện vẽ. Chỉnh cấu
hình tiếng Việt ở đầu file rồi Run. Mặc định đọc dữ liệu gốc NOAI, một nguồn,
mọi khoảng cách; lưu một phiên báo cáo mới ở data/_reports/analysis_<thời điểm>/.
Trình duyệt tự mở index.html (đặt OPEN_REPORT=False nếu chỉ muốn lưu).

```python
DATA_MODE = "raw"       # Dữ liệu gốc; "filtered" hoặc "compare" cho bản lọc
MODE = "no_ai"          # "ai" hoặc "all" nếu đã có dữ liệu tương ứng
SOURCE_COUNTS = (1,)    # (1, 2, 3) cho nhiều số nguồn, không trộn nhóm
DISTANCES_M = ()        # () mọi khoảng cách; (0.1,) chỉ 0.1m
PROCESSED_SESSION = ""  # "": phiên lọc hoàn tất mới nhất
DETAIL_FILE = ""        # "": file đầu tiên; hoặc "1sourceNOAI/0.2m/01_00dis02.csv"
```

Kết quả gồm HTML xem offline, SVG riêng cho mỗi biểu đồ, per_file.csv,
by_angle_configuration.csv, by_distance.csv, analysis_errors.csv và README.md.
SVG là ảnh vector để chèn vào báo cáo, không cần matplotlib/Excel.

Biểu đồ có recall/precision/F1 theo khoảng cách, MAE/RMSE theo khoảng cách,
recall/MAE theo góc, góc thật so với góc dự đoán trung bình vòng và góc raw
theo từng sample. Chỉ vẽ các góc thực sự đã thu; không tạo số liệu AI nếu
chưa có nhánh AI. Nhiều nguồn giữ tổ hợp góc; không gán recall tổng cho một
góc riêng. Tỷ lệ nhóm cộng TP/FP/FN rồi tính, không trung bình tỷ lệ file.

MAE/RMSE/median/P90 equal-count chỉ trên frame đúng số lượng nguồn, dùng
sai số vòng 0..180° và không cắt ngưỡng TP. Matched MAE chỉ cặp TP trong
ngưỡng. Không nhầm hai loại sai số. Trung bình góc dùng trung bình vòng;
359° và 1° không cho trung bình 180°. Không đổi góc raw trong CSV.

Muốn xem sau lọc: chạy process_doa.py trước rồi chọn DATA_MODE="filtered".
Muốn so sánh: DATA_MODE="compare". Hai vế chỉ gồm các cặp file hợp lệ cùng
nguồn, được kiểm tra SHA256 và toàn bộ các dòng giữ lại. File nguồn đổi
nội dung hoặc chưa có bản lọc bị bỏ khỏi cả hai vế và ghi cảnh báo.
Không có phiên lọc thì báo rõ, không tự lọc ngầm hay dùng raw thay filtered.
Recall filtered luôn là chỉ số trên tập frame được chọn theo DOA, không
thay recall raw/speech có nhãn thời gian. Lọc frame rỗng không thay đổi
MAE equal-count của các góc đã phát hiện. Đọc file lỗi trước khi dùng kết quả.

## Thu nhanh, không chạy lệnh dài

Ví dụ terminal:

```text
Góc thật 0–359 (...): 0
Khoảng cách MÉT (...): 0.1
... bắt đầu thu, bỏ frame khởi động rồi lưu 600 frame ...
Góc thật 0–359 (...): 90
Khoảng cách MÉT (...): [Enter dùng lại 0.1]
... bắt đầu thu lần tiếp ...
Góc thật 0–359 (...): q
```

Hai nguồn nhập 0;90. Ba nguồn nhập 0;90;180; không phải nhập riêng số nguồn.
Có thể nhập góc bằng dấu phẩy hoặc chấm phẩy. Khoảng cách nhập mét, ví dụ
0.1 = 10 cm. Nhiều nguồn cùng bán kính tới tâm mảng mic.
Nhập noise thay góc để đo chỉ nhiễu, không có nguồn tiếng người.

Sau mỗi lần thu, Recall/Precision/F1 hiển thị chỉ tính frame có ít nhất
một góc; bỏ mọi frame DOA,0 khỏi chỉ số này. Màn hình ghi số frame có góc
và số frame rỗng bị bỏ khỏi chỉ số. CSV vẫn lưu tất cả frame, kể cả DOA,0.
Đây là chỉ số trên frame có phát hiện, không xác nhận frame rỗng là im lặng.
ACTION="analyze" và các báo cáo offline vẫn đánh giá trên mọi frame CSV.

Sau lần thu đầu tiên, nếu Recall hiển thị dưới TARGET_RECALL (hiện 75%) thì tự thu thêm tối đa 3 lần với
cùng góc, khoảng cách và số frame (tối đa 4 lần gồm lần đầu). Chỉ cần một
lần đạt ngưỡng là dừng đo thêm ngay; nếu vẫn chưa đạt thì
thu đủ 3 lần bổ sung rồi quay lại hỏi góc cho lượt tiếp theo. Ngưỡng tính
trên Recall bỏ frame rỗng của từng lần thu riêng, không cộng dồn các lần đo.
Nếu toàn bộ frame rỗng thì Recall=N/A và vẫn thử thêm trong giới hạn trên.
Mỗi lần lưu CSV riêng, giữ cả các lần dưới ngưỡng. Đo noise có Recall=N/A
thì chỉ thu một lần, không tự đo thêm.

Xong lượt đo tự hỏi lần tiếp theo, không cần sửa code/chạy lại. q hoặc EOF để thoát.
Ctrl+C hoặc mất UART giữ phần CSV đã ghi, dừng phiên để kiểm tra.
Frame rỗng, thiếu/thừa nguồn đều được lưu; không chờ frame đẹp.

## Mọi dữ liệu ở trong data/

```text
data/
├── 0.1m/, 0.2m/, 0.3m/             Dữ liệu gốc cũ giữ nguyên
├── 1sourceNOAI/
│   ├── 0.1m/01_00dis01.csv
│   └── 0.2m/01_90dis02.csv
├── 2sourceNOAI/0.2m/01_00_90dis02.csv
├── 3sourceNOAI/
├── 1sourceAI/                       Nhánh tương tự khi MODE="ai"
├── 2sourceAI/
├── 3sourceAI/
├── 0sourceNOAI/, 0sourceAI/         Đo chỉ nhiễu
├── _reports/                        Kết quả đánh giá mới
├── _processed/                      Bản lọc chuỗi rỗng, nhật ký và so sánh riêng
└── _archive/                        Bản sao dữ liệu/công cụ trước khi dọn
```

Không còn dùng data_measurements/, data_recall/ hoặc reports/ ngoài data/.
Các thư mục cũ và data.zip đã được sao lưu vào
data/_archive/data_before_ai3_reset_20261006.zip trước khi bỏ.
Python và main.c trước lần đổi format nằm trong tools_before_ai3_format_20261006.zip.
data/ cũ được bảo toàn, không nhập lẫn với các nhánh thu AI3 mới.

## Format đúng AI3

UART chỉ nhận DOA,n,goc1,...,gocN (n=0..3), gồm DOA,0; không nhận EVAL/binary.
Giữ nguyên góc raw; không tự mirror, offset hoặc làm đẹp số liệu.

Tên file: 01_00_90dis02.csv = lần 01, hai góc 0°/90°, mã khoảng cách 20 cm.
Góc thật sắp tăng, góc và run/mã dis có ít nhất 2 chữ số.
Run tăng nếu đã có file, không ghi đè. Folder khoảng cách giữ giá trị mét thực.
Mã dis làm tròn theo bước 10 cm như AI3; CSV vẫn ghi khoảng cách chính xác.

CSV hai nguồn:

```text
sample,distance_cm,detected_count,raw_angles,true_angle_1,true_angle_2,detected_angle_1,detected_angle_2,error_1,error_2,mean_error
```

N nguồn thì có N cột mỗi nhóm true_angle/detected_angle/error.
distance_cm ghi centimet (mét nhập terminal *100). raw_angles ngăn bằng ;.
Các cột ghép/error chỉ có khi detected_count=N, ghép hoán vị nhỏ nhất như AI3;
thiếu/thừa thì để trống. Vẫn giữ raw và frame để đánh giá recall toàn bộ.

## Firmware phải flash lại trước khi đo

FFT/B1/src/main.c đã dùng SEND_DOA_TEST_UART=1, SEND_EVAL_UART=0,
SEND_DATASET_UART=0, USE_AI_FOR_PYTHON_TEST=1.

- AI_ENABLE=0 trên mạch: MODE="no_ai" trong Python.
- AI_ENABLE=1 và USE_AI_FOR_PYTHON_TEST=1: MODE="ai", DOA chỉ gửi góc AI giữ.
- USE_AI_FOR_PYTHON_TEST=0 gửi peak DSP ngay cả khi chạy AI; không gán nhãn
  kết quả này như đầu ra AI.
- MODE chỉ là nhãn folder, không tự bật/tắt AI/flash. Giữ clock 100 MHz và DSP cũ.

Giữ quy ước raw AI3, xác nhận bốn góc bố trí trước đợt đo; không tự đảo 90/270.
Firmware không biết góc thật/khoảng cách nguồn: Python nhận nhãn từ terminal.

## Đánh giá

Đổi ACTION="analyze" trong cùng file rồi Run. Không hỏi terminal, không mở UART.
Mặc định chỉ đọc các nhánh 0..3sourceAI/NOAI trong data/, không đọc _archive/,
_reports/, _processed/ hoặc các CSV đã lọc frame trong data/0.1m, 0.2m, 0.3m.
ANALYZE_FOLDERS ở đầu file cho phép chọn một nhánh/khoảng cách.

Xuất data/_reports/measurement_summary.csv và measurement_report.md.
AI/NOAI, số nguồn và khoảng cách được tách nhóm. Tính từ raw, không sửa CSV.
Báo cáo được tạo lại mỗi lần analyze; file không hợp lệ được cảnh báo rõ.

Recall=TP/(TP+FN) trên mọi frame: không bỏ frame zero như evaluator AI3 cũ.
Ghép góc một-một trong ±TOLERANCE_DEG, tối đa TP trước rồi tối thiểu sai số.
Matched MAE chỉ tính các cặp TP trong ngưỡng; không phải mean_error trong CSV.
Không có TP: MAE=N/A; noise không có nguồn thật: recall=N/A.
Các nguồn khai báo được coi là đang hoạt động ở mọi frame; podcast có khoảng
nghỉ cần nhãn speech theo thời gian riêng, chưa được bộ đo này hỗ trợ.

## Kiểm thử phát triển (không cần chạy để thu)

Python 3.10+; pyserial khi mở UART; Tkinter/Tcl-Tk chỉ cho visualize_doa.py. Kiểm thử dùng
UART/CSV giả và widget ẩn, không dùng data thật:

```text
python -B -m unittest discover -s Python/tests -v
```
