# D23 TRẦN ANH TÀI
*báo cáo công việc ngày 5/9/2026*

# A. Công việc đã làm

1. Phân tích kiến trúc xử lý DOA hiện tại trên STM32F411CEU6.
2. Xác định hướng triển khai Edge AI: huấn luyện mô hình trước trên máy tính, sau đó chuyển mô hình sang dạng C để nạp vào Flash của STM32F4.
3. Xây dựng định hướng sử dụng MLP để xử lý phần SCORE và dự đoán hướng đến của nguồn âm.
4. Thiết kế hệ thống theo cơ chế pipeline nhằm duy trì xử lý real-time khi dữ liệu âm thanh liên tục được nhận từ 4 microphone.
5. Định hướng đầu ra tập trung vào hai đại lượng chính: góc đến của nguồn âm

# B. Công việc chi tiết

## 1. Kiến trúc tổng thể

```text
4 Microphone
     ↓
I2S + DMA
     ↓
Buffer 
     ↓
FFT + Hann Window
     ↓
Phase giữa 4 microphone
     ↓
ScorePV theo từng bin tần số
     ↓
Radar Histogram 360 điểm
     ↓
Accumulation + Spatial Smoothing
     ↓
Peak Detection
     ↓
Lấy vùng ±X° quanh Peak
     ↓
MLP Edge AI
     ↓
Góc dự báo + Biên độ nguồn âm
```

Mục tiêu là giữ phần DSP hiện tại làm tầng trích xuất đặc trưng, sau đó AI đảm nhiệm phần dự báo cuối thay vì thay thế toàn bộ thuật toán DOA.

## 2.Histogram 360 điểm

`radar_histogram[360]` biểu diễn mức độ tin cậy của nguồn âm tại từng góc từ `0°` đến `359°`.

Ví dụ:

```text
Góc       Score
87°       350
88°       520
89°       760
90°       820  ← Peak
91°       740
92°       500
```

Mỗi bin tương ứng với 1°, do đó giữ 360 điểm giúp hệ thống duy trì độ phân giải góc cao.


### Trích xuất vùng quanh Peak

- Sau khi histogram được xử lý, hệ thống tìm các peak có score lớn.

```text
Peak 1 = 90°
Peak 2 = 210°
Peak 3 = 315°
```

Nếu chọn cửa sổ `±10°`:

```text
Peak 90°
→ 80°, 81°, ..., 89°, 90°, ..., 99°, 100°
```

Tổng cộng 21 giá trị cho một peak.

Với tối đa 3 nguồn:

```text
3 × 21 = 63 đặc trưng
```

Thay vì đưa toàn bộ 360 điểm vào MLP.

Giá trị `±10°` là tham số cần khảo sát; có thể thử `±5°`, `±8°`, `±10°`, `±15°` và chọn theo validation.

- Xử lý vòng 0°/360°

Histogram là dữ liệu vòng tròn nên phải xử lí tại các điểm gần và tại biên.

Ví dụ:

```text
Peak = 2°
```

với cửa sổ ±10° sẽ lấy:

```text
352° ... 359°, 0° ... 12°
```


## 4. Mô hình MLP

MLP  là mạng neural network gồm input layer, hidden layer và output layer.

Một neuron thực hiện:

```text
y = activation(Wx + b)
```

MLP phù hợp vì dữ liệu đưa vào AI đã được DSP chuyển thành các đặc trưng nhỏ:

```text
Histogram → Peak → vùng lân cận Peak
```

## 5. Đầu vào mô hình

Phương án ban đầu là lấy histogram quanh peak:

```text
[
 Score(-10°),
 Score(-9°),
 ...
 Score(-1°),
 Score(0°),
 Score(+1°),
 ...
 Score(+10°)
]
```
 và một số đặc trưng dưới đây
```text
Peak score
Tổng score trong cửa sổ
Độ rộng peak
```

Nhưng ưu tiên ban đầu là giữ input nhỏ để giảm kích thước model. Nếu vượt quá có thể cắt giảm

## 6. Đầu ra mô hình

Mô hình tập trung vào:

```text
Output 1: Direction
Output 2: Amplitude
```

Ví dụ:

```text
Angle = 87.6°
Amplitude = 0.81
```

Amplitude được chuẩn hóa về khoảng `0 → 1` trong quá trình training.

## 7. Xử lý đa nguồn âm

Khi histogram có nhiều peak:

```text
Histogram 360
      ↓
Peak Detection
      ↓
Peak 1 → ±10° → MLP
Peak 2 → ±10° → MLP
Peak 3 → ±10° → MLP
```

Mỗi peak được xử lý như một nguồn âm.

Ví dụ đầu ra:

```text
Nguồn 1: 87.4°   Amplitude = 0.82
Nguồn 2: 211.8°  Amplitude = 0.61
Nguồn 3: 314.5°  Amplitude = 0.43
```


## 8. Pipeline real-time nhằm khắc phục độ trễ

Pipeline dự kiến:

```text
Stage 1: I2S + DMA
        ↓
Stage 2: Extract Audio
        ↓
Stage 3: FFT
        ↓
Stage 4: Score / Histogram
        ↓
Stage 5: Peak Detection
        ↓
Stage 6: MLP Inference
        ↓
Angle + Amplitude
```

Trong khi AI xử lý frame hiện tại, DMA có thể tiếp tục nhận dữ liệu cho frame tiếp theo.

```text
Frame N:
DMA → FFT → Score → AI

Frame N+1:
       DMA → FFT → Score → AI

Frame N+2:
              DMA → FFT → Score → AI
```

Mục tiêu là duy trì xử lý liên tục và giảm thời gian chờ giữa các frame.

## 9. Quản lý tài nguyên STM32F4

Giới hạn tài nguyên mục tiêu:

```text
Khoảng 50–60 kB
```

Do đó mô hình không được quá lớn.

Kiến trúc ban đầu có thể khảo sát:

```text
21-23 tùy lượng đặc trưng được thêm vào
 ↓
32
 ↓
16
 ↓
2
```


Kiến trúc cuối cùng sẽ được lựa chọn dựa trên:

```text
Accuracy
Flash
RAM
Inference time
```

Có thể tiếp tục tối ưu bằng quantization hoặc loại bỏ bớt đặc trưng không cần thiết thông qua đánh giá, khảo sát

## 10. Quy trình train model và áp xuống kit

Quy trình:

```text
Thu dữ liệu thực tế
       ↓
Python
       ↓
Tạo dataset
       ↓
Train MLP
       ↓
Validation / Test
       ↓
Export weight + bias
       ↓
Chuyển sang C
       ↓
Nạp vào Flash STM32
       ↓
Inference real-time
```

## 11. Manual C export

Sau khi train trên Python, trọng số và bias được export thành mảng C:

```c
const float W1[21][32] = {
    ...
};

const float b1[32] = {
    ...
};

const float W2[32][16] = {
    ...
};

const float b2[16] = {
    ...
};

const float W3[16][2] = {
    ...
};

const float b3[2] = {
    ...
};
```

STM32 thực hiện:

```text
x
 ↓
W1x + b1
 ↓
ReLU
 ↓
W2x + b2
 ↓
ReLU
 ↓
W3x + b3
 ↓
Output
```


## 12. Đầu ra hệ thống

Thay vì chỉ xuất:

```text
Peak = 90°
```

hệ thống hướng tới:

```text
Source 1:
Angle = 87.6°
Amplitude = 0.82

Source 2:
Angle = 211.4°
Amplitude = 0.61

Source 3:
Angle = 315.2°
Amplitude = 0.43
```

Các kết quả có thể gửi qua UART để Python hiển thị trên polar plot, hoặc demo trên màn tft.


# C. Khó khăn đang gặp

# D. Công việc tiếp theo
1. Thu data và tiến hành xây model
2. Tự động tìm peak và cắt vùng ±X° quanh từng peak.
3. Train và so sánh các kiến trúc MLP nhỏ.
4. Đánh giá MAE góc, sai số amplitude và khả năng xử lý đa nguồn.
5. Benchmark Flash, RAM và inference time.
6. Chọn kiến trúc MLP phù hợp giới hạn 50–60 kB.
7. Export weight/bias sang C.
8. Viết hàm MLP inference chạy trực tiếp trên STM32F4.
9. Tích hợp MLP vào pipeline I2S → FFT → Score → Histogram → Peak → AI.
10. Sửa Python polar monitor để hiển thị đồng thời **góc + amplitude** từ STM32.
11. Kiểm tra khả năng real-time khi nguồn âm thay đổi liên tục.
