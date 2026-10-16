#include "LCD.h"
#define LCD_BACKLIGHT 0x08 // Bit 3 di?u khi?n dèn n?n

void LCD_Write_I2C(uint8_t data){
    I2C_Start();
    I2C_Send_Addr(ADD, 0);
   
    I2C_Send_Data(data | LCD_BACKLIGHT); 
    I2C_Stop();
}

void LCD_Write_Data(uint8_t data){
    uint8_t high = data & 0xF0;
    uint8_t low = (data << 4) & 0xF0;
    
 
    LCD_Write_I2C(high | 0x05); // EN=1, RS=1 (0x04 | 0x01)
    Delay_ms(1);                
    LCD_Write_I2C(high | 0x01); // EN=0, RS=1
    
 
    LCD_Write_I2C(low | 0x05);  // EN=1, RS=1
    Delay_ms(1);
    LCD_Write_I2C(low | 0x01);  // EN=0, RS=1
}

void LCD_Write_CMD(uint8_t cmd){
    uint8_t high = cmd & 0xF0;
    uint8_t low = (cmd << 4) & 0xF0;

    LCD_Write_I2C(high | 0x04); // EN=1, RS=0
    Delay_ms(1);
    LCD_Write_I2C(high | 0x00); // EN=0, RS=0
    
   
    LCD_Write_I2C(low | 0x04);  // EN=1, RS=0
    Delay_ms(1);
    LCD_Write_I2C(low | 0x00);  // EN=0, RS=0
}
void LCD_Clear(void) {
    LCD_Write_CMD(0x01);
    Delay_ms(2);           
}
void LCD_Init(void) {
   
    Delay_ms(50);
    LCD_Write_CMD(0x33); 
    LCD_Write_CMD(0x32); 
    LCD_Write_CMD(0x28); 
    LCD_Write_CMD(0x0C); // Display ON, Cursor OFF
    LCD_Write_CMD(0x06); // Entry mode
    LCD_Clear();
}
/*
Y la hang 
X la cot
*/
void LCD_Set_Pos(uint8_t x,uint8_t y){
uint8_t addr;
	switch(y){
		case 0:
			addr=0x80+x;
		break;
		case 1:
			addr=0xC0+x;
		break;
		case 2:
		addr =0x94+x;
		break;
		case 3:
			addr=0xD4+x;
		break;
		default:
			addr=0x80;
		
	}
	LCD_Write_CMD(addr);
}
void LCD_Send_String(char *str) {
    while (*str) {
        LCD_Write_Data(*str++);
    }
}
void LCD_Print_Number(uint16_t num){
char str[10];
	int i=0;
	if(num==0){
	LCD_Write_Data('0');
		return;
	}
	while(num>0){
	str[i++]=(num%10)+'0';
		num/=10;
	}
	while(i--){
	LCD_Write_Data(str[i]);
	}
	
}
void Update_LCD_Status(char* status) {
    char buf[21];
    
    sprintf(buf, "STAT: %-14s", status); 
    LCD_Set_Pos(0, 2); 
    LCD_Send_String(buf);
}
