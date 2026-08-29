#include "relay.h"
#include "pico/stdlib.h"

static const uint8_t RELAY_PINS[RELAY_NUM_CHANNELS] = {6, 7, 8, 9, 10, 11};
static uint8_t current_relay_mask = 0;

void relay_init(void) {
    for (int i = 0; i < RELAY_NUM_CHANNELS; i++) {
        uint pin = RELAY_PINS[i];
        gpio_init(pin);
        gpio_set_dir(pin, GPIO_OUT);
        gpio_put(pin, false); // Turn off by default
    }
    current_relay_mask = 0;
}

void relay_set_state(uint8_t ch, bool state) {
    if (ch < 1 || ch > RELAY_NUM_CHANNELS) return;
    uint pin = RELAY_PINS[ch - 1];
    gpio_put(pin, state);
    
    if (state) {
        current_relay_mask |= (1 << (ch - 1));
    } else {
        current_relay_mask &= ~(1 << (ch - 1));
    }
}

void relay_set_mask(uint8_t mask) {
    for (int i = 0; i < RELAY_NUM_CHANNELS; i++) {
        uint pin = RELAY_PINS[i];
        bool state = (mask & (1 << i)) != 0;
        gpio_put(pin, state);
    }
    current_relay_mask = mask & 0x3F; // Only 6 bits
}

uint8_t relay_get_mask(void) {
    return current_relay_mask;
}
