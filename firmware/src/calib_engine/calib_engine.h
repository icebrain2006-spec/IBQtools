#ifndef CALIB_ENGINE_H
#define CALIB_ENGINE_H

#include <stdint.h>
#include <stdbool.h>

#define CMD_CALIB_RUN    0x60
#define CMD_CALIB_STATUS 0x61

typedef struct {
    uint16_t cell1_gain;
    uint16_t pack_gain;
    uint16_t bat_gain;
    bool success;
} ch_calib_result_t;

typedef struct {
    uint8_t state;           // 0: IDLE, 1: RUNNING, 2: DONE, 3: ERROR
    uint8_t active_channels;
    uint8_t error_channels;
    uint8_t mode;              // 0: VOLTAGE, 1: CURRENT, 2: TEMP
    ch_calib_result_t results[7]; // Index 1..6
} calib_status_t;

extern volatile calib_status_t calib_status;

void calib_engine_init(void);
bool calib_engine_start(uint8_t channel_mask, uint8_t mode, uint16_t target_cell1_mv, uint16_t target_pack_mv, uint16_t target_bat_mv);

#endif // CALIB_ENGINE_H
