#ifndef WS2812_CONTROL_H
#define WS2812_CONTROL_H

#include <stdint.h>
#include <stdbool.h>

#define WS2812_PIN 16

// Colors in 0x00RRGGBB format
#define COLOR_WHITE   0x00333333  // Dim white
#define COLOR_CYAN    0x0000FFFF
#define COLOR_MAGENTA 0x00FF00FF
#define COLOR_YELLOW  0x00FFFF00
#define COLOR_GREEN   0x0000FF00
#define COLOR_RED     0x00FF0000
#define COLOR_BLUE    0x000000FF
#define COLOR_OFF     0x00000000

typedef enum {
    LED_MODE_SOLID = 0,
    LED_MODE_BLINK = 1,
} led_mode_t;

// Initialize WS2812 on GPIO16 using PIO
void led_init(void);

// Set the LED state. If mode is BLINK, it will automatically revert to SOLID after duration_ms
void led_set_state(uint32_t color, led_mode_t mode, uint32_t duration_ms);

// Call this from the main while(true) loop to process blinking asynchronously
void led_task(void);

#endif // WS2812_CONTROL_H
