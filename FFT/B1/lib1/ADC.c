#include "ADC.h"


volatile uint16_t adc_value = 0;

void ADC1_CH1_DMA_Init(void)
{
   
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC->AHB1ENR |= RCC_AHB1ENR_DMA2EN;
    RCC->APB2ENR |= RCC_APB2ENR_ADC1EN;

    /* 2. PA1 -> Analog mode */
    GPIOA->MODER &= ~(3U << (1 * 2));
    GPIOA->MODER |=  (3U << (1 * 2));
    GPIOA->PUPDR &= ~(3U << (1 * 2));

   /**/
    ADC1->CR1 = 0;
    ADC1->CR2 = 0;

    /* 4. ADC common prescaler: PCLK2 / 4 */
    ADC->CCR &= ~(3U << 16);
    ADC->CCR |=  (1U << 16);

    /* 5. Ðo phân giai 12-bit */
    ADC1->CR1 &= ~(3U << 24);

    /* 6. Right alignment */
    ADC1->CR2 &= ~(1U << 11);

    /* 7. Continuous conversion */
    ADC1->CR2 |= ADC_CR2_CONT;

   /* chuyen 1 kenh thoi*/
    ADC1->SQR1 &= ~(0xFU << 20);

    /* 9. Ch?n channel 1 ? v? trí SQ1 */
    ADC1->SQR3 &= ~0x1FU;
    ADC1->SQR3 |= 1U;

    /* 10. Sample time cho channel 1 */
    ADC1->SMPR2 &= ~(7U << 3);      // channel 1 dùng bit [5:3]
    ADC1->SMPR2 |=  (4U << 3);      // 84 cycles

    /* 11. B?t DMA cho ADC */
    ADC1->CR2 |= ADC_CR2_DMA;

    /* 12. Cho phép DMA request liên tuc sau moi lan ADC convert */
    ADC1->CR2 |= ADC_CR2_DDS;

    /* ================= DMA2 Stream0 Channel0 cho ADC1 ================= */

    /* Tat stream truoc khi cau hình */
    DMA2_Stream0->CR &= ~DMA_SxCR_EN;
    while (DMA2_Stream0->CR & DMA_SxCR_EN) {}

   /*
	xoa tat ca co ngat cu cua Stream0
		*/
    DMA2->LIFCR |= (DMA_LIFCR_CFEIF0 |
                    DMA_LIFCR_CDMEIF0 |
                    DMA_LIFCR_CTEIF0 |
                    DMA_LIFCR_CHTIF0 |
                    DMA_LIFCR_CTCIF0);

   /* chon channel 0 cho DMA2_Stream0*/
    DMA2_Stream0->CR &= ~(7U << 25);

    /* 14. Peripheral address = ADC1->DR */
    DMA2_Stream0->PAR = (uint32_t)&ADC1->DR;

    /* 15. Memory address = bi?n adc_value */
    DMA2_Stream0->M0AR = (uint32_t)&adc_value;

    /* 16. Number of data = 1 */
    DMA2_Stream0->NDTR = 1;

    /* 17. C?u hình DMA:
       - peripheral to memory
       - peripheral size = half-word
       - memory size = half-word
       - memory increment = disable
       - peripheral increment = disable
       - circular mode = enable
    */
    DMA2_Stream0->CR &= ~(3U << 6);     // DIR = 00: peripheral-to-memory
    DMA2_Stream0->CR &= ~(1U << 9);     // PINC = 0
    DMA2_Stream0->CR &= ~(1U << 10);    // MINC = 0
    DMA2_Stream0->CR |=  (1U << 8);     // CIRC = 1

    DMA2_Stream0->CR &= ~(3U << 11);    // PSIZE clear
    DMA2_Stream0->CR |=  (1U << 11);    // PSIZE = 01: 16-bit

    DMA2_Stream0->CR &= ~(3U << 13);    // MSIZE clear
    DMA2_Stream0->CR |=  (1U << 13);    // MSIZE = 01: 16-bit

    /* 18. Enable DMA stream */
    DMA2_Stream0->CR |= DMA_SxCR_EN;

    /* 19. Enable ADC */
    ADC1->CR2 |= ADC_CR2_ADON;

    /* 20. Start ADC */
    ADC1->CR2 |= ADC_CR2_SWSTART;
}
void ADC1_CH0_Init(void){
RCC->AHB1ENR |=(1<<0);
	RCC->APB2ENR |=(1<<8);
	GPIOA->MODER |=(0X3<<0);
	GPIOA->PUPDR &=~(0X3<<0);
	/* 3. ADC common config
       Prescaler chia clock ADC: PCLK2 / 4
       
    */
	ADC->CCR &=~(0X3<<16);
	ADC->CCR |=(0X1<<16);
	
	ADC1->CR1 = 0;// reset ve 0 truoc cho an toan 
    ADC1->CR2 = 0;// ADON Strat ADC

   
    ADC1->CR1 &= ~(3U << 24);  // RES = 00 => 12-bit tren f1 khong co mac dinh 12 bit

    /* 6. Right alignment (can chinh phai ) de 12 bit gia tri ADC 
	doc duoc nam dung ben phai cua thanh ghi DR de cho chan chan */
    ADC1->CR2 &= ~(1U << 11); 

    /* 7. Single conversion */
    ADC1->CR2 &= ~(1U << 1);   // CONT = 0

  
    ADC1->SQR1 &= ~(0xFU << 20); // 0000: 1 conversion

    /* 9. Channel d?u tiên trong sequence là channel 0 */
    ADC1->SQR3 &= ~0x1FU;
    ADC1->SQR3 |= 0U;

    /* 10. Sampling time cho channel 0
       d?t l?n m?t chút cho ?n d?nh
       84 cycles
    */
    ADC1->SMPR2 &= ~(7U << 0);
    ADC1->SMPR2 |=  (4U << 0);

    /* 11. Enable ADC */
    ADC1->CR2 |= (1<<0);
}

uint16_t ADC1_CHO_Read(void)
{
 
    ADC1->CR2 |= (1<<30);

 
    while (!(ADC1->SR & ADC_SR_EOC))
    {
    }

    
    return (uint16_t)ADC1->DR;
}
