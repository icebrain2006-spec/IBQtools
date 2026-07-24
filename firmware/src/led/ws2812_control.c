#include "ws2812_control.h"
#include "ws2812.pio.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"

static PIO pio = pio0;
static uint sm = 0;

static uint32_t current_color = COLOR_WHITE;
static led_mode_t current_mode = LED_MODE_SOLID;

// Blinking state
static uint32_t blink_duration_ms = 0;
static uint32_t blink_start_time = 0;
static uint32_t last_toggle_time = 0;
static bool is_led_on = true;

static inline void put_pixel(uint32_t pixel_grb) {
    pio_sm_put_blocking(pio, sm, pixel_grb << 8u);
}

static inline uint32_t urgb_u32(uint8_t r, uint8_t g, uint8_t b) {
    return
            ((uint32_t) (r) << 8) |
            ((uint32_t) (g) << 16) |
            (uint32_t) (b);
}

static void update_hardware(bool on) {
    if (on) {
        // Convert 0x00RRGGBB to 0x00GGRRBB
        uint8_t r = (current_color >> 16) & 0xFF;
        uint8_t g = (current_color >> 8) & 0xFF;
        uint8_t b = current_color & 0xFF;
        
        // Dim the color slightly so it doesn't blind the user (max 255 -> 64)
        r = r / 4;
        g = g / 4;
        b = b / 4;
        put_pixel(urgb_u32(r, g, b));
    } else {
        put_pixel(0); // Off
    }
}

void led_init(void) {
    // Try to claim a free state machine on PIO0 or PIO1
    bool success = false;
    uint offset = 0;
    
    if (pio_can_add_program(pio0, &ws2812_program)) {
        pio = pio0;
        offset = pio_add_program(pio, &ws2812_program);
        int free_sm = pio_claim_unused_sm(pio, false);
        if (free_sm >= 0) {
            sm = (uint)free_sm;
            success = true;
        }
    }
    
    if (!success && pio_can_add_program(pio1, &ws2812_program)) {
        pio = pio1;
        offset = pio_add_program(pio, &ws2812_program);
        int free_sm = pio_claim_unused_sm(pio, false);
        if (free_sm >= 0) {
            sm = (uint)free_sm;
            success = true;
        }
    }

    if (success) {
        ws2812_program_init(pio, sm, offset, WS2812_PIN, 800000, false);
        update_hardware(true);
    }
}

void led_set_state(uint32_t color, led_mode_t mode, uint32_t duration_ms) {
    current_color = color;
    current_mode = mode;
    blink_duration_ms = duration_ms;
    
    uint32_t now = to_ms_since_boot(get_absolute_time());
    
    if (mode == LED_MODE_BLINK) {
        blink_start_time = now;
        last_toggle_time = now;
        is_led_on = false; // start with off to make blink noticeable
        update_hardware(is_led_on);
    } else {
        is_led_on = true;
        update_hardware(is_led_on);
    }
}

void led_task(void) {
    if (current_mode != LED_MODE_BLINK) {
        return; // Nothing to do if solid
    }
    
    uint32_t now = to_ms_since_boot(get_absolute_time());
    
    // Check if blink duration expired
    if (blink_duration_ms > 0 && (now - blink_start_time >= blink_duration_ms)) {
        // Revert to solid mode
        current_mode = LED_MODE_SOLID;
        is_led_on = true;
        update_hardware(is_led_on);
        return;
    }
    
    // Toggle every 250ms
    if (now - last_toggle_time >= 250) {
        last_toggle_time = now;
        is_led_on = !is_led_on;
        update_hardware(is_led_on);
    }
}
