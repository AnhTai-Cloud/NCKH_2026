#ifndef __SPI_H
#define __SPI_H
#include "stm32f4xx.h"

#define PORT_SCK       GPIOA
#define PORT_MISO      GPIOA
#define PORT_MOSI      GPIOA
#define PORT_CS        GPIOB

#define PIN_SCK     5
#define PIN_MISO    6
#define PIN_MOSI    7
#define PIN_CS      0

void SPI1_Init_Master(void);
void SPI1_Send(uint8_t data);

#endif