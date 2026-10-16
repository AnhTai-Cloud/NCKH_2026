#include "AI_Model.h"
#include "ai_model_data.h"
#include <math.h>

static float relu(float x)
{
    return (x > 0.0f) ? x : 0.0f;
}

static float sigmoid(float x)
{
    return 1.0f / (1.0f + expf(-x));
}

float AI_Predict(const float input[32])
{
    float x[32];

    float h1[32];
    float h2[16];
    float h3[8];

    float out;

    // =========================
    // PREPROCESS
    // log1p + StandardScaler
    // =========================

    for (int i = 0; i < 32; i++)
    {
        float v = log1pf(input[i]);

        x[i] = (v - ai_scaler_mean[i]) /
               ai_scaler_scale[i];
    }

    // =========================
    // DENSE 1
    // 32 -> 32
    // =========================

    for (int j = 0; j < 32; j++)
    {
        float sum = ai_b1[j];

        for (int i = 0; i < 32; i++)
        {
            sum += x[i] * ai_w1[i][j];
        }

        h1[j] = relu(sum);
    }

    // =========================
    // DENSE 2
    // 32 -> 16
    // =========================

    for (int j = 0; j < 16; j++)
    {
        float sum = ai_b2[j];

        for (int i = 0; i < 32; i++)
        {
            sum += h1[i] * ai_w2[i][j];
        }

        h2[j] = relu(sum);
    }

    // =========================
    // DENSE 3
    // 16 -> 8
    // =========================

    for (int j = 0; j < 8; j++)
    {
        float sum = ai_b3[j];

        for (int i = 0; i < 16; i++)
        {
            sum += h2[i] * ai_w3[i][j];
        }

        h3[j] = relu(sum);
    }

    // =========================
    // OUTPUT
    // 8 -> 1
    // =========================

    out = ai_b4[0];

    for (int i = 0; i < 8; i++)
    {
        out += h3[i] * ai_w4[i][0];
    }

    return sigmoid(out);
}