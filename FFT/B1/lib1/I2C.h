#ifndef __I2C_H
#define __I2C_H

#include "stm32f4xx.h"
#include "SYSTICK.h"
void I2C_Init(void);
void I2C_Start(void);
void I2C_Stop(void);
uint8_t I2C_Send_Addr(uint8_t addr,uint8_t rw);
uint8_t I2C_Send_Data(uint8_t data);
uint8_t I2C_Read_Data(uint8_t ack);
void ConfigI2C(void);

#endif