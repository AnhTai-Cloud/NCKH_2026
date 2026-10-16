#include "TFT.h"



void writeCMDTFT(uint8_t cmd){
    GPIOB->ODR &= ~(1<<0); // CS = 0
    GPIOB->ODR &= ~(1<<1); // A0 = 0 (G?i Command)
    SPI1_Send(cmd);
    GPIOB->ODR |= (1<<0);  // CS = 1
}

void writeDataTFT(uint8_t data){
    GPIOB->ODR &= ~(1<<0); // CS = 0
    GPIOB->ODR |= (1<<1);  // A0 = 1 (G?i Data)
    SPI1_Send(data);
    GPIOB->ODR |= (1<<0);  // CS = 1
}

void sendCMDList(const uint8_t* cmdList){
    uint8_t index = 0;
    uint8_t cmd = 0;
    uint8_t num = 0;
    while(1){
        cmd = *cmdList++;
        num = *cmdList++;
        if(cmd == LCD_CMD_END){
            break;
        } else {
            writeCMDTFT(cmd);
            for(index = 0; index < num; index++){
                writeDataTFT(*cmdList++);
            }
        }
    }
}

void setPos(uint8_t x1, uint8_t y1, uint8_t x2, uint8_t y2){
    writeCMDTFT(0x2A);
    writeDataTFT(0x00);
    writeDataTFT(x1);
    writeDataTFT(0x00);
    writeDataTFT(x2);
    
    writeCMDTFT(0x2B);
    writeDataTFT(0x00);
    writeDataTFT(y1);
    writeDataTFT(0x00);
    writeDataTFT(y2);
}

// RGB 16bit 565
// RGB 16bit 565 - T?i uu hóa d?y liên t?c
void fullDisplay(uint16_t color){
    setPos(0, 0, 127, 159); // Set toàn màn hình 128x160
    writeCMDTFT(0x2C);
    
    uint8_t high_byte = color >> 8;
    uint8_t low_byte = color & 0xFF;
    
    GPIOB->ODR &= ~(1<<0); // CS = 0 (Kéo xu?ng 1 l?n duy nh?t)
    GPIOB->ODR |= (1<<1);  // A0 = 1 (Data mode)
    
    int i;
    for(i = 0; i < 128 * 160; i++){
        SPI1_Send(high_byte);
        SPI1_Send(low_byte);
    }
    
    GPIOB->ODR |= (1<<0);  // CS = 1 (Xong h?t m?i kéo lên)
}

void drawPixel(uint8_t x, uint8_t y, uint16_t color){
    if(x >= 128 || y >= 160){
        return;
    }
    setPos(x, y, x+1, y+1);
    writeCMDTFT(0x2C);
    writeDataTFT(color >> 8);
    writeDataTFT(color & 0xFF);
}

void initTFT(void){
  
    RCC->AHB1ENR |= (1 << 1); 


    GPIOB->MODER &= ~((3 << (0 * 2)) | (3 << (1 * 2)) | (3 << (10 * 2))); // Xóa c?u hình cu
    GPIOB->MODER |=  ((1 << (0 * 2)) | (1 << (1 * 2)) | (1 << (10 * 2))); // Set Output
    

    GPIOB->OSPEEDR |= ((3 << (0 * 2)) | (3 << (1 * 2)) | (3 << (10 * 2)));

    // Quá trình Reset c?ng màn hình
    GPIOB->ODR &= ~(1<<10); // Ðua chân RST xu?ng 0
    Delay_ms(20);
    GPIOB->ODR |= (1<<10);  // Kéo chân RST lên 1
    Delay_ms(150);
    
   
    writeCMDTFT(0x01);
    Delay_ms(150);
    
    
    writeCMDTFT(0x11);
    Delay_ms(255);
    
    
    sendCMDList(u8InitCmdList);
    
    writeCMDTFT(0x36); // Memory Data Access Control 
    writeDataTFT(0x08);
    
    writeCMDTFT(0x3A); // Interface Pixel Format (16-bit color)
    writeDataTFT(0x05);
    
    writeCMDTFT(0x20); // Display inversion off 
    
    setPos(0, 0, 128, 160);
    
    // B?T HI?N TH?
    writeCMDTFT(0x29);
    Delay_ms(100);
}

void drawChar(uint8_t x, uint8_t y, char ch, FontDef font, uint16_t color, uint16_t bg){
    uint32_t i, j;
    uint16_t pixelData;
    
    // 1. M? khung c?a s? 1 l?n duy nh?t cho toàn b? ký t? (Ti?t ki?m 80% l?nh SPI)
    setPos(x, y, x + font.width - 1, y + font.height - 1);
    writeCMDTFT(0x2C); // L?nh b?t d?u ghi b? nh? màn hình
    
    // 2. Kéo chân CS xu?ng 0 và gi? c? d?nh d? d?y m?t lèo d? li?u t?c d? cao
    GPIOB->ODR &= ~(1<<0); // CS = 0
    GPIOB->ODR |= (1<<1);  // A0 = 1 (Ch? d? g?i Data)
    
    for(i = 0; i < font.height; i++){
        pixelData = font.data[(ch - 32) * font.height + i];
        for(j = 0; j < font.width; j++){
            uint16_t c = ((pixelData << j) & 0x8000) ? color : bg;
            SPI1_Send(c >> 8);   // G?i byte cao
            SPI1_Send(c & 0xFF); // G?i byte th?p
        }
    }
    
    // 3. Ð?y xong toàn b? ch? cái m?i kéo chân CS lên 1
    GPIOB->ODR |= (1<<0);  // CS = 1
}

void drawString(uint8_t x, uint8_t y, char *str, FontDef font, uint16_t color, uint16_t bg){
    while(*str){
        drawChar(x, y, *str, font, color, bg);
        x += font.width;
        str++;
    }
}

void drawNumber(uint8_t x, uint8_t y, int number, FontDef font, uint16_t color, uint16_t bg){
    char buf[16];              
    sprintf(buf, "%d", number);
    drawString(x, y, buf, font, color, bg);
}

void drawLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint16_t color) {
    int16_t dx = abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
    int16_t dy = -abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
    int16_t err = dx + dy, e2;
    
    while (1) {
        drawPixel(x0, y0, color);
        if (x0 == x1 && y0 == y1) break;
        e2 = 2 * err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}


void drawCircle(int16_t x0, int16_t y0, int16_t r, uint16_t color) {
    int16_t f = 1 - r;
    int16_t ddF_x = 1;
    int16_t ddF_y = -2 * r;
    int16_t x = 0;
    int16_t y = r;

    drawPixel(x0, y0 + r, color);
    drawPixel(x0, y0 - r, color);
    drawPixel(x0 + r, y0, color);
    drawPixel(x0 - r, y0, color);

    while (x < y) {
        if (f >= 0) { y--; ddF_y += 2; f += ddF_y; }
        x++; ddF_x += 2; f += ddF_x;
        
        drawPixel(x0 + x, y0 + y, color);
        drawPixel(x0 - x, y0 + y, color);
        drawPixel(x0 + x, y0 - y, color);
        drawPixel(x0 - x, y0 - y, color);
        drawPixel(x0 + y, y0 + x, color);
        drawPixel(x0 - y, y0 + x, color);
        drawPixel(x0 + y, y0 - x, color);
        drawPixel(x0 - y, y0 - x, color);
    }
}