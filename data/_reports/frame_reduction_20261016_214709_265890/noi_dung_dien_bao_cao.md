# Dữ liệu rút gọn và số liệu bổ sung báo cáo

Ngày xử lý: 16/10/2026.

Tổng khung: 16.216.648 → 673.000. Tổng CSV đang hoạt động: 13.782 → 4.123.

19 nhóm vượt 40.000 khung được rút về 35.000. Bốn nhóm nhỏ giữ nguyên số khung; nhóm hai nguồn Không AI tại 10 cm vẫn chưa có dữ liệu. Không tạo khung để đạt chỉ tiêu.

Chia hạn mức tỷ lệ theo tổng khung gốc của từng bố trí góc × hồ sơ nguồn × nhóm thu. Mỗi tầng không rỗng giữ ít nhất một khung. Thứ tự file và vị trí đoạn lấy được xác định bằng SHA-256 với seed 20261016, trước khi đánh giá chỉ số.

Giữ các file đầy đủ theo thứ tự đã chọn, sau đó lấy một đoạn liên tiếp trong file cuối nếu cần. Quy tắc không xem góc đo, lỗi, TP/FP, khung trống hay mức lặp khi chọn. Tất cả bố trí góc hiện có được giữ.

Góc, số hướng, góc mục tiêu, cự ly và các cột sai số của từng khung được giữ nguyên. Chỉ đánh lại sample từ 1 cho file bị cắt để tương thích chương trình đọc; JSON ghi checksum và khoảng dòng trong bản gốc để truy ngược.

Các đầu vào mô phỏng AI/Không AI dùng cùng quy tắc xếp file và điểm bắt đầu khi có cùng nguồn chung. Nếu hạn mức khác nhau, các đoạn cùng file có phần đầu trùng nhau; không xem hai tập con là các phép đo phần cứng độc lập.

Chỉ số có thể thay đổi do chọn ít file và khung hơn. Không chạy lại seed để tìm kết quả tốt hơn. Không tái sử dụng khoảng tin cậy hoặc p-value cũ cho tập đã rút gọn; độ bất định cần được ước lượng trên tập mới khi dùng suy luận thống kê.

Tập rút gọn không đáp ứng mặc nhiên quy trình 1.000 khung × ba lần đo mỗi cấu hình. Với hai nguồn AI có 630 bố trí mỗi cự ly, hạn mức 35.000 chỉ cho trung bình khoảng 56 khung/bố trí; cần ghi đúng quy mô này trong bài.

Nguồn gốc dữ liệu được giữ trong JSON bên ngoài CSV. Rút gọn không thay mô phỏng thành kết quả thực nghiệm; các hạn chế về nhiễu, thời lượng thu, phiên bản firmware và đối chứng trong báo cáo trước vẫn còn.

Bản gốc đầy đủ được giữ trong thư mục sao lưu. Thời điểm sửa của file bị cắt là lúc xử lý tập con, không phải thời điểm thu; không sửa dấu thời gian để mô phỏng thời gian đo.

## Bảng 5.2 · Không AI

Bảng mô tả tập hỗn hợp hiện có. R/F1 tính cả khung trống.

| Số nguồn | r (m) | MAE (°) | P (%) | R (%) | F1 (%) |

| --- | --- | --- | --- | --- | --- |

| 1 | 0.1 | 3.76 | 90.90 | 89.80 | 90.35 |

| 1 | 0.2 | 3.66 | 86.44 | 87.36 | 86.90 |

| 1 | 0.3 | 4.05 | 78.63 | 88.92 | 83.46 |

| 1 | 0.4 | 7.05 | 52.42 | 64.39 | 57.79 |

| 2 | 0.1 | — | — | — | — |

| 2 | 0.2 | 6.48 | 92.64 | 64.33 | 75.93 |

| 2 | 0.3 | 5.91 | 93.63 | 62.46 | 74.93 |

| 2 | 0.4 | 7.75 | 58.53 | 36.95 | 45.31 |

| 3 | 0.1 | 5.87 | 71.17 | 31.27 | 43.45 |

| 3 | 0.2 | 6.40 | 71.87 | 31.03 | 43.35 |

| 3 | 0.3 | 6.75 | 57.54 | 27.20 | 36.94 |

| 3 | 0.4 | 6.67 | 55.03 | 24.89 | 34.27 |

## Bảng 5.3 · Có AI

Bảng mô tả tập hỗn hợp hiện có. R/F1 tính cả khung trống.

| Số nguồn | r (m) | MAE (°) | P (%) | R (%) | F1 (%) |

| --- | --- | --- | --- | --- | --- |

| 1 | 0.1 | 3.66 | 83.90 | 88.08 | 85.94 |

| 1 | 0.2 | 3.51 | 89.86 | 81.63 | 85.54 |

| 1 | 0.3 | 4.03 | 84.96 | 83.63 | 84.29 |

| 1 | 0.4 | 7.05 | 56.74 | 47.90 | 51.95 |

| 2 | 0.1 | 5.32 | 82.74 | 55.51 | 66.44 |

| 2 | 0.2 | 7.34 | 81.66 | 52.22 | 63.71 |

| 2 | 0.3 | 9.32 | 81.66 | 49.53 | 61.66 |

| 2 | 0.4 | 5.96 | 75.76 | 31.48 | 44.47 |

| 3 | 0.1 | 5.91 | 75.25 | 28.26 | 41.09 |

| 3 | 0.2 | 6.43 | 74.88 | 28.05 | 40.81 |

| 3 | 0.3 | 6.77 | 59.99 | 23.69 | 33.96 |

| 3 | 0.4 | 6.69 | 57.14 | 22.37 | 32.16 |

## Tác động của rút gọn

| Nguồn | Chế độ | cm | ΔP (điểm %) | ΔR toàn khung | ΔR có hướng | ΔF1 toàn khung | ΔMAE (°) |

| --- | --- | --- | --- | --- | --- | --- | --- |

| 1 | Có AI | 10 | -0.53 | -0.75 | -0.43 | -0.63 | 0.02 |

| 1 | Có AI | 20 | -0.15 | -0.23 | -0.19 | -0.19 | -0.01 |

| 1 | Có AI | 30 | -0.10 | -0.05 | -0.01 | -0.08 | 0.14 |

| 1 | Có AI | 40 | -0.20 | -1.21 | -0.80 | -0.79 | 0.20 |

| 1 | Không AI | 10 | 0.27 | -0.30 | 0.08 | -0.01 | -0.05 |

| 1 | Không AI | 20 | 0.49 | 1.92 | 0.34 | 1.20 | -0.07 |

| 1 | Không AI | 30 | 0.17 | 0.31 | 0.30 | 0.23 | 0.17 |

| 1 | Không AI | 40 | 0.27 | -0.34 | -0.30 | 0.03 | 0.05 |

| 2 | Có AI | 10 | -0.02 | -0.02 | -0.19 | -0.02 | 0.13 |

| 2 | Có AI | 20 | -0.09 | 0.07 | 0.08 | 0.03 | 0.09 |

| 2 | Có AI | 30 | 1.07 | 0.61 | 0.86 | 0.78 | 0.06 |

| 2 | Có AI | 40 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

| 2 | Không AI | 20 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

| 2 | Không AI | 30 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

| 2 | Không AI | 40 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

| 3 | Có AI | 10 | -0.54 | -0.27 | -0.18 | -0.37 | 0.01 |

| 3 | Có AI | 20 | 0.27 | -0.25 | 0.16 | -0.22 | -0.03 |

| 3 | Có AI | 30 | 0.15 | 0.05 | 0.08 | 0.08 | -0.03 |

| 3 | Có AI | 40 | 0.11 | 0.16 | 0.19 | 0.18 | -0.05 |

| 3 | Không AI | 10 | -0.62 | -0.03 | -0.15 | -0.14 | -0.01 |

| 3 | Không AI | 20 | 0.50 | -0.14 | 0.19 | -0.05 | -0.03 |

| 3 | Không AI | 30 | -0.13 | 0.06 | -0.08 | 0.03 | -0.02 |

| 3 | Không AI | 40 | 0.01 | 0.04 | 0.16 | 0.04 | -0.06 |

Chỉ tính được 23/24 dòng của Bảng 5.2–5.3; thiếu hai nguồn Không AI tại 10 cm. Các bảng nhiễu, thời gian thực thi, điện năng và đối chứng phiên bản firmware vẫn cần bằng chứng theo đánh giá toàn bộ trước đó.
