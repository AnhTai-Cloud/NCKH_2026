# NCKH 2026 — Định hướng nguồn âm trên STM32F4

Project xử lý tín hiệu từ microphone INMP441 để phát hiện hướng của một,
hai hoặc ba nguồn âm; so sánh các cấu hình có và không có bộ phân loại AI.
Firmware hiện tại dùng AI để phân loại tiếng cần giữ và tiếng nhiễu.

## Thành phần

- [FFT/B1](FFT/B1): firmware STM32F411CEU6 và project Keil uVision.
- [Python](Python/README.md): thu UART, xem radar, đọc CSV và tính các chỉ số.
- [data](data): tập dữ liệu đang dùng và hồ sơ nguồn đi kèm.
- [Paper](Paper): bản báo cáo, tài liệu tham khảo và các lần đánh giá.
- [AI.md](AI.md): tài liệu định hướng cũ đã có trong repository;
  mô tả trong tài liệu này không thay thế việc kiểm tra firmware hiện tại.

## Dữ liệu hiện tại

Bản rút gọn ngày 16/10/2026 gồm **4.123 CSV, 673.000 khung**, trong đó
có 6 CSV chỉ có tiêu đề. Các nhánh `1sourceAI`, `1sourceNOAI`,
`2sourceAI`, `2sourceNOAI`, `3sourceAI` và `3sourceNOAI` chứa dữ liệu
đang hoạt động. Hai nhánh 0 nguồn hiện chưa có CSV.

Mỗi nhóm số nguồn × chế độ AI/không AI × khoảng cách có tối đa 35.000
khung sau rút gọn; nhóm ít hơn được giữ nguyên. Một số cấu hình hai nguồn
không đủ dữ liệu, và hai nguồn không AI tại 10 cm chưa có dữ liệu.

Tập hiện có gồm dữ liệu mô phỏng có hồ sơ, dữ liệu khớp bản ghi thu cũ và
dữ liệu chưa xác minh. Không xem toàn bộ tập là kết quả đo phần cứng đã
được xác thực độc lập. Giữ kèm [data/_data_sources.json](data/_data_sources.json)
khi sao chép hoặc phân tích CSV. Hồ sơ này lưu nguồn, checksum và lịch sử
xử lý mà không thêm cột nguồn vào CSV.

Việc rút gọn chọn theo cấu hình và hồ sơ nguồn, không chọn theo precision,
recall, F1 hay MAE. Các ô số đo được giữ nguyên; các đoạn CSV bị cắt chỉ
đánh lại `sample` từ 1. Quy tắc và khoảng dòng gốc nằm trong nhật ký rút gọn.

## Báo cáo và biểu đồ

- **Hiện tại:** [đánh giá sau rút gọn](data/_reports/frame_reduction_20261016_214709_265890/index.html)
  và [nội dung tham khảo để điền bảng](data/_reports/frame_reduction_20261016_214709_265890/noi_dung_dien_bao_cao.md).
- **Hiện tại:** [bộ 9 biểu đồ](Paper/bieu_do_du_lieu_rut_gon_20261016/index.html),
  [chú thích](Paper/bieu_do_du_lieu_rut_gon_20261016/chu_thich_chen_bao_cao.md)
  và [gói PNG/SVG](Paper/bieu_do_du_lieu_rut_gon_20261016/bieu_do_nckh.zip).
- **Trước rút gọn:** [kiểm định toàn bộ tập cũ](data/_reports/data_quality_audit_20261015_141043_680418/index.html)
  và [đối chiếu khả năng điền báo cáo](data/_reports/paper_readiness_20261016/index.html).

Các kết quả trước rút gọn dùng 13.782 CSV và 16.216.648 khung, không phải
quy mô của tập hiện tại. Những báo cáo cũ hơn trong `Paper` cũng mô tả
phiên bản dữ liệu tại thời điểm tạo báo cáo. Bản PDF bài báo chưa được
tự động thay bảng hoặc thay hình bằng các kết quả mới.

Để xem trang HTML, tải/clone repository rồi mở `index.html` tương ứng trên
máy. GitHub hiển thị mã nguồn HTML; các ảnh PNG và tài liệu Markdown có thể
xem trực tiếp trên GitHub. Hình 5.4/H17 chưa được dựng từ giả định vì thiếu
hồ sơ xác nhận các kịch bản nhiễu cụ thể.

## Thu và đánh giá

1. Mở `FFT/B1/B1.uvprojx` bằng Keil, cài các pack được khai báo trong project
   và build/nạp firmware phù hợp với cấu hình cần đo.
2. Cài Python và các thư viện: `python -m pip install -r Python/requirements.txt`.
3. Đọc [hướng dẫn Python](Python/README.md), đặt cổng COM và cấu hình thu,
   rồi chạy `python Python/measure_doa.py`.

Nhãn `MODE` trong Python không tự đổi firmware; chọn AI/không AI phải khớp
bản firmware đã nạp. `AI_ENABLE` trong mã nguồn hiện tại mặc định bằng 0.
Ứng dụng radar Windows nằm ở `Python/visualize_doa.exe`.

Các chỉ số dùng ghép một-một với ngưỡng sai số vòng tròn 15°. Cần phân biệt
recall trên mọi khung với recall bỏ khung trống; MAE trên các cặp ghép đúng
khác với `mean_error` trong CSV. Đọc định nghĩa và giới hạn trong từng báo
cáo trước khi sử dụng làm kết quả nghiên cứu.

## Phạm vi bản đưa lên Git

Repository chứa mã nguồn, tập CSV đang dùng, hồ sơ nguồn, các báo cáo được
chọn ở trên và tài liệu trong `Paper`. Các bản gốc, bản sao lưu, tập mô
phỏng thay thế, thư viện cài tạm và kết quả build Keil vẫn được giữ tại máy
ban đầu, không đưa vào Git. Không có số đo nào được sửa trong lần cập nhật Git.

Bốn tệp trung gian lớn của lần kiểm định cũ không đưa lên Git:
`sequence_blocks.jsonl.gz`, `file_features_before.jsonl.gz`,
`file_features_after.jsonl.gz` và `file_features_before.initial_pass.jsonl.gz`.
Kết quả cuối, cảnh báo, kiểm định, mã phân tích và nhật ký thay đổi vẫn được giữ.
Checksum trong báo cáo lịch sử có thể liệt kê cả những tệp trung gian này.

Các thư mục `reproduce` lưu mã của lần phân tích gốc; một số bước cần
snapshot đầy đủ và đường dẫn/runtime của máy ban đầu. Repository không chứa
toàn bộ snapshot trước rút gọn, nên không thể chạy lại mọi phân tích lịch sử
chỉ từ tập hiện tại. Các đường dẫn tuyệt đối trong hồ sơ chỉ nơi lưu bản gốc
trên máy ban đầu, không phải tệp có sẵn sau khi clone.

Git giữ nguyên byte của các tệp để bảo toàn checksum. Thời gian checkout
không được dùng làm bằng chứng về thời điểm thu hay nguồn gốc dữ liệu.
