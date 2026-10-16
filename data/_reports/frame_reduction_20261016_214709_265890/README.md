# Tập dữ liệu rút gọn – 16/10/2026

Đã cập nhật trực tiếp tám nhánh 0–3sourceAI/NOAI đang hoạt động. Các nhóm trên 40.000 khung được rút về 35.000, nhóm nhỏ hơn giữ nguyên. Tổng cộng còn 673.000 khung trong 4.123 CSV, gồm 6 CSV chỉ có tiêu đề. Mọi bố trí góc ban đầu được giữ.

`index.html` và `noi_dung_dien_bao_cao.md` trình bày số khung, chỉ số trước–sau và hai bảng để tham khảo cho bài. Không dùng khoảng tin cậy hoặc p-value của tập đầy đủ làm kết quả suy luận cho tập con mới.

`selection_plan.json` lưu quy tắc, seed, mỗi file được giữ/cắt/chuyển khỏi nhánh hoạt động và khoảng dòng gốc. `file_metrics_after.json` lưu chỉ số đọc lại từ toàn bộ tập con. Trường origin trong kế hoạch và bảng chỉ số nói về nguồn của bản cha tại lúc chụp; file bị cắt là tập con đã xử lý, không còn là bản đầy đủ khớp byte hồ sơ cũ. Hồ sơ nguồn của file hiện có được cập nhật ở data/_data_sources.json và bản sao trong thư mục _subsets tương ứng.

`staged_verification.json` xác nhận mọi ô đo của các dòng được giữ khớp bản cha, `sample` đánh lại đúng quy tắc. `native_reader_verification.json` kiểm tra chương trình đọc không đổi trên đại diện đủ 23 nhóm. `installation.json` và `installation_log.jsonl` ghi cập nhật thư mục chính, checksum và đường dẫn bản gốc. Bản gốc đầy đủ, hồ sơ nguồn trước chỉnh và snapshot_manifest.json nằm trong thư mục sao lưu được ghi trong installation.json. Không xóa bản sao lưu.

Việc chọn theo số nguồn, cự ly, bố trí góc và hồ sơ nguồn không dựa vào số đo hoặc chỉ số. Chỉ các cặp mô phỏng có hồ sơ đầu vào chung mới dùng cùng seed chọn file/điểm bắt đầu; các file trùng tên khác nguồn không bị coi mặc nhiên là cùng phiên. Không thêm nhiễu, không tạo mẫu, không sửa hướng, không sửa sai số và không thay dấu thời gian để thể hiện thời gian đo.

Mã ở reproduce/ lưu cách xử lý đã áp dụng. Trong workspace, các bản chạy gốc nằm ở tmp/frame_reduction_20261016 và phụ thuộc common.py, runtime và các thư viện của lần kiểm định. Các bước có kiểm tra trạng thái để tránh cắt lại tập đã rút gọn. Một lỗi kiểm tra cặp cùng tên nhưng khác độ dài được sửa trước khi tạo tập con; toàn bộ snapshot nguyên vẹn đã được xác minh và sử dụng lại, không vẽ lại seed dựa trên kết quả chỉ số.
