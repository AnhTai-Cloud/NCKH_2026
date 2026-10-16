#ifndef _TFT_H
#define _TFT_H
#include "SYSTICK.h"
#include "stm32f4xx.h" // Thêm thu vi?n lõi c?a STM32F4
#include "SPI.h"
#include "stdio.h"
#include "FONT.h"
#include <math.h>
#include <stdlib.h>

/* 
 * Ket noi chan cua man hinh TFT 
 * PB0  -> CS (Chip Select)
 * PB1  -> A0 
 * PB10 -> RESET
 * SCK->PA5
 * PIN_MISO ->PA6
 * PIN_MOSI  -> PA7
 * PIN_CS    ->  PB0

 */
#define LCD_CMD_END 0xFF

static const uint8_t u8InitCmdList[] = {
//  Command     Length      Data
    0xB1,       0x03,       0x01, 0x2C, 0x2D,                       // Frame Rate Control (In normal mode/ Full colors)
    0xB2,       0x03,       0x01, 0x2C, 0x2D,                       // Frame Rate Control (In Idle mode/ 8-colors)
    0xB3,       0x06,       0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D,     // Frame Rate Control (In Partial mode/ full colors)
    0xB4,       0x01,       0x07,                                   // Display Inversion Control
    0xC0,       0x03,       0xA2, 0x02, 0x84,                       // Power Control 1
    0xC1,       0x01,       0xC5,                                   // Power Control 2
    0xC2,       0x02,       0x0A, 0x00,                             // Power Control 3 (in Normal mode/ Full colors)
    0xC3,       0x02,       0x8A, 0x2A,                             // Power Control 4 (in Idle mode/ 8-colors)
    0xC4,       0x02,       0x8A, 0xEE,                             // Power Control 5 (in Partial mode/ full-colors)
    0xC5,       0x01,       0x0E,                                   // VCOM Control 1
    0xE0,       0x10,       0x02, 0x1C, 0x07, 0x12, 0x37, 0x32, 0x29, 0x2D, 0x29, 0x25, 0x2B, 0x39, 0x00, 0x01, 0x03, 0x10,     //Gamma adjustment(+ polarity)
    0xE1,       0x10,       0x03, 0x1D, 0x07, 0x06, 0x2E, 0x2C, 0x29, 0x2D, 0x2E, 0x2E, 0x37, 0x3F, 0x00, 0x00, 0x02, 0x10,     //Gamma adjustment(- polarity)
    LCD_CMD_END, LCD_CMD_END
};

void writeCMDTFT(uint8_t cmd);
void writeDataTFT(uint8_t data);
void sendCMDList(const uint8_t* cmdList);
void setPos(uint8_t x1, uint8_t y1, uint8_t x2, uint8_t y2);
void fullDisplay(uint16_t color);
void drawPixel(uint8_t x, uint8_t y, uint16_t color);
void initTFT(void);
void drawChar(uint8_t x, uint8_t y, char ch, FontDef font, uint16_t color, uint16_t bg);
void drawString(uint8_t x, uint8_t y, char *str, FontDef font, uint16_t color, uint16_t bg);
void drawNumber(uint8_t x, uint8_t y, int number, FontDef font, uint16_t color, uint16_t bg);
void drawLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint16_t color);
void drawCircle(int16_t x0, int16_t y0, int16_t r, uint16_t color);
#endif