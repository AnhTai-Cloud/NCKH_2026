#ifndef __ADC_H
#define __ADC_H
#include "stm32f4xx.h"
void ADC1_CH0_Init(void);
uint16_t ADC1_CHO_Read(void);
void ADC1_CH1_DMA_Init(void);

#endif