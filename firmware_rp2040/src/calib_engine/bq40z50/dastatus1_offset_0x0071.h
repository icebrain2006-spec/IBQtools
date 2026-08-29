#ifndef DASTATUS1_OFFSET_0X0071_H
#define DASTATUS1_OFFSET_0X0071_H

#include <stdint.h>

// BQ40Z50 DAStatus1 (MAC 0x0071) Output Byte Offset Configuration
// Note: SMBus Block Read (0x44) prepends a 2-byte MAC Echo (0x71 0x00) at bytes 0-1.
typedef struct {
    uint8_t min_len;
    uint8_t cell1;
    uint8_t cell2;
    uint8_t cell3;
    uint8_t cell4;
    uint8_t bat;
    uint8_t pack;
    uint8_t cell1_current;
    uint8_t cell2_current;
    uint8_t cell3_current;
    uint8_t cell4_current;
    uint8_t cell1_power;
    uint8_t cell2_power;
    uint8_t cell3_power;
    uint8_t cell4_power;
    uint8_t power;
} bq_dastatus1_offsets_t;

static const bq_dastatus1_offsets_t BQ40Z50_DASTATUS1_OFFSETS = {
    .min_len        = 34,
    .cell1          = 2,
    .cell2          = 4,
    .cell3          = 6,
    .cell4          = 8,
    .bat            = 10,
    .pack           = 12,
    .cell1_current  = 14,
    .cell2_current  = 16,
    .cell3_current  = 18,
    .cell4_current  = 20,
    .cell1_power    = 22,
    .cell2_power    = 24,
    .cell3_power    = 26,
    .cell4_power    = 28,
    .power          = 30
};

#endif // DASTATUS1_OFFSET_0X0071_H
