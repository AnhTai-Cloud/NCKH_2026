#include "I2S.h"


uint16_t i2s1_rx_buffer[I2S_RX_BUFFER_SIZE]; 
uint16_t i2s2_rx_buffer[I2S_RX_BUFFER_SIZE]; 
uint16_t i2s3_rx_buffer[I2S_RX_BUFFER_SIZE]; 
uint16_t i2s4_rx_buffer[I2S_RX_BUFFER_SIZE]; 

volatile uint8_t i2s1_half = 0, i2s1_full = 0;
volatile uint8_t i2s2_half = 0, i2s2_full = 0;
volatile uint8_t i2s3_half = 0, i2s3_full = 0;
volatile uint8_t i2s4_half = 0, i2s4_full = 0;

void I2S_PLLI2S_Init(void) {// I2S su dung 1 nguon clock rieng biet voi cpu 
    RCC->CR &= ~(1 << 26);
    while((RCC->CR & (1 << 27))); 

    RCC->PLLI2SCFGR &= ~((0x1FF << 6) | (0x7 << 28)); 
    RCC->PLLI2SCFGR |= (213 << 6) | (2 << 28);   //PLLI2SN =213 PLLI2SR=2      
    
    RCC->CR |= (1 << 26);
    while(!(RCC->CR & (1 << 27))); 
}

void I2S_Init(SPI_TypeDef *SPIx, uint16_t *rx_buffer) {
    DMA_Stream_TypeDef *DMA_Stream;
    IRQn_Type irqn;
    uint32_t dma_channel = 0;// luu kenh DMA tuong ung voi I2S
 
    if (SPIx == SPI1) { 
        RCC->AHB1ENR |= (1 << 0) | (1 << 22); 
        RCC->APB2ENR |= (1 << 12);            

      
        GPIOA->MODER &= ~((0x3 << 8) | (0x3 << 10) | (0x3 << 14));
        GPIOA->MODER |=  ((0x2 << 8) | (0x2 << 10) | (0x2 << 14));
        GPIOA->OSPEEDR |= ((0x3 << 8) | (0x3 << 10) | (0x3 << 14));
        GPIOA->AFR[0] &= ~((0xF << 16) | (0xF << 20) | (0xF << 28));
        GPIOA->AFR[0] |=  ((0x5 << 16) | (0x5 << 20) | (0x5 << 28));

        DMA_Stream = DMA2_Stream2;
        dma_channel = 3; // Kênh 3 cho SPI1_RX
        irqn = DMA2_Stream2_IRQn;

    } else if (SPIx == SPI2) { 
        RCC->AHB1ENR |= (1 << 1) | (1 << 21); 
        RCC->APB1ENR |= (1 << 14);           

      
        GPIOB->MODER &= ~((0x3 << 24) | (0x3 << 26) | (0x3 << 30));
        GPIOB->MODER |=  ((0x2 << 24) | (0x2 << 26) | (0x2 << 30));
        GPIOB->OSPEEDR |= ((0x3 << 24) | (0x3 << 26) | (0x3 << 30));
        GPIOB->AFR[1] &= ~((0xF << 16) | (0xF << 20) | (0xF << 28));
        GPIOB->AFR[1] |=  ((0x5 << 16) | (0x5 << 20) | (0x5 << 28)); 

        DMA_Stream = DMA1_Stream3;
        dma_channel = 0; // Kênh 0 cho SPI2_RX
        irqn = DMA1_Stream3_IRQn;

   } else if (SPIx == SPI3) { // ========== I2S3 ==========
        RCC->AHB1ENR |= (1 << 0) | (1 << 1) | (1 << 21); 
        RCC->APB1ENR |= (1 << 15);                      
    
        
        // 1. Chân PA15 (WS)
        GPIOA->MODER &= ~(0x3 << 30);     
        GPIOA->MODER |=  (0x2 << 30);
        GPIOA->OSPEEDR |= (0x3 << 30);    
        GPIOA->AFR[1] &= ~(0xF << 28);    // Dùng AFR[1] vì PA15 > PA7
        GPIOA->AFR[1] |=  (0x6 << 28);    // Ch?n ch?c nang AF6 (SPI3)
        
        // 2. Chân PB3 (CK) và PB5 (SD)
        GPIOB->MODER &= ~((0x3 << 6) | (0x3 << 10)); 
        GPIOB->MODER |=  ((0x2 << 6) | (0x2 << 10));
        GPIOB->OSPEEDR |= ((0x3 << 6) | (0x3 << 10));
GPIOB->AFR[0] &= ~((0xF << 12) | (0xF << 20)); 
        GPIOB->AFR[0] |=  ((0x6 << 12) | (0x6 << 20)); 

        DMA_Stream = DMA1_Stream0;
        dma_channel = 0; // Kênh 0 cho SPI3_RX
        irqn = DMA1_Stream0_IRQn;

    } else if (SPIx == SPI4) { 
        RCC->AHB1ENR |= (1 << 4) | (1 << 22); 
        RCC->APB2ENR |= (1 << 13);           

     
        GPIOE->MODER &= ~((0x3 << 4) | (0x3 << 8) | (0x3 << 12));
        GPIOE->MODER |=  ((0x2 << 4) | (0x2 << 8) | (0x2 << 12));
        GPIOE->OSPEEDR |= ((0x3 << 4) | (0x3 << 8) | (0x3 << 12));
        GPIOE->AFR[0] &= ~((0xF << 8) | (0xF << 16) | (0xF << 24));
        GPIOE->AFR[0] |=  ((0x5 << 8) | (0x5 << 16) | (0x5 << 24));

        DMA_Stream = DMA2_Stream3;
        dma_channel = 5; // Kênh 5 cho SPI4_RX
        irqn = DMA2_Stream3_IRQn; 

    } else {
        return; 
    }


    SPIx->I2SCFGR = 0;
    
    // --- B?T Ð?U ÐO?N S?A Ð?I Ð?NG B? MASTER - SLAVE ---
    if (SPIx == SPI3) {
        // C?u hình SPI3 làm Slave Receive (0x1 << 8)
        SPIx->I2SCFGR |= (1 << 11) | (0x1 << 8) | (0x0 << 4) | (0x1 << 1) | (1 << 0);
    } else {
        // C?u hình các SPI khác (bao g?m SPI2) làm Master Receive (0x3 << 8)
        SPIx->I2SCFGR |= (1 << 11) | (0x3 << 8) | (0x0 << 4) | (0x1 << 1) | (1 << 0);
    }
    // --- K?T THÚC ÐO?N S?A Ð?I ---
    
	/*
	
	
	+chuyen SPI Sang che do I2S
	+ che do Master_Receive (hoac Slave_Receive tuy thuoc SPIx)
	+ Chuan I2S Philips
	+ do dai du lieu la 24 bit 
	+ moi kenh chiem 32 bit tren khung truyen 
	*/
    SPIx->I2SPR = 49;// do dang dung 64 bit  1 frame se co 32 bit trai 32 bit phai (khac trong RM411)
    SPIx->CR2 |= (1 << 0); 


    DMA_Stream->CR &= ~(1 << 0);
    while(DMA_Stream->CR & (1 << 0)); 
    DMA_Stream->CR = 0; 

   
    DMA_Stream->CR |= (dma_channel << 25) | (0x2 << 16) | (0x1 << 13) | (0x1 << 11) | (1 << 10) | (1 << 8);
    
    DMA_Stream->PAR = (uint32_t)&(SPIx->DR);     
    DMA_Stream->M0AR = (uint32_t)rx_buffer;       
    DMA_Stream->NDTR = I2S_RX_BUFFER_SIZE;

    DMA_Stream->CR |= (1 << 3) | (1 << 4); 
    NVIC_EnableIRQ(irqn);

    DMA_Stream->CR |= (1 << 0);
    SPIx->I2SCFGR |= (1 << 10); 
}


//void INMP441_4Mic_Init(void) {
//    I2S_PLLI2S_Init();
//    
//   
//    // I2S_Init(SPI1, i2s1_rx_buffer);
//    I2S_Init(SPI2, i2s2_rx_buffer);
//    I2S_Init(SPI3, i2s3_rx_buffer);
//    // I2S_Init(SPI4, i2s4_rx_buffer); 
//}



void DMA2_Stream2_IRQHandler(void) {//Tuong ung I2S1 
    if (DMA2->LISR & (1 << 20)) { DMA2->LIFCR = (1 << 20); i2s1_half = 1; }
    if (DMA2->LISR & (1 << 21)) { DMA2->LIFCR = (1 << 21); i2s1_full = 1; }
    DMA2->LIFCR = (1 << 19) | (1 << 18) | (1 << 16);
}


void DMA1_Stream3_IRQHandler(void) {//tuong ung voi I2S2
    if (DMA1->LISR & (1 << 26)) { DMA1->LIFCR = (1 << 26); i2s2_half = 1; }
    if (DMA1->LISR & (1 << 27)) { DMA1->LIFCR = (1 << 27); i2s2_full = 1; }
    DMA1->LIFCR = (1 << 25) | (1 << 24) | (1 << 22);
}


void DMA1_Stream0_IRQHandler(void) {// tuong ung voi I2S3 
    if (DMA1->LISR & (1 << 4)) { DMA1->LIFCR = (1 << 4); i2s3_half = 1; }
    if (DMA1->LISR & (1 << 5)) { DMA1->LIFCR = (1 << 5); i2s3_full = 1; }
    DMA1->LIFCR = (1 << 3) | (1 << 2) | (1 << 0);
}


void DMA2_Stream3_IRQHandler(void) {// tuong ung voi I2S4
    if (DMA2->LISR & (1 << 26)) { DMA2->LIFCR = (1 << 26); i2s4_half = 1; }
    if (DMA2->LISR & (1 << 27)) { DMA2->LIFCR = (1 << 27); i2s4_full = 1; }
    DMA2->LIFCR = (1 << 25) | (1 << 24) | (1 << 22);
}

//#include "I2S.h"

//uint16_t i2s1_rx_buffer[I2S_RX_BUFFER_SIZE]; 
//uint16_t i2s2_rx_buffer[I2S_RX_BUFFER_SIZE]; 
//uint16_t i2s3_rx_buffer[I2S_RX_BUFFER_SIZE]; 
//uint16_t i2s4_rx_buffer[I2S_RX_BUFFER_SIZE]; 

//volatile uint8_t i2s1_half = 0, i2s1_full = 0;
//volatile uint8_t i2s2_half = 0, i2s2_full = 0;
//volatile uint8_t i2s3_half = 0, i2s3_full = 0;
//volatile uint8_t i2s4_half = 0, i2s4_full = 0;

//void I2S_PLLI2S_Init(void) {
//    RCC->CR &= ~(1 << 26);
//    while((RCC->CR & (1 << 27))); 

//    RCC->PLLI2SCFGR &= ~((0x1FF << 6) | (0x7 << 28)); 
//    RCC->PLLI2SCFGR |= (213 << 6) | (2 << 28);        
//    
//    RCC->CR |= (1 << 26);
//    while(!(RCC->CR & (1 << 27))); 
//}

//void I2S_Init(SPI_TypeDef *SPIx, uint16_t *rx_buffer) {
//    DMA_Stream_TypeDef *DMA_Stream;
//    IRQn_Type irqn;
//    uint32_t dma_channel = 0;
// 
//    if (SPIx == SPI1) { // ========== I2S1 ==========
//        RCC->AHB1ENR |= (1 << 0) | (1 << 22); 
//        RCC->APB2ENR |= (1 << 12);            

//        GPIOA->MODER &= ~((0x3 << 8) | (0x3 << 10) | (0x3 << 14));
//        GPIOA->MODER |=  ((0x2 << 8) | (0x2 << 10) | (0x2 << 14));
//        GPIOA->OSPEEDR |= ((0x3 << 8) | (0x3 << 10) | (0x3 << 14));
//        GPIOA->AFR[0] &= ~((0xF << 16) | (0xF << 20) | (0xF << 28));
//        GPIOA->AFR[0] |=  ((0x5 << 16) | (0x5 << 20) | (0x5 << 28));

//        DMA_Stream = DMA2_Stream2;
//        dma_channel = 3; 
//        irqn = DMA2_Stream2_IRQn;

//    } else if (SPIx == SPI2) { // ========== I2S2 ==========
//        RCC->AHB1ENR |= (1 << 1) | (1 << 21); // B?t Clock PORT B và DMA1
//        RCC->APB1ENR |= (1 << 14);            // B?t Clock SPI2 (APB1)

//        // I2S2 Pins: PB12(WS), PB13(CK), PB15(SD) -> Chu?n AF5
//        GPIOB->MODER &= ~((0x3 << 24) | (0x3 << 26) | (0x3 << 30));
//        GPIOB->MODER |=  ((0x2 << 24) | (0x2 << 26) | (0x2 << 30));
//        GPIOB->OSPEEDR |= ((0x3 << 24) | (0x3 << 26) | (0x3 << 30));
//        GPIOB->AFR[1] &= ~((0xF << 16) | (0xF << 20) | (0xF << 28));
//        GPIOB->AFR[1] |=  ((0x5 << 16) | (0x5 << 20) | (0x5 << 28)); 

//        DMA_Stream = DMA1_Stream3;
//        dma_channel = 0; 
//        irqn = DMA1_Stream3_IRQn;

//    } else if (SPIx == SPI3) { // ========== I2S3 ==========
//        RCC->AHB1ENR |= (1 << 0) | (1 << 1) | (1 << 21); // B?t PORT A, B và DMA1
//        RCC->APB1ENR |= (1 << 15);                       // B?t Clock SPI3 (APB1)

//        // C?U HÌNH G?C THEO Ý B?N: PA4(WS), PB3(CK), PB5(SD) -> Chu?n AF6
//        // 1. Chân PA4 (WS)
//        GPIOA->MODER &= ~(0x3 << 8);     
//        GPIOA->MODER |=  (0x2 << 8);
//        GPIOA->OSPEEDR |= (0x3 << 8);    
//        GPIOA->AFR[0] &= ~(0xF << 16); 
//        GPIOA->AFR[0] |=  (0x6 << 16); 
//        
//        // 2. Chân PB3 (CK) và PB5 (SD)
//        GPIOB->MODER &= ~((0x3 << 6) | (0x3 << 10)); 
//        GPIOB->MODER |=  ((0x2 << 6) | (0x2 << 10));
//        GPIOB->OSPEEDR |= ((0x3 << 6) | (0x3 << 10));
//        GPIOB->AFR[0] &= ~((0xF << 12) | (0xF << 20)); 
//        GPIOB->AFR[0] |=  ((0x6 << 12) | (0x6 << 20)); 

//        DMA_Stream = DMA1_Stream0;
//        dma_channel = 0; 
//        irqn = DMA1_Stream0_IRQn;

//    } else if (SPIx == SPI4) { // ========== I2S4 ==========
//        RCC->AHB1ENR |= (1 << 4) | (1 << 22); 
//        RCC->APB2ENR |= (1 << 13);            
//     
//        GPIOE->MODER &= ~((0x3 << 4) | (0x3 << 8) | (0x3 << 12));
//        GPIOE->MODER |=  ((0x2 << 4) | (0x2 << 8) | (0x2 << 12));
//        GPIOE->OSPEEDR |= ((0x3 << 4) | (0x3 << 8) | (0x3 << 12));
//        GPIOE->AFR[0] &= ~((0xF << 8) | (0xF << 16) | (0xF << 24));
//        GPIOE->AFR[0] |=  ((0x5 << 8) | (0x5 << 16) | (0x5 << 24));

//        DMA_Stream = DMA2_Stream3;
//        dma_channel = 5; 
//        irqn = DMA2_Stream3_IRQn; 

//    } else {
//        return; 
//    }

//    SPIx->I2SCFGR = 0;
//    SPIx->I2SCFGR |= (1 << 11) | (0x3 << 8) | (0x0 << 4) | (0x1 << 1) | (1 << 0);
//    SPIx->I2SPR = 52;
//    SPIx->CR2 |= (1 << 0); 

//    DMA_Stream->CR &= ~(1 << 0);
//    while(DMA_Stream->CR & (1 << 0)); 
//    DMA_Stream->CR = 0; 
//   
//    DMA_Stream->CR |= (dma_channel << 25) | (0x2 << 16) | (0x1 << 13) | (0x1 << 11) | (1 << 10) | (1 << 8);
//    
//    DMA_Stream->PAR = (uint32_t)&(SPIx->DR);     
//    DMA_Stream->M0AR = (uint32_t)rx_buffer;        
//    DMA_Stream->NDTR = I2S_RX_BUFFER_SIZE;

//    DMA_Stream->CR |= (1 << 3) | (1 << 4); 
//    NVIC_EnableIRQ(irqn);

//    DMA_Stream->CR |= (1 << 0);
//    SPIx->I2SCFGR |= (1 << 10); 
//}

//void DMA2_Stream2_IRQHandler(void) { 
//    if (DMA2->LISR & (1 << 20)) { DMA2->LIFCR = (1 << 20); i2s1_half = 1; }
//    if (DMA2->LISR & (1 << 21)) { DMA2->LIFCR = (1 << 21); i2s1_full = 1; }
//    DMA2->LIFCR = (1 << 19) | (1 << 18) | (1 << 16);
//}

//void DMA1_Stream3_IRQHandler(void) {
//    if (DMA1->LISR & (1 << 26)) { DMA1->LIFCR = (1 << 26); i2s2_half = 1; }
//    if (DMA1->LISR & (1 << 27)) { DMA1->LIFCR = (1 << 27); i2s2_full = 1; }
//    DMA1->LIFCR = (1 << 25) | (1 << 24) | (1 << 22);
//}

//void DMA1_Stream0_IRQHandler(void) { 
//    if (DMA1->LISR & (1 << 4)) { DMA1->LIFCR = (1 << 4); i2s3_half = 1; }
//    if (DMA1->LISR & (1 << 5)) { DMA1->LIFCR = (1 << 5); i2s3_full = 1; }
//    DMA1->LIFCR = (1 << 3) | (1 << 2) | (1 << 0);
//}

//void DMA2_Stream3_IRQHandler(void) { 
//    if (DMA2->LISR & (1 << 26)) { DMA2->LIFCR = (1 << 26); i2s4_half = 1; }
//    if (DMA2->LISR & (1 << 27)) { DMA2->LIFCR = (1 << 27); i2s4_full = 1; }
//    DMA2->LIFCR = (1 << 25) | (1 << 24) | (1 << 22);
//}