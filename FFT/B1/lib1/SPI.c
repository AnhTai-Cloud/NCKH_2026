#include "SPI.h"

void SPI1_Init_Master(void){

    RCC->AHB1ENR |= (1<<0) | (1<<1); 
    RCC->APB2ENR |= (1<<12);         
    

    PORT_SCK->MODER  &= ~(0x3 << (2*PIN_SCK));
    PORT_MISO->MODER &= ~(0x3 << (2*PIN_MISO));
    PORT_MOSI->MODER &= ~(0x3 << (2*PIN_MOSI));
    PORT_CS->MODER   &= ~(0x3 << (2*PIN_CS));


    PORT_SCK->MODER  |= (0x2 << (2*PIN_SCK));   
    PORT_MISO->MODER |= (0x2 << (2*PIN_MISO));  
    PORT_MOSI->MODER |= (0x2 << (2*PIN_MOSI));  
    PORT_CS->MODER   |= (0x1 << (2*PIN_CS));    


    PORT_SCK->OSPEEDR  |= (0x3 << (2*PIN_SCK));
    PORT_MOSI->OSPEEDR |= (0x3 << (2*PIN_MOSI));

 
    PORT_SCK->AFR[0] &= ~((0xF << (4*PIN_SCK)) | (0xF << (4*PIN_MISO)) | (0xF << (4*PIN_MOSI)));
    PORT_SCK->AFR[0] |=  ((0x5 << (4*PIN_SCK)) | (0x5 << (4*PIN_MISO)) | (0x5 << (4*PIN_MOSI)));


    SPI1->CR1 = 0;              
    SPI1->CR1 |= (1 << 2);      // Master
    SPI1->CR1 |= (0x01 << 3);   // Baudrate max
    SPI1->CR1 |= (1 << 9);      // SSM = 1
    SPI1->CR1 |= (1 << 8);      // SSI = 1
    SPI1->CR1 |= (1 << 6);      // bat SPI
    
    // keo cs len cao 
    PORT_CS->ODR |= (1<<PIN_CS); 
}

void SPI1_Send(uint8_t data){
    while(!(SPI1->SR & (1 << 1))){}  
    SPI1->DR = data;                
    
    while(!(SPI1->SR & (1 << 0))){}  
    (void)SPI1->DR;                 

    while(SPI1->SR & (1 << 7)){}     
}