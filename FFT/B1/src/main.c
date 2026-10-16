#include "stm32f4xx.h"
#include "RCC.h"
#include "SysTick.h"
#include "UART.h"
#include "I2S.h"
#include "SPI.h"
#include "TFT.h"
#include "FONT.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "arm_math.h"
#include "AI_Model.h"

// ============================================================
// AUDIO & DSP CONFIG
// ============================================================
#define VOLUME_BOOST        1
#define FFT_SIZE            512
#define PI                  3.14159265358979f
#define SAMPLE_RATE         16000.0f

// ============================================================
// AI FEATURE CONFIG
// ============================================================
#define NUM_BANDS           16
#define MAX_SOURCES         3
#define MAX_FFT_BINS        128
#define FEATURE_ANGLE_GATE  20

// ============================================================
// AI TEMPORAL CONFIG (�� T?I UU CH?NG NH�Y)
// ============================================================
#ifndef AI_ENABLE
#define AI_ENABLE            0   // 0: Python MODE="no_ai"; 1: MODE="ai" (build/flash lai)
#endif
#define AI_WINDOW_SIZE      5

#define AI_MIN_BIN_COUNT    2

#define AI_TRACK_ANGLE_GATE 60

// [S?A QUAN TR?NG 1]: Tang timeout l�n 15 (~480ms) 
// �? kim kh�ng b? r?ng gi?a c�c kho?ng ng?t hoi c?a t? ng?
#define AI_TRACK_TIMEOUT    15

// G�c kim radar l?ch tr�n 3 d? m?i v? l?i, ch?ng nh�y h�nh TFT
#define TFT_ANGLE_JITTER    3 

// ============================================================
// AI DECISION
// ============================================================
#define AI_KEEP_THRESHOLD      0.50f
#define AI_KEEP_ON_THRESHOLD   0.60f
#define AI_KEEP_OFF_THRESHOLD  0.40f
#define AI_FEATURE_MISS_LIMIT  4

// ============================================================
// UART
// ============================================================
#define AI_DEBUG_UART       0
#define SEND_DATASET_UART   0
#define SEND_DOA_TEST_UART  1   // Format AI3: DOA,n,goc1,... (ke ca DOA,0)
#define SEND_EVAL_UART      0   // Khong tron EVAL voi luong do AI3
#ifndef USE_AI_FOR_PYTHON_TEST
#define USE_AI_FOR_PYTHON_TEST 1 // AI_ENABLE=1: gui goc AI giu; 0: gui peak DSP raw
#endif

// Chi mot frame DOA moi frame DSP. Python nhap goc/khoang cach (ground truth),
// mach KHONG tu biet cac nhan nay. Python luu CSV theo format AI3 trong data/.
// AI_ENABLE=0: baseline DSP; AI_ENABLE=1 + USE_AI_FOR_PYTHON_TEST=1: dau ra AI.
#if SEND_DOA_TEST_UART && (SEND_EVAL_UART || SEND_DATASET_UART || AI_DEBUG_UART)
#error "AI3 measurement UART must not mix DOA with EVAL/binary/debug streams"
#endif

// ============================================================
// TFT
// ============================================================
#define RADAR_X             64
#define RADAR_Y             80
#define RADAR_R             60

// ============================================================
// FFT BUFFERS
// ============================================================
float32_t fft_in_m1[FFT_SIZE];
float32_t fft_in_m2[FFT_SIZE];
float32_t fft_in_m3[FFT_SIZE];
float32_t fft_in_m4[FFT_SIZE];

float32_t win_in_m1[FFT_SIZE];
float32_t win_in_m2[FFT_SIZE];
float32_t win_in_m3[FFT_SIZE];
float32_t win_in_m4[FFT_SIZE];

float32_t fft_out_m1[FFT_SIZE];
float32_t fft_out_m2[FFT_SIZE];
float32_t fft_out_m3[FFT_SIZE];
float32_t fft_out_m4[FFT_SIZE];

float32_t radar_histogram[360];
float32_t accum_hist[360];
float32_t smoothed_hist[360];

float32_t hann_window[FFT_SIZE];

arm_rfft_fast_instance_f32 fft_handler;

volatile uint32_t float_index = 0;
volatile uint8_t data_ready = 0;

// ============================================================
// I2S DMA
// ============================================================
extern uint16_t i2s2_rx_buffer[I2S_RX_BUFFER_SIZE];
extern uint16_t i2s3_rx_buffer[I2S_RX_BUFFER_SIZE];

extern volatile uint8_t i2s2_half;
extern volatile uint8_t i2s2_full;

extern volatile uint8_t i2s3_half;
extern volatile uint8_t i2s3_full;

// ============================================================
// AI TEMP DATA
// ============================================================
float bin_power[MAX_FFT_BINS];
int bin_angles[MAX_FFT_BINS];
uint8_t bin_valid[MAX_FFT_BINS];

// ============================================================
// AI TRACKER
// ============================================================
typedef struct
{
    uint8_t active;
    uint8_t timeout;
    uint8_t frame_count;
    uint8_t ai_valid;
    uint8_t keep;
    uint8_t feature_miss;
    int angle;
    float probability;
    float history[AI_WINDOW_SIZE][NUM_BANDS];

} AI_SourceTracker;

static AI_SourceTracker ai_tracks[MAX_SOURCES];
static uint8_t ai_drawn_active[MAX_SOURCES] = {0};
static int ai_drawn_angles[MAX_SOURCES] = {0};

// ============================================================
// SEND DOA TEXT TO PC
// ============================================================
void UART_SendDOAFrame(USART_TypeDef *USARTx, int peak_count, int *peak_angles)
{
    char msg[64];
    if (peak_count <= 0) {
        sprintf(msg, "DOA,0\r\n");
    } else if (peak_count == 1) {
        sprintf(msg, "DOA,1,%d\r\n", peak_angles[0]);
    } else if (peak_count == 2) {
        sprintf(msg, "DOA,2,%d,%d\r\n", peak_angles[0], peak_angles[1]);
    } else {
        sprintf(msg, "DOA,3,%d,%d,%d\r\n", peak_angles[0], peak_angles[1], peak_angles[2]);
    }
    UART_SendString(USARTx, msg);
}

#if SEND_DOA_TEST_UART
// Giong AI3: neu do AI, chi gui tracker active + ai_valid + keep.
// Goi SAU AI_UpdateTrackers, khong gui raw truoc AI roi dem trung frame.
static void UART_SendMeasurementFrame(USART_TypeDef *USARTx, int peak_count, int *peak_angles)
{
#if AI_ENABLE && USE_AI_FOR_PYTHON_TEST
    int kept_count = 0;
    int kept_angles[MAX_SOURCES];
    for (int t = 0; t < MAX_SOURCES; t++) {
        if (ai_tracks[t].active && ai_tracks[t].ai_valid && ai_tracks[t].keep) {
            kept_angles[kept_count++] = ai_tracks[t].angle;
        }
    }
    UART_SendDOAFrame(USARTx, kept_count, kept_angles);
#else
    UART_SendDOAFrame(USARTx, peak_count, peak_angles);
#endif
}
#endif

// ============================================================
// DATASET BINARY UART
// ============================================================
void UART_SendFeatureFrame(USART_TypeDef *USARTx, uint8_t active_count,
                           int *angles, uint8_t *bin_counts, float features[][NUM_BANDS])
{
    UART_Send(USARTx, 0xBB);
    UART_Send(USARTx, active_count);

    for (uint8_t i = 0; i < active_count; i++) {
        uint16_t angle = (uint16_t)angles[i];
        UART_Send(USARTx, (uint8_t)(angle & 0xFF));
        UART_Send(USARTx, (uint8_t)((angle >> 8) & 0xFF));
        UART_Send(USARTx, bin_counts[i]);

        uint8_t *ptr = (uint8_t *)&features[i][0];
        for (int b = 0; b < NUM_BANDS * sizeof(float); b++) {
            UART_Send(USARTx, ptr[b]);
        }
    }
    UART_Send(USARTx, 0x55);
}

#if SEND_EVAL_UART
// Evaluation stream. The PC converts raw angles to the displayed/physical
// convention and can sweep the probability threshold offline.
static void UART_SendEvalFrame(USART_TypeDef *USARTx, int peak_count, int *peak_angles)
{
    char msg[256];
    int angles[MAX_SOURCES];
    int probabilities[MAX_SOURCES];
    int keeps[MAX_SOURCES];
    int count = 0;

#if AI_ENABLE
    for (int t = 0; t < MAX_SOURCES && count < MAX_SOURCES; t++) {
        if (!ai_tracks[t].active || !ai_tracks[t].ai_valid) continue;

        float probability = ai_tracks[t].probability;
        if (probability < 0.0f) probability = 0.0f;
        if (probability > 1.0f) probability = 1.0f;

        angles[count] = ai_tracks[t].angle;
        probabilities[count] = (int)(probability * 1000.0f + 0.5f);
        keeps[count] = ai_tracks[t].keep ? 1 : 0;
        count++;
    }
#else
    count = peak_count;
    if (count > MAX_SOURCES) count = MAX_SOURCES;
    for (int i = 0; i < count; i++) {
        angles[i] = peak_angles[i];
        probabilities[i] = 1000;
        keeps[i] = 1;
    }
#endif

    int offset = sprintf(msg, "EVAL,%d", count);
    for (int i = 0; i < count && offset < (int)sizeof(msg) - 32; i++) {
        offset += sprintf(&msg[offset], ",%d,%d,%d",
                          angles[i], probabilities[i], keeps[i]);
    }
    if (offset < (int)sizeof(msg) - 3) {
        msg[offset++] = '\r';
        msg[offset++] = '\n';
        msg[offset] = '\0';
    }
    UART_SendString(USARTx, msg);
}
#endif

// ============================================================
// CIRCULAR ANGLE DIFFERENCE
// ============================================================
int get_angle_diff(int a1, int a2)
{
    int diff = abs(a1 - a2) % 360;
    return (diff > 180) ? (360 - diff) : diff;
}

// ============================================================
// DRAW RADAR NEEDLE
// ============================================================
void draw_needle(float angle_deg, uint16_t color)
{
    float rad = angle_deg * PI / 180.0f;
    int x_end = RADAR_X + (int)(RADAR_R * cosf(rad));
    int y_end = RADAR_Y - (int)(RADAR_R * sinf(rad));
    drawLine(RADAR_X, RADAR_Y, x_end, y_end, color);
}

// ============================================================
// RESET TRACKER
// ============================================================
static void AI_ResetTracker(int index)
{
    memset(&ai_tracks[index], 0, sizeof(AI_SourceTracker));
}

// ============================================================
// AI INFERENCE
// ============================================================
static void AI_RunWindow(int track_index)
{
    AI_SourceTracker *track = &ai_tracks[track_index];
    float input[32];

    for (int band = 0; band < NUM_BANDS; band++) {
        float sum = 0.0f;
        for (int frame = 0; frame < AI_WINDOW_SIZE; frame++) {
            sum += track->history[frame][band];
        }
        input[band] = sum / (float)AI_WINDOW_SIZE;
    }

    for (int band = 0; band < NUM_BANDS; band++) {
        float mean = input[band];
        float variance_sum = 0.0f;
        for (int frame = 0; frame < AI_WINDOW_SIZE; frame++) {
            float diff = track->history[frame][band] - mean;
            variance_sum += diff * diff;
        }
        float variance = variance_sum / (float)AI_WINDOW_SIZE;
        input[NUM_BANDS + band] = sqrtf(variance);
    }

    float new_probability = AI_Predict(input);

    if (!track->ai_valid) {
        track->keep = (new_probability >= AI_KEEP_THRESHOLD) ? 1 : 0;
    } else {
        if (new_probability >= AI_KEEP_ON_THRESHOLD) {
            track->keep = 1;
        } else if (new_probability <= AI_KEEP_OFF_THRESHOLD) {
            track->keep = 0;
        }
    }

    track->probability = new_probability;
    track->ai_valid = 1;
}

// ============================================================
// SLIDING WINDOW
// ============================================================
static void AI_AddFeatureFrame(int track_index, const float *features)
{
    AI_SourceTracker *track = &ai_tracks[track_index];

    if (track->frame_count < AI_WINDOW_SIZE) {
        for (int band = 0; band < NUM_BANDS; band++) {
            track->history[track->frame_count][band] = features[band];
        }
        track->frame_count++;
    } else {
        for (int frame = 0; frame < AI_WINDOW_SIZE - 1; frame++) {
            for (int band = 0; band < NUM_BANDS; band++) {
                track->history[frame][band] = track->history[frame + 1][band];
            }
        }
        for (int band = 0; band < NUM_BANDS; band++) {
            track->history[AI_WINDOW_SIZE - 1][band] = features[band];
        }
    }

    if (track->frame_count == AI_WINDOW_SIZE) {
        AI_RunWindow(track_index);
    }
}

// ============================================================
// UPDATE AI TRACKERS (T?I UU CO CH? CU?P SLOT)
// ============================================================
static void AI_UpdateTrackers(int peak_count, int *peak_angles,
                              uint8_t *peak_bin_count, float peak_features[][NUM_BANDS])
{
    uint8_t track_used[MAX_SOURCES] = {0};

    for (int p = 0; p < peak_count; p++) {
        int best_track = -1;
        int best_diff = AI_TRACK_ANGLE_GATE + 1;

        for (int t = 0; t < MAX_SOURCES; t++) {
            if (!ai_tracks[t].active || track_used[t]) continue;
            int diff = get_angle_diff(peak_angles[p], ai_tracks[t].angle);
            if (diff <= AI_TRACK_ANGLE_GATE && diff < best_diff) {
                best_diff = diff;
                best_track = t;
            }
        }

        if (best_track == -1) {
            for (int t = 0; t < MAX_SOURCES; t++) {
                if (!ai_tracks[t].active && !track_used[t]) {
                    best_track = t;
                    break;
                }
            }
        }

        // [S?A QUAN TR?NG 2]: B?o v? c�c ngu?n dang du?c gi? (keep == 1)
        if (best_track == -1) {
            int oldest_timeout = 255;
            for (int t = 0; t < MAX_SOURCES; t++) {
                if (track_used[t]) continue;
                
                // TUY?T �?I KH�NG GI?T tracker dang v? kim! Cho n� s?ng h?t timeout.
                if (ai_tracks[t].keep) continue; 

                if (ai_tracks[t].timeout < oldest_timeout) {
                    oldest_timeout = ai_tracks[t].timeout;
                    best_track = t;
                }
            }
            if (best_track != -1) {
                AI_ResetTracker(best_track);
            }
        }

        if (best_track == -1) continue;

        if (!ai_tracks[best_track].active) {
            AI_ResetTracker(best_track);
            ai_tracks[best_track].active = 1;
            ai_tracks[best_track].angle = peak_angles[p];
        }

        ai_tracks[best_track].angle = peak_angles[p];
        ai_tracks[best_track].timeout = AI_TRACK_TIMEOUT;
        track_used[best_track] = 1;

        if (peak_bin_count[p] >= AI_MIN_BIN_COUNT) {
            ai_tracks[best_track].feature_miss = 0;
            AI_AddFeatureFrame(best_track, peak_features[p]);
        } else {
            if (ai_tracks[best_track].feature_miss < 255) {
                ai_tracks[best_track].feature_miss++;
            }
            if (ai_tracks[best_track].feature_miss >= AI_FEATURE_MISS_LIMIT) {
                ai_tracks[best_track].frame_count = 0;
                ai_tracks[best_track].ai_valid = 0;
                ai_tracks[best_track].keep = 0;
                ai_tracks[best_track].probability = 0.0f;
            }
        }
    }

    for (int t = 0; t < MAX_SOURCES; t++) {
        if (!ai_tracks[t].active || track_used[t]) continue;
        if (ai_tracks[t].timeout > 0) {
            ai_tracks[t].timeout--;
        }
        if (ai_tracks[t].timeout == 0) {
            AI_ResetTracker(t);
        }
    }
}

// ============================================================
// TFT (T?I UU CO CH? L?C LU?I G�C - ANTI JITTER)
// ============================================================
static void AI_UpdateTFT(void)
{
    int need_redraw_radar = 0;

    for (int t = 0; t < MAX_SOURCES; t++) {
        int should_draw = (ai_tracks[t].active && ai_tracks[t].ai_valid && ai_tracks[t].keep);

        if (should_draw) {
            int new_angle = ai_tracks[t].angle;
            
            if (!ai_drawn_active[t]) {
                draw_needle((float)new_angle, 0xF800);
                ai_drawn_angles[t] = new_angle;
                ai_drawn_active[t] = 1;
            } 
            // [S?A QUAN TR?NG 3]: Ph?i l?ch > 3 d? m?i v? l?i, ch?ng nh�y
            else if (get_angle_diff(ai_drawn_angles[t], new_angle) > TFT_ANGLE_JITTER) {
                draw_needle((float)ai_drawn_angles[t], 0x0000); 
                need_redraw_radar = 1;
                draw_needle((float)new_angle, 0xF800);
                ai_drawn_angles[t] = new_angle;
            }
        } else {
            if (ai_drawn_active[t]) {
                draw_needle((float)ai_drawn_angles[t], 0x0000); 
                ai_drawn_active[t] = 0;
                need_redraw_radar = 1;
            }
        }
    }

    if (need_redraw_radar) {
        drawCircle(RADAR_X, RADAR_Y, RADAR_R, 0x07E0);
        drawCircle(RADAR_X, RADAR_Y, 2, 0xFFFF);
    }
}

// ============================================================
// C�C H�M X? L� �M THANH GI? NGUY�N B�N DU?I
// ============================================================
void Extract_Audio(uint32_t start_index, uint32_t end_index)
{
    for (uint32_t i = start_index; i < end_index; i += 4) {
        int32_t amp_m1 = (int32_t)((int16_t)i2s2_rx_buffer[i]) * VOLUME_BOOST;
        if (amp_m1 > 32767) amp_m1 = 32767;
        else if (amp_m1 < -32768) amp_m1 = -32768;
        fft_in_m1[float_index] = (float32_t)amp_m1;

        int32_t amp_m3 = (int32_t)((int16_t)i2s3_rx_buffer[i]) * VOLUME_BOOST;
        if (amp_m3 > 32767) amp_m3 = 32767;
        else if (amp_m3 < -32768) amp_m3 = -32768;
        fft_in_m3[float_index] = (float32_t)amp_m3;

        int32_t amp_m2 = (int32_t)((int16_t)i2s2_rx_buffer[i + 2]) * VOLUME_BOOST;
        if (amp_m2 > 32767) amp_m2 = 32767;
        else if (amp_m2 < -32768) amp_m2 = -32768;
        fft_in_m2[float_index] = (float32_t)amp_m2;

        int32_t amp_m4 = (int32_t)((int16_t)i2s3_rx_buffer[i + 2]) * VOLUME_BOOST;
        if (amp_m4 > 32767) amp_m4 = 32767;
        else if (amp_m4 < -32768) amp_m4 = -32768;
        fft_in_m4[float_index] = (float32_t)amp_m4;

        float_index++;
        if (float_index >= FFT_SIZE) {
            float_index = 0;
            data_ready = 1;
            return;
        }
    }
}

void unwrap_and_center_phase(float *phases, float offset, float *out_phases)
{
    float sum = 0.0f;
    for (int i = 0; i < 4; i++) {
        float p = phases[i] + offset;
        p = fmodf(p, 2.0f * PI);
        if (p < 0.0f) p += 2.0f * PI;
        out_phases[i] = p;
        sum += p;
    }
    float mean = sum / 4.0f;
    for (int i = 0; i < 4; i++) {
        out_phases[i] -= mean;
    }
}

// ============================================================
// MAIN
// ============================================================
int main(void)
{
    /* Set the CPU clock before initializing SysTick, UART and peripherals. */
    SystemClock_100MHz_HSI();
    SysTick_Init();
    UART_Init(USART2, 921600);

    I2S_PLLI2S_Init();
    I2S_Init(SPI3, i2s3_rx_buffer);
    I2S_Init(SPI2, i2s2_rx_buffer);
    SPI1_Init_Master();

    arm_rfft_fast_init_f32(&fft_handler, FFT_SIZE);

    for (uint32_t i = 0; i < FFT_SIZE; i++) {
        hann_window[i] = 0.5f * (1.0f - cosf(2.0f * PI * i / (FFT_SIZE - 1)));
    }

    float mic_X[4] = {-1.0f,  1.0f, -1.0f,  1.0f};
    float mic_Y[4] = {-1.0f, -1.0f,  1.0f,  1.0f};
    float d_meter = 0.0275f;

    memset(accum_hist, 0, sizeof(accum_hist));
    memset(ai_tracks, 0, sizeof(ai_tracks));

    initTFT();
    fullDisplay(0x0000);
    drawCircle(RADAR_X, RADAR_Y, RADAR_R, 0x07E0);
    drawCircle(RADAR_X, RADAR_Y, 2, 0xFFFF);

    UART_SendString(USART2, "\r\n--- SYSTEM READY 100MHz ---\r\n");

    static int active_sources = 1;

    while (1) {
        if (SPI2->SR & (1 << 6)) {
            volatile uint32_t tmpreg = SPI2->DR;
            tmpreg = SPI2->SR;
            (void)tmpreg;
        }
        if (SPI3->SR & (1 << 6)) {
            volatile uint32_t tmpreg = SPI3->DR;
            tmpreg = SPI3->SR;
            (void)tmpreg;
        }

        if (i2s2_half && i2s3_half) {
            i2s2_half = 0;
            i2s3_half = 0;
            Extract_Audio(0, I2S_RX_BUFFER_SIZE / 2);
        }

        if (i2s2_full && i2s3_full) {
            i2s2_full = 0;
            i2s3_full = 0;
            Extract_Audio(I2S_RX_BUFFER_SIZE / 2, I2S_RX_BUFFER_SIZE);
        }

        if (data_ready) {
            data_ready = 0;

            float32_t mean1 = 0.0f, mean2 = 0.0f, mean3 = 0.0f, mean4 = 0.0f;

            for (uint32_t i = 0; i < FFT_SIZE; i++) {
                mean1 += fft_in_m1[i];
                mean2 += fft_in_m2[i];
                mean3 += fft_in_m3[i];
                mean4 += fft_in_m4[i];
            }
            mean1 /= FFT_SIZE;
            mean2 /= FFT_SIZE;
            mean3 /= FFT_SIZE;
            mean4 /= FFT_SIZE;

            float32_t energy = 0.0f;
            for (uint32_t i = 0; i < FFT_SIZE; i++) {
                float e1 = fabsf(fft_in_m1[i] - mean1);
                float e2 = fabsf(fft_in_m2[i] - mean2);
                float e3 = fabsf(fft_in_m3[i] - mean3);
                float e4 = fabsf(fft_in_m4[i] - mean4);
                energy += (e1 + e2 + e3 + e4) * 0.25f;

                win_in_m1[i] = (fft_in_m1[i] - mean1) * hann_window[i];
                win_in_m2[i] = (fft_in_m2[i] - mean2) * hann_window[i];
                win_in_m3[i] = (fft_in_m3[i] - mean3) * hann_window[i];
                win_in_m4[i] = (fft_in_m4[i] - mean4) * hann_window[i];
            }

            if (energy / FFT_SIZE < 50.0f) {
                for (int i = 0; i < 360; i++) {
                    accum_hist[i] *= 0.85f;
                }
#if AI_ENABLE
                AI_UpdateTrackers(0, NULL, NULL, NULL);
                AI_UpdateTFT();
#endif

#if SEND_DOA_TEST_UART
                UART_SendMeasurementFrame(USART2, 0, NULL);
#endif
#if SEND_DATASET_UART
                UART_SendFeatureFrame(USART2, 0, NULL, NULL, NULL);
#endif
#if SEND_EVAL_UART
                UART_SendEvalFrame(USART2, 0, NULL);
#endif
                continue;
            }

            arm_rfft_fast_f32(&fft_handler, win_in_m1, fft_out_m1, 0);
            arm_rfft_fast_f32(&fft_handler, win_in_m2, fft_out_m2, 0);
            arm_rfft_fast_f32(&fft_handler, win_in_m3, fft_out_m3, 0);
            arm_rfft_fast_f32(&fft_handler, win_in_m4, fft_out_m4, 0);

            memset(radar_histogram, 0, sizeof(radar_histogram));
            memset(bin_valid, 0, sizeof(bin_valid));

            int k_min = (int)(300.0f * FFT_SIZE / SAMPLE_RATE);
            int k_max = (int)(1500.0f * FFT_SIZE / SAMPLE_RATE);

            for (int k = k_min; k < k_max; k++) {
                float f_hz = k * (SAMPLE_RATE / FFT_SIZE);
                float k_factor = 2.0f * PI * f_hz * d_meter / 343.2f;
                float Sum3f = 4.0f * k_factor * k_factor;

                float raw_phases[4];
                raw_phases[0] = atan2f(fft_out_m1[2 * k + 1], fft_out_m1[2 * k]);
                raw_phases[1] = atan2f(fft_out_m2[2 * k + 1], fft_out_m2[2 * k]);
                raw_phases[2] = atan2f(fft_out_m3[2 * k + 1], fft_out_m3[2 * k]);
                raw_phases[3] = atan2f(fft_out_m4[2 * k + 1], fft_out_m4[2 * k]);

                float p1 = fft_out_m1[2 * k] * fft_out_m1[2 * k] + fft_out_m1[2 * k + 1] * fft_out_m1[2 * k + 1];
                float p2 = fft_out_m2[2 * k] * fft_out_m2[2 * k] + fft_out_m2[2 * k + 1] * fft_out_m2[2 * k + 1];
                float p3 = fft_out_m3[2 * k] * fft_out_m3[2 * k] + fft_out_m3[2 * k + 1] * fft_out_m3[2 * k + 1];
                float p4 = fft_out_m4[2 * k] * fft_out_m4[2 * k] + fft_out_m4[2 * k + 1] * fft_out_m4[2 * k + 1];

                float power_avg = (p1 + p2 + p3 + p4) * 0.25f;
                float magnitude = sqrtf(power_avg);

                float min_Variance = 1e9f;
                float best_Angle = 0.0f;
                float best_AbsPhamic = 0.0f;
                float offsets[4] = {0.0f, PI / 2.0f, PI, 1.5f * PI};

                for (int o = 0; o < 4; o++) {
                    float PhAF[4];
                    unwrap_and_center_phase(raw_phases, offsets[o], PhAF);

                    float Phasq = 0.0f, PhamicR = 0.0f, PhamicI = 0.0f;
                    for (int i = 0; i < 4; i++) {
                        Phasq += PhAF[i] * PhAF[i];
                        PhamicR += PhAF[i] * mic_X[i];
                        PhamicI += PhAF[i] * mic_Y[i];
                    }

                    float angle_rad = atan2f(PhamicI, PhamicR);
                    float angle_deg = angle_rad * (180.0f / PI);

                    while (angle_deg < 0.0f) angle_deg += 360.0f;
                    while (angle_deg >= 360.0f) angle_deg -= 360.0f;

                    float AbsPhamic = sqrtf(PhamicR * PhamicR + PhamicI * PhamicI);
                    float MeanPV = Phasq + Sum3f;
                    float MinPV = MeanPV - 2.0f * k_factor * AbsPhamic;

                    if (MinPV < min_Variance) {
                        min_Variance = MinPV;
                        best_Angle = angle_deg;
                        best_AbsPhamic = AbsPhamic;
                    }
                }

                if (min_Variance < 0.001f) min_Variance = 0.001f;

                float MeanPV_total = min_Variance + 2.0f * k_factor * best_AbsPhamic;
                float ScorePV = MeanPV_total / min_Variance;
                if (ScorePV > 12.0f) ScorePV = 12.0f;

                if (ScorePV > 6.0f) {
                    radar_histogram[(int)best_Angle % 360] += magnitude * ScorePV;
                }

                if (k < MAX_FFT_BINS) {
                    bin_angles[k] = (int)best_Angle;
                    bin_power[k]  = power_avg;
                    bin_valid[k]  = (ScorePV > 6.0f) ? 1 : 0;
                }
            }

            for (int i = 0; i < 360; i++) {
                accum_hist[i] = accum_hist[i] * 0.5f + radar_histogram[i] * 0.5f;
            }

            for (int i = 0; i < 360; i++) {
                smoothed_hist[i] = (
                    accum_hist[(i + 355) % 360] +
                    accum_hist[(i + 356) % 360] * 2.0f +
                    accum_hist[(i + 357) % 360] * 3.0f +
                    accum_hist[(i + 358) % 360] * 4.0f +
                    accum_hist[(i + 359) % 360] * 5.0f +
                    accum_hist[i]               * 6.0f +
                    accum_hist[(i + 1)   % 360] * 5.0f +
                    accum_hist[(i + 2)   % 360] * 4.0f +
                    accum_hist[(i + 3)   % 360] * 3.0f +
                    accum_hist[(i + 4)   % 360] * 2.0f +
                    accum_hist[(i + 5)   % 360]) / 36.0f;
            }

            float hist_mean = 0.0f;
            for (int i = 0; i < 360; i++) {
                hist_mean += smoothed_hist[i];
            }
            hist_mean /= 360.0f;

            float dynamic_thresh = hist_mean * 3.0f;
            if (dynamic_thresh < 100.0f) dynamic_thresh = 100.0f;

            typedef struct {
                int angle;
                float val;
            } Peak;

            Peak candidates[36];
            int cand_count = 0;

            for (int i = 0; i < 360; i++) {
                if (smoothed_hist[i] > dynamic_thresh) {
                    int is_peak = 1;
                    for (int d = -30; d <= 30; d++) {
                        if (d == 0) continue;
                        int idx = (i + d + 360) % 360;
                        if ((smoothed_hist[idx] >= smoothed_hist[i] && d > 0) ||
                            (smoothed_hist[idx] >  smoothed_hist[i] && d < 0)) {
                            is_peak = 0;
                            break;
                        }
                    }

                    if (is_peak && cand_count < 36) {
                        candidates[cand_count].angle = i;
                        candidates[cand_count].val = smoothed_hist[i];
                        cand_count++;
                    }
                }
            }

            for (int i = 0; i < cand_count - 1; i++) {
                for (int j = i + 1; j < cand_count; j++) {
                    if (candidates[j].val > candidates[i].val) {
                        Peak temp = candidates[i];
                        candidates[i] = candidates[j];
                        candidates[j] = temp;
                    }
                }
            }

            int peak_angles[MAX_SOURCES];
            int peak_count = 0;

            if (cand_count > 0) {
                peak_angles[peak_count++] = candidates[0].angle;
                float max1_val = candidates[0].val;

                float thresh_N2 = 0.15f;
                float thresh_N3 = 0.20f;
                int min_separation = 35;
                int idx_n2 = -1;

                for (int i = 1; i < cand_count; i++) {
                    if (candidates[i].val > max1_val * thresh_N2 &&
                        candidates[i].val > dynamic_thresh * 1.25f) {
                        if (get_angle_diff(candidates[i].angle, peak_angles[0]) >= min_separation) {
                            peak_angles[peak_count++] = candidates[i].angle;
                            idx_n2 = i;
                            break;
                        }
                    }
                }

                if (idx_n2 != -1) {
                    for (int i = idx_n2 + 1; i < cand_count; i++) {
                        if (candidates[i].val > max1_val * thresh_N3 &&
                            candidates[i].val > dynamic_thresh * 1.5f) {
                            if (get_angle_diff(candidates[i].angle, peak_angles[0]) >= min_separation &&
                                get_angle_diff(candidates[i].angle, peak_angles[1]) >= min_separation) {
                                peak_angles[peak_count++] = candidates[i].angle;
                                break;
                            }
                        }
                    }
                }
            }

            active_sources = (peak_count > 0) ? peak_count : 1;

            float peak_features[MAX_SOURCES][NUM_BANDS];
            memset(peak_features, 0, sizeof(peak_features));
            uint8_t peak_bin_count[MAX_SOURCES] = {0};

            for (int k = k_min; k < k_max; k++) {
                if (k >= MAX_FFT_BINS || !bin_valid[k]) continue;

                int closest_peak = -1;
                int min_diff = FEATURE_ANGLE_GATE + 1;

                for (int p = 0; p < peak_count; p++) {
                    int diff = get_angle_diff(bin_angles[k], peak_angles[p]);
                    if (diff <= FEATURE_ANGLE_GATE && diff < min_diff) {
                        min_diff = diff;
                        closest_peak = p;
                    }
                }

                if (closest_peak == -1) continue;

                int band_idx = (k - k_min) * NUM_BANDS / (k_max - k_min);
                if (band_idx >= NUM_BANDS) band_idx = NUM_BANDS - 1;
                if (band_idx < 0) band_idx = 0;

                peak_features[closest_peak][band_idx] += bin_power[k];

                if (peak_bin_count[closest_peak] < 255) {
                    peak_bin_count[closest_peak]++;
                }
            }

#if SEND_DATASET_UART
            if (peak_count > 0) {
                UART_SendFeatureFrame(USART2, (uint8_t)peak_count, peak_angles, peak_bin_count, peak_features);
            } else {
                UART_SendFeatureFrame(USART2, 0, NULL, NULL, NULL);
            }
#endif

#if AI_ENABLE
            AI_UpdateTrackers(peak_count, peak_angles, peak_bin_count, peak_features);
            AI_UpdateTFT();
#endif
#if SEND_DOA_TEST_UART
            UART_SendMeasurementFrame(USART2, peak_count, peak_angles);
#endif
#if SEND_EVAL_UART
            UART_SendEvalFrame(USART2, peak_count, peak_angles);
#endif
        }
    }
}
