#include "UART.h"

void UART_Init(USART_TypeDef *USARTx, uint32_t baudrate) {
    uint32_t pclk; 

    // ---------------------------------------------------------
    // A. PHÂN LU?NG PH?N C?NG (CLOCK, GPIO, ALTERNATE FUNCTION)
    // ---------------------------------------------------------
    if (USARTx == USART1) {
        RCC->AHB1ENR |= (1 << 0);
        RCC->APB2ENR |= (1 << 4);

        GPIOA->MODER &= ~((0x3 << 18) | (0x3 << 20));
        GPIOA->MODER |=  ((0x2 << 18) | (0x2 << 20));
        GPIOA->OSPEEDR |= ((0x3 << 18) | (0x3 << 20));

        GPIOA->AFR[1] &= ~((0xF << 4) | (0xF << 8));
        GPIOA->AFR[1] |=  ((0x7 << 4) | (0x7 << 8));
        pclk = SystemCoreClock; // APB2 = 100 MHz

    } else if (USARTx == USART2) {
        RCC->AHB1ENR |= (1 << 0);
        RCC->APB1ENR |= (1 << 17);

        GPIOA->MODER &= ~((0x3 << 4) | (0x3 << 6));
        GPIOA->MODER |=  ((0x2 << 4) | (0x2 << 6));
        GPIOA->OSPEEDR |= ((0x3 << 4) | (0x3 << 6));

        GPIOA->AFR[0] &= ~((0xF << 8) | (0xF << 12));
        GPIOA->AFR[0] |=  ((0x7 << 8) | (0x7 << 12));
        pclk = SystemCoreClock / 2U; // APB1 = 50 MHz

    } else if (USARTx == USART6) {
        RCC->AHB1ENR |= (1 << 2); 
        RCC->APB2ENR |= (1 << 5); 

        GPIOC->MODER &= ~((0x3 << 12) | (0x3 << 14));
        GPIOC->MODER |=  ((0x2 << 12) | (0x2 << 14));
        GPIOC->OSPEEDR |= ((0x3 << 12) | (0x3 << 14));

        GPIOC->AFR[0] &= ~((0xF << 24) | (0xF << 28));
        GPIOC->AFR[0] |=  ((0x8 << 24) | (0x8 << 28));
        pclk = SystemCoreClock; // APB2 = 100 MHz

    } else {
        return; 
    }

    // ---------------------------------------------------------
    // B. C?U HÌNH CÁC THANH GHI LÕI USART (DÙNG CHUNG)
    // ---------------------------------------------------------
    USARTx->CR1 = 0;          
    USARTx->CR1 |= (1 << 3);  
    USARTx->CR1 |= (1 << 2);  

    USARTx->BRR = (pclk + (baudrate / 2)) / baudrate;

    USARTx->CR1 |= (1 << 13); 
}

// ==============================================================================
// CÁC HÀM X? LÝ TRUY?N NH?N D? LI?U T?NG QUÁT
// ==============================================================================

void UART_Send(USART_TypeDef *USARTx, uint8_t data) {
    while (!(USARTx->SR & (1 << 7))) {}
    USARTx->DR = data;
}

void UART_SendString(USART_TypeDef *USARTx, char *str) {
    while (*str) {
        UART_Send(USARTx, (uint8_t)(*str++));
    }
}

uint8_t UART_Available(USART_TypeDef *USARTx) {
    if (USARTx->SR & (1 << 5)) {
        return 1;
    }
    return 0;
}

uint8_t UART_Read(USART_TypeDef *USARTx) {
    return (uint8_t)(USARTx->DR & 0xFF);
}