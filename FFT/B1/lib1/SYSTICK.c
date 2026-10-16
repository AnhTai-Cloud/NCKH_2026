#include "SYSTICK.h"

volatile uint32_t systick_ms = 0;



void SysTick_Init(void)
{
    uint32_t ticks_per_ms = SystemCoreClock / 1000U;
    if (ticks_per_ms == 0U) ticks_per_ms = 1U;

    SysTick->LOAD = ticks_per_ms - 1U;
    SysTick->VAL  = 0;

    SysTick->CTRL = (1<<2) |     // Clock = AHB
                    (1<<1) |     // Enable interrupt
                    (1<<0);      // Enable SysTick
}



void SysTick_Handler(void)
{
    systick_ms++;
}



uint32_t millis(void)
{
    return systick_ms;
}



void Delay_ms(uint32_t ms)
{
    uint32_t start = millis();

    while(millis() - start < ms);
}
