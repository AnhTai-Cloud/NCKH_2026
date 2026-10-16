#ifndef __UART_H
#define __UART_H

#include "stm32f4xx.h"

void UART_Init(USART_TypeDef *USARTx, uint32_t baudrate);


void UART_Send(USART_TypeDef *USARTx, uint8_t data);
void UART_SendString(USART_TypeDef *USARTx, char *str);


uint8_t UART_Available(USART_TypeDef *USARTx);
uint8_t UART_Read(USART_TypeDef *USARTx);

#endif