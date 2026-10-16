#ifndef __FONT_H
#define __FONT_H
#include <stdint.h>
typedef struct {
	
	const uint8_t width;
	const uint8_t height;
	const uint16_t *data;
	
}FontDef;


extern const FontDef Font_7x10 ;

#endif
