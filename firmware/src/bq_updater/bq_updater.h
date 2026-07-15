#ifndef BQ_UPDATER_H
#define BQ_UPDATER_H

#include <stdint.h>
#include <stdbool.h>

typedef struct {
    volatile bool is_running;
    volatile uint32_t current_line;
    volatile uint32_t total_lines;
    volatile uint8_t active_channels; // Bitmask (bits 0~5 for CH1~CH6)
    volatile uint8_t error_channels;  // Bitmask of failed channels
    volatile int error_code;
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
