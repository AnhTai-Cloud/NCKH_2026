# Biểu đồ NCKH trên tập rút gọn – 16/10/2026

H14 là sơ đồ thiết kế để tham khảo cho Hình 5.1; H15 và H16 là biểu đồ Hình 5.2 và Hình 5.3 từ tập đang dùng. S01–S06 bổ sung phân tích theo cự ly, phát hiện đủ nguồn, góc tách, khung trống và độ phủ. Mỗi hình có PNG 240 dpi và SVG có chữ dạng văn bản. Đọc chu_thich_chen_bao_cao.md trước khi chèn hình.

Các kết quả mô tả tập hiện có, gồm mô phỏng và nguồn chưa xác minh. Sơ đồ không xác nhận bố trí thực tế đã đo. Không tạo H17 từ giả định vì chưa xác nhận các kịch bản nhiễu cụ thể trong bài. Khoảng bootstrap tính mới trên tập con và chỉ có ý nghĩa có điều kiện theo cụm; các vùng P10–P90 theo độ tách là mức phân tán giữa các bố trí góc, không phải CI.

plot_data.json lưu số đếm và mọi chỉ số trên biểu đồ. input_manifest.json đối chiếu checksum toàn bộ 4.123 CSV; CSV và PDF gốc được giữ nguyên. Thời điểm sửa được ghi để xác nhận bảo toàn, không dùng đánh giá nguồn gốc. ZIP gồm ảnh, chú thích và dữ liệu biểu đồ; không bao gồm các CSV đầu vào.

reproduce/build.py lưu thuật toán dựng hình của lần chạy. Bản chạy trong workspace là tmp/report_figures_20261016/build.py, dùng common.py và các thư viện của lần kiểm định; đầu vào là file_metrics_after.json đã đối chiếu checksum với mọi CSV đang hoạt động. Thiếu CSV gốc thì không thể tái xác minh nguồn chỉ bằng biểu đồ hoặc JSON.
