#ifndef __AD_H
#define __AD_H

#include "stm32f10x.h"

#define AD_BUFFER_SIZE 512
extern volatile uint16_t AD_Value[AD_BUFFER_SIZE];
extern volatile uint16_t AD_BlockSequence;
extern volatile uint8_t AD_CompletedBlock;

void AD_Init(void);

#endif
