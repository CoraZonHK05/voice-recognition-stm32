#include "stm32f10x.h"
#include "usart.h"
#include "mfcc.h"
#include "OLED.h"
#include "AD.h"
#include "MyDMA.h"

MFCC_HandleTypeDef hmfcc;
int16_t mfcc_int[MFCC_COEFFS];
float32_t mfcc_float[MFCC_COEFFS];
uint16_t frame_count = 0;

static void delay_ms(uint32_t ms)
{
    volatile uint32_t i;
    while (ms--) for (i = 0; i < 8000; ++i) { }
}

static uint8_t copy_audio_block(int16_t *frame, uint8_t block, uint16_t expected_sequence)
{
    uint16_t i;
    uint16_t current_sequence;
    uint32_t pending_overwrite;
    uint16_t start = block ? MFCC_FRAME_LEN : 0;
    for (i = 0; i < MFCC_FRAME_LEN; ++i) {
        frame[i] = (int16_t)AD_Value[start + i];
    }
    /* A pending next-half event means DMA may have started overwriting the
       source during the copy. Drop that frame instead of processing a mix. */
    __disable_irq();
    current_sequence = AD_BlockSequence;
    pending_overwrite = block ? DMA_GetITStatus(DMA1_IT_HT1) : DMA_GetITStatus(DMA1_IT_TC1);
    __enable_irq();
    return (current_sequence == expected_sequence && pending_overwrite == RESET);
}

static void send_mfcc_frame(void)
{
    uint16_t i;
    USART3_Send_Data(0xAA);
    USART3_Send_Data(0x55);
    for (i = 0; i < MFCC_COEFFS; ++i) {
        USART3_Send_Data((uint8_t)((uint16_t)mfcc_int[i] >> 8));
        USART3_Send_Data((uint8_t)mfcc_int[i]);
    }
    USART3_Send_Data(0x0D);
    USART3_Send_Data(0x0A);
}

static void update_oled_display(void)
{
    uint16_t level = (uint16_t)(AD_Value[0] >> 4);
    OLED_ShowString(1, 1, "MFCC F:");
    OLED_ShowNum(1, 8, frame_count, 4);
    OLED_ShowString(2, 1, "C0:");
    OLED_ShowSignedNum(2, 4, mfcc_int[0], 5);
    OLED_ShowString(3, 1, "ADC:");
    OLED_ShowNum(3, 5, level, 3);
}

int main(void)
{
    int16_t audio_frame[MFCC_FRAME_LEN];
    uint16_t seen_sequence = 0;
    uint16_t sequence;
    uint8_t block;

    OLED_Init();
    uart3_init(9600);
    AD_Init();
    MyDMA_Init();
    MFCC_Init(&hmfcc);
    OLED_Clear();
    OLED_ShowString(1, 1, "MFCC Ready");
    delay_ms(300);
    OLED_Clear();

    while (1) {
        /* DMA completes 256 samples every 32 ms. Sending every second block
           leaves enough time for a 30-byte packet at 9600 baud. */
        __disable_irq();
        sequence = AD_BlockSequence;
        block = AD_CompletedBlock;
        __enable_irq();
        if (sequence == seen_sequence) continue;
        seen_sequence = sequence;
        if (sequence & 1U) continue;

        if (!copy_audio_block(audio_frame, block, sequence)) continue;
        MFCC_ComputeFrame(&hmfcc, audio_frame, mfcc_float);
        MFCC_Quantize(mfcc_float, mfcc_int, 3);
        send_mfcc_frame();
        ++frame_count;
        update_oled_display();
    }
}
