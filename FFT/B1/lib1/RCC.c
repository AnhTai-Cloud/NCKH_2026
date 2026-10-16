#include "stm32f4xx.h"

void SystemClock_100MHz_HSI(void)
{
    /* 1. B?t Dao d?ng n?i HSI (16MHz) thay vì dùng th?ch anh ngoài */
    RCC->CR |= RCC_CR_HSION;
    while (!(RCC->CR & RCC_CR_HSIRDY)); // S? vu?t qua trong chua t?i 1 micro-giây

    /* 2. B?t ngu?n PWR */
    RCC->APB1ENR |= RCC_APB1ENR_PWREN;
    PWR->CR |= PWR_CR_VOS; // VOS scale

    /* 3. C?u hình Flash d? theo k?p 100MHz */
    FLASH->ACR = FLASH_ACR_PRFTEN | FLASH_ACR_ICEN | FLASH_ACR_DCEN | FLASH_ACR_LATENCY_3WS;

    /* 4. Chia Prescaler cho các Bus */
    RCC->CFGR &= ~(RCC_CFGR_HPRE | RCC_CFGR_PPRE1 | RCC_CFGR_PPRE2);
    RCC->CFGR |= RCC_CFGR_HPRE_DIV1;     // AHB = 100 MHz
    RCC->CFGR |= RCC_CFGR_PPRE1_DIV2;    // APB1 = 50 MHz
    RCC->CFGR |= RCC_CFGR_PPRE2_DIV1;    // APB2 = 100 MHz

    /* 5. C?u hình PLL v?i HSI (16MHz) */
    // PLLM = 16 (chia 16 -> 1MHz)
    // PLLN = 200 (nhân 200 -> 200MHz)
    // PLLP = 2 (chia 2 -> 100MHz)
    RCC->PLLCFGR = (16U  << RCC_PLLCFGR_PLLM_Pos)
                 | (200U << RCC_PLLCFGR_PLLN_Pos)
                 | (0U   << RCC_PLLCFGR_PLLP_Pos)
                 | RCC_PLLCFGR_PLLSRC_HSI      // <--- CH? Ð?NH DÙNG NGU?N N?I B?
                 | (4U   << RCC_PLLCFGR_PLLQ_Pos);

    /* 6. Kh?i d?ng vòng khóa pha PLL */
    RCC->CR |= RCC_CR_PLLON;
    while (!(RCC->CR & RCC_CR_PLLRDY));

    /* 7. Chuy?n Switch System Clock sang PLL */
    RCC->CFGR &= ~RCC_CFGR_SW;
    RCC->CFGR |= RCC_CFGR_SW_PLL;
    while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_PLL);

    /* 8. C?p nh?t bi?n lõi CMSIS */
    SystemCoreClockUpdate();
}