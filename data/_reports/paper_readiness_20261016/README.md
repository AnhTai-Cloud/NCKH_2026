# Đối chiếu dữ liệu và báo cáo NCKH – 16/10/2026

Mở `index.html` để xem mức độ sẵn sàng của từng bảng/hình, lọc theo hồ sơ nguồn và xem các biểu đồ. `noi_dung_dien_bao_cao.md` chứa bảng số và đoạn văn để tham khảo khi cập nhật bài. Hai bảng số chính mô tả tập hỗn hợp; không coi là xác nhận đã đo phần cứng trong đúng điều kiện của bài.

`inventory.json` lưu SHA-256 từng CSV và thời điểm sửa chỉ làm thông tin phụ. `assessment.json` lưu số đếm, các chỉ số, nguồn gốc, 144 điều kiện theo kế hoạch và bố trí góc thực có. `paper_evidence.json` lưu checksum PDF và đầy đủ trang văn bản liên quan. `verification.json` và `browser_verification.json` ghi kiểm tra số liệu, bảo toàn đầu vào và giao diện.

Các kết quả kiểm định chi tiết, bootstrap và đặc trưng từng file được dùng lại từ `../data_quality_audit_20261015_141043_680418/` chỉ sau khi xác nhận toàn bộ nội dung CSV và hồ sơ nguồn vẫn khớp SHA-256. Không chạy lại các kiểm định không bị ảnh hưởng bởi thay đổi dữ liệu. Các tổng TP/FP/FN, chỉ số gộp, độ phủ và đối chiếu trong lần này được tính lại.

Mã tái lập nằm ở `reproduce/`. Trong workspace gốc, bản chạy ở `tmp/paper_readiness_20261016/` phụ thuộc các hàm `common.py` trong `tmp/data_quality_audit_20261015/` và NumPy/SciPy/matplotlib đã cài cho lần kiểm định trước. Các bước là `review.py inventory`, `review.py analyze`, `report.py`, `verify.py`, và `check_report.mjs` bằng runtime Python/Node đã dùng trong phiên này. Mã kiểm tra sẽ dừng nếu dữ liệu thay đổi trước khi tái sử dụng kết quả kiểm định cũ; phải kiểm định lại các đầu vào thay đổi. Không ghi vào dữ liệu hoặc PDF nguồn.

Đã xuất ba hình ở cả PNG và SVG. Hình 5.3 dùng khoảng bootstrap có điều kiện theo cụm góc/CSV; không phải xác nhận độ chính xác suy rộng của phần cứng. Mã lưu thời gian không được sửa, không đặt tỷ lệ lặp mục tiêu, không tạo thêm mẫu.
