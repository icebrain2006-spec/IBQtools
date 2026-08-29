#ifndef BQ_UPDATER_H
#define BQ_UPDATER_H

#include <stdint.h>
#include <stdbool.h>

typedef enum {
    UPDATER_STATE_IDLE = 0,
    UPDATER_STATE_RUNNING = 1,
    UPDATER_STATE_DELAYING = 2,
    UPDATER_STATE_ERROR = 3,
    UPDATER_STATE_DONE = 4
} updater_state_e;

typedef struct {
    volatile updater_state_e state;
    volatile uint32_t current_line;
    volatile uint32_t total_lines;
    volatile uint8_t active_channels; // Bitmask (bits 0~5 for CH1~CH6)
    volatile uint8_t error_channels;  // Bitmask of failed channels
    volatile int error_code;
    volatile uint32_t current_delay_ms; // Used if in delay state
} update_status_t;

extern volatile update_status_t update_status;

// Initialize updater and register Core 1 entry point
void bq_updater_init(void);

// Start flash stream update on specified channels (mask)
// This launches the update loop on Core 1 asynchronously
bool bq_updater_start(uint8_t channel_mask);

// Force stop update process
void bq_updater_stop(void);

#endif // BQ_UPDATER_H
