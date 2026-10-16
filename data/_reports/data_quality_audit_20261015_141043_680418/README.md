# Kiểm định dữ liệu DOA

Mở `index.html` để xem báo cáo, lọc từng file và xem đồ thị. `bao_cao_kiem_dinh.md` là bản mô tả ngắn có thể đọc độc lập.

## Phạm vi và kết quả

- 13.782 CSV đang dùng trong các nhánh 0–3sourceAI/NOAI; 16.216.648 dòng dữ liệu. Các thư mục lưu trữ/kịch bản/bản sao không được đếm lại thành phiên thu độc lập.
- 59 file hai nguồn không AI được đổi thứ tự cột để tương thích bộ đọc hiện tại, tổng 5.900 dòng. Không đổi giá trị theo tên cột, không thêm/xóa khung và không sửa góc đo hay góc mục tiêu.
- 6 file chỉ có tiêu đề được giữ nguyên và không tham gia tính hiệu năng. File 200 khung không được bổ sung thành 300 khung.
- 13.191 file có bằng chứng mô phỏng; 149 file khớp bản ghi thu cũ; 442 file chưa xác minh. Khớp bản ghi cũ không xác minh độc lập nguồn phần cứng.
- Các chỉ số, khoảng tin cậy và kiểm định trước/sau không đổi. Cảnh báo còn lại được lưu và không dùng để sửa/xóa quan sát.

## Tệp phân tích

Mười bảng CSV gồm chỉ số theo nhóm, từng file, từng bố trí góc, phân phối mô tả, kiểm định và q-value, đối chứng bố trí chung, ảnh hưởng cự ly, tương quan, nhật ký sửa file và tổng hợp cảnh báo.

`audited_file_details.jsonl.gz` là chi tiết từng cột/tệp, CI theo khối, thống kê vòng tròn, ACF và các kiểm định runs chính xác có q-value. `file_features_before/after.jsonl.gz` giữ dữ liệu phân tích trung gian; trường `sequence_tests` trong hai tệp này là chẩn đoán chuẩn hóa ban đầu. Giá trị kiểm định chính thức nằm trong `statistical_tests.csv`, `statistics_before/after.json` và `audited_file_details.jsonl.gz`.

`row_flags_after.jsonl.gz` ghi file, khoảng dòng, mã cảnh báo và lý do. `shared_sequences.jsonl.gz` ghi các cửa sổ góc trùng, kèm phân biệt cặp mô phỏng dùng chung đầu vào. `file_changes.json/csv` ghi header cũ/mới và checksum. `row_changes.jsonl.gz` không có sự kiện thay ô vì không có ô giá trị nào được sửa.

`raw_angle_temporal_features.jsonl.gz` phân tích mọi góc raw, bao gồm hướng không ghép đúng mục tiêu. Bước nhảy được ghép giữa hai khung liên tiếp theo tổng độ dịch chuyển góc vòng nhỏ nhất; phép ghép này không xác định danh tính nguồn. ACF của phần thực/ảo vector đơn vị trung bình giữ nguyên trục khung và bỏ cặp đầu mút trống, không nối tắt các khoảng trống. Các kết quả bước góc và ACF theo nguồn trong bảng chi tiết TP có phạm vi khác và chỉ dùng các góc ghép đúng trong 15°.

`historical_selection_bias.json` xác minh 40 file trong bản ZIP của lần chọn loại theo ngưỡng 55% trước đây, tính lại chỉ số từ dữ liệu gốc và đối chiếu nhật ký. Phân tích này không trộn các phiên bản lưu trữ vào bộ hiện tại và không thay đổi bản gốc.

## Giới hạn thống kê

Không có âm thanh gốc, mã phiên thu, nhãn hoạt động từng nguồn, SNR hay dấu thời gian cảm biến. Các CI/kiểm định có điều kiện theo đơn vị tệp/bố trí được chọn. Không xem khung chồng lấp là quan sát độc lập. Bootstrap khối chỉ dùng ACF đến độ trễ 30; phụ thuộc dài hơn hoặc chuỗi không dừng có thể làm CI chưa đủ rộng. CI 0 trong trường hợp không quan sát sự kiện không chứng minh xác suất thật bằng 0.

MAE trên TP trong 15° khác `mean_error` của khung xuất đúng số góc. Khả năng phát hiện đủ nguồn khác việc xuất đủ số góc. Góc trùng trong một khung được giữ nguyên, và phép thử bỏ trùng chỉ là phân tích nhạy cảm.

p-value lớn không chứng minh dữ liệu thật. Không dùng thời gian tạo/sửa file làm tiêu chí nguồn hay chất lượng. Không tạo mẫu hoặc nhiễu để làm thay đổi phân phối.

## Tái lập

Bản gốc đã đối chiếu SHA-256: `D:\Downloads\NCKH\STM32F4-vs-INMP441-AI\STM32F4-vs-INMP441-AI\data\_archive\data_quality_before_20261015_141043_680418`.

`snapshot_manifest.json` liệt kê từng CSV gốc và checksum. Cài các phiên bản thư viện trong `reproduce/requirements.txt`, rồi chạy:

```
python reproduce/run_again.py --output THU_MUC_KET_QUA_MOI --source THU_MUC_SNAPSHOT_GOC
```

Thư mục nguồn phải chứa các nhánh CSV gốc cùng `_data_sources.json` của snapshot. Thư mục đầu ra mới không được tồn tại trước. Lệnh chỉ tái lập phân tích snapshot; không sửa dữ liệu đang dùng. Seed resampling là 20261015. Mã tái lập đã được chạy kiểm tra trên bốn CSV gốc đại diện; số đếm, biểu đồ tần suất và CI từng tệp khớp lần chạy đầy đủ.

`file_checksums.json` kiểm chứng các tệp kết quả. `verification.json` và `browser_verification.json` ghi các kiểm tra đã thực hiện. Gói kết quả không chứa toàn bộ 554 MB bản gốc; các bản gốc vẫn nằm nguyên trong thư mục sao lưu nêu trên.
