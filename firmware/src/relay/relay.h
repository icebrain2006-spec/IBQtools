#ifndef RELAY_H
#define RELAY_H

#include <stdint.h>
#include <stdbool.h>

#define RELAY_NUM_CHANNELS 6

// Initialize relay control GPIO pins
void relay_init(void);

// Set individual relay state (ch: 1~6, state: true=ON/High, false=OFF/Low)
void relay_set_state(uint8_t ch, bool state);

// Set all relays at once using a bitmask (bits 0~5 represent channels 1~6)
void relay_set_mask(uint8_t mask);

// Get current relay state as a mask
uint8_t relay_get_mask(void);

#endif // RELAY_H
