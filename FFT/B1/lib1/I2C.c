#include "I2C.h"

void ConfigI2C(void){
    RCC->AHB1ENR |= (1 << 1);    // GPIOB
    RCC->APB1ENR |= (1 << 21);   // I2C1

    /* PB6, PB7 -> AF */
    GPIOB->MODER &= ~((0x3 << 12) | (0x3 << 14));
    GPIOB->MODER |=  ((0x2 << 12) | (0x2 << 14));

    /* Open-drain */
    GPIOB->OTYPER |= (1 << 6) | (1 << 7);

    /* Pull-up */
    GPIOB->PUPDR &= ~((0x3 << 12) | (0x3 << 14));
    GPIOB->PUPDR |=  ((0x1 << 12) | (0x1 << 14));

    /* AF4 */
    GPIOB->AFR[0] &= ~((0xF << 24) | (0xF << 28));
    GPIOB->AFR[0] |=  ((0x4 << 24) | (0x4 << 28));
}

void I2C_Init(void){
	ConfigI2C();
    I2C1->CR1 |=  (1 << 15);   // SWRST
    I2C1->CR1 &= ~(1 << 15);

    I2C1->CR1 &= ~(1 << 0);    // PE = 0

    I2C1->CR2 = 16;            // PCLK1 = 16 MHz
    I2C1->CCR = 80;            // 100 kHz standard mode
    I2C1->TRISE = 17;          // Fpclk1 + 1

    I2C1->CR1 |= (1 << 10);    // ACK
    I2C1->CR1 |= (1 << 0);     // PE
}

void I2C_Start(void){
    I2C1->CR1 |= (1 << 8);
    while (!(I2C1->SR1 & (1 << 0))) {}
}

void I2C_Stop(void){
    I2C1->CR1 |= (1 << 9);
}

uint8_t I2C_Send_Addr(uint8_t addr, uint8_t rw){
    I2C1->DR = (addr << 1) | (rw & 0x01);

    while (!(I2C1->SR1 & ((1 << 1) | (1 << 10)))) {}

    if (I2C1->SR1 & (1 << 10)) {
        I2C1->SR1 &= ~(1 << 10);
        I2C_Stop();
        return 1;
    }

    (void)I2C1->SR1;
    (void)I2C1->SR2;
    return 0;
}

uint8_t I2C_Send_Data(uint8_t data){
    I2C1->DR = data;

    while (!(I2C1->SR1 & ((1 << 7) | (1 << 10)))) {}

    if (I2C1->SR1 & (1 << 10)) {
        I2C1->SR1 &= ~(1 << 10);
        I2C_Stop();
        return 1;
    }

    return 0;
}

uint8_t I2C_Read_Data(uint8_t ack){
    if (ack){
        I2C1->CR1 |= (1 << 10);
    } else {
        I2C1->CR1 &= ~(1 << 10);
        I2C1->CR1 |=  (1 << 9);
    }

    while (!(I2C1->SR1 & (1 << 6))) {}
    return (uint8_t)I2C1->DR;
}