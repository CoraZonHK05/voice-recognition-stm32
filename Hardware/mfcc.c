#include "mfcc.h"
#include <math.h>
#include <string.h>

static float32_t hamming_window[MFCC_FRAME_LEN];
static float32_t mel_filters[MFCC_NUM_FILTERS * (MFCC_FFT_SIZE / 2 + 1)];
static arm_cfft_radix2_instance_f32 fft_instance;

static void create_hamming_window(float32_t *window, uint16_t len)
{
    uint16_t i;
    for (i = 0; i < len; ++i) {
        window[i] = 0.54f - 0.46f * cosf((2.0f * PI * i) / (len - 1));
    }
}

static void create_mel_filterbank(float32_t *filters, uint16_t fft_size,
                                  uint16_t num_filters, uint32_t sample_rate)
{
    uint16_t i, j;
    const uint16_t bins = fft_size / 2 + 1;
    uint16_t bin_points[MFCC_NUM_FILTERS + 2];
    const float32_t mel_high = 2595.0f * log10f(1.0f + (sample_rate / 2.0f) / 700.0f);

    for (i = 0; i < num_filters + 2; ++i) {
        float32_t mel = mel_high * i / (num_filters + 1);
        float32_t frequency = 700.0f * (powf(10.0f, mel / 2595.0f) - 1.0f);
        uint32_t bin = (uint32_t)(frequency * fft_size / sample_rate);
        bin_points[i] = (uint16_t)((bin < bins) ? bin : bins - 1);
    }

    for (i = 0; i < num_filters; ++i) {
        float32_t *filter = &filters[i * bins];
        memset(filter, 0, bins * sizeof(float32_t));
        for (j = bin_points[i]; j <= bin_points[i + 1]; ++j) {
            if (bin_points[i + 1] > bin_points[i]) {
                filter[j] = (float32_t)(j - bin_points[i]) /
                            (bin_points[i + 1] - bin_points[i]);
            }
        }
        for (j = bin_points[i + 1]; j <= bin_points[i + 2]; ++j) {
            if (bin_points[i + 2] > bin_points[i + 1]) {
                filter[j] = 1.0f - (float32_t)(j - bin_points[i + 1]) /
                            (bin_points[i + 2] - bin_points[i + 1]);
            }
        }
    }
}

void MFCC_Init(MFCC_HandleTypeDef *hmfcc)
{
    static float32_t fft_buffer[MFCC_FFT_SIZE * 2];
    static float32_t mfcc_out[MFCC_COEFFS];

    create_hamming_window(hamming_window, MFCC_FRAME_LEN);
    create_mel_filterbank(mel_filters, MFCC_FFT_SIZE, MFCC_NUM_FILTERS, MFCC_SAMPLE_RATE);
    arm_cfft_radix2_init_f32(&fft_instance, MFCC_FFT_SIZE, 0, 1);
    hmfcc->hamming_window = hamming_window;
    hmfcc->mel_filters = mel_filters;
    hmfcc->fft_buffer = fft_buffer;
    hmfcc->mfcc_out = mfcc_out;
    hmfcc->frame_count = 0;
}

void MFCC_ComputeFrame(MFCC_HandleTypeDef *hmfcc, int16_t *pcm_frame,
                       float32_t *mfcc_out)
{
    uint16_t i, j;
    int32_t sum = 0;
    float32_t mean;
    float32_t power_spec[MFCC_FFT_SIZE / 2 + 1];
    float32_t mel_energy[MFCC_NUM_FILTERS];
    const uint16_t bins = MFCC_FFT_SIZE / 2 + 1;

    /* Remove microphone DC bias before applying the analysis window. */
    for (i = 0; i < MFCC_FRAME_LEN; ++i) sum += pcm_frame[i];
    mean = (float32_t)sum / MFCC_FRAME_LEN;
    for (i = 0; i < MFCC_FFT_SIZE; ++i) {
        float32_t sample = (i < MFCC_FRAME_LEN) ?
            ((float32_t)pcm_frame[i] - mean) * hmfcc->hamming_window[i] : 0.0f;
        hmfcc->fft_buffer[2 * i] = sample;
        hmfcc->fft_buffer[2 * i + 1] = 0.0f;
    }

    /* CMSIS radix-2 complex FFT; input is interleaved real/imaginary data. */
    arm_cfft_radix2_f32(&fft_instance, hmfcc->fft_buffer);
    for (i = 0; i < bins; ++i) {
        float32_t real = hmfcc->fft_buffer[2 * i];
        float32_t imag = hmfcc->fft_buffer[2 * i + 1];
        power_spec[i] = real * real + imag * imag;
    }

    for (i = 0; i < MFCC_NUM_FILTERS; ++i) {
        const float32_t *filter = &hmfcc->mel_filters[i * bins];
        float32_t energy = 0.0f;
        for (j = 0; j < bins; ++j) energy += power_spec[j] * filter[j];
        mel_energy[i] = logf(energy + 1e-10f);
    }

    for (i = 0; i < MFCC_COEFFS; ++i) {
        float32_t coefficient = 0.0f;
        for (j = 0; j < MFCC_NUM_FILTERS; ++j) {
            coefficient += mel_energy[j] *
                cosf(i * (j + 0.5f) * PI / MFCC_NUM_FILTERS);
        }
        mfcc_out[i] = coefficient * sqrtf((i == 0 ? 1.0f : 2.0f) / MFCC_NUM_FILTERS);
    }
    hmfcc->frame_count++;
}

void MFCC_Quantize(float32_t *mfcc_float, int16_t *mfcc_int, uint8_t shift)
{
    uint8_t i;
    float32_t scale;
    if (shift > 14) shift = 14;
    scale = (float32_t)(1UL << shift);
    for (i = 0; i < MFCC_COEFFS; ++i) {
        float32_t value = mfcc_float[i] * scale;
        if (value > 32767.0f) value = 32767.0f;
        if (value < -32768.0f) value = -32768.0f;
        mfcc_int[i] = (int16_t)((value >= 0.0f) ? value + 0.5f : value - 0.5f);
    }
}
