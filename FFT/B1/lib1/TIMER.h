#ifndef __TIMER_H
#define __TIMER_H
#include "stm32f4xx.h"
void TIMER2_Init(void);
void delay_ms(uint32_t ms);
void PWM_Init(void);
void set_angle_servo(uint16_t pwm);
void GPIO_Pwm(void);
#endif