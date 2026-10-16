#include "TIMER.h"

void PWM_Init(void){
    RCC->APB1ENR |= (1 << 1);   // enable clock TIM3

    TIM3->PSC = 15;             // 16MHz / 16 = 1MHz => 1us/tick
    TIM3->ARR = 20000 - 1;      // 20ms period
    TIM3->CNT = 0;
    TIM3->CCR2 = 1500;          // 1.5ms, v? trí gi?a servo

    TIM3->EGR = (1 << 0);       // update event

    /* CH2 output compare mode */
    TIM3->CCMR1 &= ~(0x7 << 12);  // clear OC2M
    TIM3->CCMR1 |=  (0x6 << 12);  // PWM mode 1 for CH2
    TIM3->CCMR1 |=  (1 << 11);    // OC2PE preload enable

    TIM3->CCER |= (1 << 4);       // CC2E enable output channel 2
    TIM3->CR1  |= (1 << 7);       // ARPE
    TIM3->CR1  |= (1 << 0);       // CEN
}

void set_angle_servo(uint16_t pwm){
    if (pwm > 180) pwm = 180;
    TIM3->CCR2 = (1000 * pwm) / 180 + 1000;
}

void GPIO_Pwm(void)
{
    RCC->AHB1ENR |= (1 << 0);   // enable GPIOA clock

    /* PA7 = Alternate Function mode */
    GPIOA->MODER &= ~(0x3 << 14);
    GPIOA->MODER |=  (0x2 << 14);

    /* Output type = Push-pull */
    GPIOA->OTYPER &= ~(1 << 7);


    GPIOA->PUPDR &= ~(0x3 << 14);

    /* AF2 for TIM3_CH2 on PA7 */
    GPIOA->AFR[0] &= ~(0xF << 28);
    GPIOA->AFR[0] |=  (0x2 << 28);
}

void TIMER2_Init(void){
    RCC->APB1ENR |= (1 << 0);

    TIM2->PSC = 16000 - 1;
    TIM2->ARR = 0xFFFFFFFF;
    TIM2->CNT = 0;
    TIM2->EGR = (1 << 0);
    TIM2->CR1 |= (1 << 0);
}

//void delay_ms(uint32_t ms){
//    TIM2->CNT = 0;
//    while(TIM2->CNT < ms){}
//}