# Kiểm định chất lượng dữ liệu DOA

Đã kiểm tra 13.782 CSV và 16.216.648 dòng trong các nhánh dữ liệu đang dùng. Các bản sao lưu, báo cáo và thư mục kịch bản không được đếm lại thành các phép đo độc lập.

Chỉ sửa thứ tự cột của 59 CSV hai nguồn không AI theo bộ đọc Python hiện tại. Mọi giá trị theo tên cột được giữ nguyên. Không có sai số góc hay ô số lượng hướng nào cần sửa theo quy tắc đã xác định. Sáu file chỉ có tiêu đề được giữ nguyên; không thêm mẫu cho file 200 khung.

Có 13.191 file khớp hồ sơ mô phỏng bằng SHA-256 hoặc khôi phục chính xác nhãn nguồn từng bị loại bỏ. Có 149 file khớp hồ sơ bản ghi thu cũ; sự trùng khớp này không xác thực độc lập việc thu bằng phần cứng. 442 file chưa đủ bằng chứng xác minh. Không dùng thời gian tạo/sửa file hay p-value để phân loại nguồn.

Tỷ lệ phát hiện đủ ba nguồn trong bộ hiện có rất thấp dù precision có thể cao. Một vài góc đúng trên mỗi khung không đồng nghĩa phát hiện đồng thời mọi nguồn. Các bảng tính đủ nguồn bằng ghép một-một trong 15° và tách riêng số khung xuất đủ số lượng góc.

Dữ liệu mô phỏng N2 dùng cùng đầu vào cho AI và không AI, rồi lọc hướng bằng ngưỡng giả định 0,25/0,35/0,15. AI không sửa góc. Nền nhiễu quạt/bàn phím và điểm phân loại là giả định, không phải nhãn âm hoặc SNR đã đo. Vì vậy chênh lệch chỉ số trong kịch bản này không chứng minh lợi thế trên mạch.

Có 8.604 khung chứa hướng góc giống hệt nhau. Giữ nguyên chúng vì chưa xác minh được nguyên nhân. Phân tích nhạy cảm thử chỉ tính hướng phân biệt làm giảm 7.176 TP và 1.428 FP; đây là phép đánh giá phụ, không được ghi vào CSV. Với nguồn sát nhau, hai hướng trùng có thể được ghép đúng hai mục tiêu trong dung sai 15° mà chưa chứng minh khả năng phân giải hai nguồn.

Tìm thấy 32.246 nhóm cửa sổ 20 khung trùng có đủ biến thiên; 32.243 nhóm nằm đúng trong cặp AI/đối chứng mô phỏng dùng chung đầu vào. Ba nhóm khác cần ngữ cảnh nguồn. Trùng chuỗi góc không chứng minh trùng âm thanh hoặc gian lận.

Góc nguyên và chuỗi lặp có thể xuất phát từ lượng tử hóa 1°, giữ vết hướng, cửa sổ AI, ngưỡng trễ, tín hiệu ổn định hoặc bộ tạo mô phỏng. CSV hướng không đủ phân biệt riêng từng nguyên nhân đối với nhóm chưa xác minh. Không thêm nhiễu để phá các mẫu lặp.

Khoảng cách, góc tách, phản xạ, trường gần và ngưỡng phát hiện đều có thể ảnh hưởng chỉ số. Tuy nhiên không có âm thanh gốc, SNR, trạng thái hoạt động từng nguồn hoặc nhật ký phiên thu để xác định nguyên nhân vật lý. Xu hướng trong phần mô phỏng còn chịu các tham số đã đặt trước.

MAE trên TP chỉ dùng những góc được ghép đúng trong 15°. mean_error trong CSV chỉ có ở khung xuất đúng số lượng hướng và dùng tất cả sai số của phép ghép tổng sai số nhỏ nhất, không cắt ở 15°. MAE giảm ở cự ly xa có thể do chỉ còn các góc dễ được phát hiện, không nhất thiết góc đo tốt hơn.

File có 26.248 khung và các nhóm 100/200/300/600/1.800/2.000 khung gây khác biệt trọng số khi gộp. Báo cáo giữ nguyên độ dài và cung cấp cả chỉ số gộp theo khung, trung bình theo CSV và trung bình theo bố trí. Không coi các khung chồng lấp là các phép thử độc lập.

Các điểm thiếu vẫn giữ nguyên: hai nguồn không AI ở 10 cm chưa có dữ liệu; hai nguồn AI ở 40 cm chỉ có một bố trí. Sáu file chỉ có tiêu đề không tham gia tính hiệu năng. Bộ hiện tại chưa thể thay thế thí nghiệm đối chứng phần cứng có nhãn âm, trạng thái nguồn và nhật ký thu.

Hồ sơ xử lý trước ghi nhận 40 file bị loại khi recall bỏ trống, precision hoặc F1 bỏ trống dưới 55%. Bản ZIP chứa đủ 40 file đã được đối chiếu checksum với nhật ký. Đây là bằng chứng chọn mẫu theo kết quả: các file giữ lại không còn là tập ngẫu nhiên đại diện cho mọi lần thu. Không khôi phục chồng các phiên bản cũ vào dữ liệu hiện tại và không loại thêm file; phân tích ảnh hưởng chọn mẫu được xuất riêng trong historical_selection_bias.json.

## Phạm vi chỉnh sửa

59 file; 5.900 dòng chỉ đổi thứ tự cột; 0 ô giá trị thay đổi. Chỉ số P/R/F1, MAE, phát hiện đủ nguồn và khoảng tin cậy trước–sau không đổi.

## Nguồn và giới hạn

- Khớp bản ghi thu cũ: 149 CSV, 232800 dòng.
- Mô phỏng có hồ sơ: 13191 CSV, 15838200 dòng.
- Chưa xác minh: 442 CSV, 145648 dòng.

Xem index.html, các bảng CSV, JSONL.gz và thư mục reproduce để tra cứu phương pháp, từng file, từng cấu hình, dòng nghi vấn và kiểm định. Bản sao gốc nằm tại D:\Downloads\NCKH\STM32F4-vs-INMP441-AI\STM32F4-vs-INMP441-AI\data\_archive\data_quality_before_20261015_141043_680418.
