#ifndef __LCD_H
#define __LCD_H
#include "stm32f4xx.h"
#include "I2C.h"
#include "SYSTICK.h"
#include "stdio.h"

#define ADD 0X27
void LCD_Write_I2C(uint8_t data);
void LCD_Write_Data(uint8_t data);
void LCD_Write_CMD(uint8_t data);
void LCD_Set_Pos(uint8_t x,uint8_t y);
void LCD_Init(void);
void LCD_Clear(void);
void LCD_Send_String(char *str);
void LCD_Print_Number(uint16_t num);
void Update_LCD_Status(char* status) ;
#endif
