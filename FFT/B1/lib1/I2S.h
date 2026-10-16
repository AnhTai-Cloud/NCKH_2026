#ifndef __I2S_H
#define __I2S_H
/*
* Ket noi chan INMP441
* if(I2S1){ 
PA4-> WS
PA5-> SCK
PA7->SD
}
if(I2S2){
PB12->WS
PB13->SCK
PB15->SD
}
if(I2S3){
PA4->WS
PB3->SCK
PB5->SD
}
*/
#include "stm32f4xx.h"
#define I2S_RX_BUFFER_SIZE 4096 // kich thuoc cua mang buffer chua du lieu khi am thanh I2S do ve 
void I2S_PLLI2S_Init(void);// Ham tao xung nhip cho I2S
/*
Brief I2S_Init() :
parameter 1 : bo I2S muon dung 
parameter 2 : mang chua du lieu ma lieu khi khi doc mic se do ve 
*/
void I2S_Init(SPI_TypeDef *SPIx, uint16_t *rx_buffer);
//void INMP441_4Mic_Init(void);
void DMA2_Stream2_IRQHandler(void);
void DMA1_Stream3_IRQHandler(void);

void DMA1_Stream0_IRQHandler(void);
void DMA2_Stream3_IRQHandler(void);
#endif 