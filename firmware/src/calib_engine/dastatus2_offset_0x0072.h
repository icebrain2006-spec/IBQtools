#ifndef DASTATUS2_OFFSET_0X0072_H
#define DASTATUS2_OFFSET_0X0072_H

#include <stdint.h>

// BQ40Z50 DAStatus2 (MAC 0x0072) Output Byte Offset Configuration
// Note: SMBus Block Read (0x44) prepends a 2-byte MAC Echo (0x72 0x00) at bytes 0-1.
typedef struct {
    uint8_t min_len;
    uint8_t int_temp;
    uint8_t ts1_temp;
    uint8_t ts2_temp;
    uint8_t ts3_temp;
    uint8_t ts4_temp;
    uint8_t cell1_raw_adc;
    uint8_t cell2_raw_adc;
    uint8_t cell3_raw_adc;
    uint8_t cell4_raw_adc;
} bq_dastatus2_offsets_t;

static const bq_dastatus2_offsets_t BQ40Z50_DASTATUS2_OFFSETS = {
    .min_len        = 30,
    .int_temp       = 2,
    .ts1_temp       = 4,
    .ts2_temp       = 6,
    .ts3_temp       = 8,
    .ts4_temp       = 10,
    .cell1_raw_adc  = 22,
    .cell2_raw_adc  = 24,
    .cell3_raw_adc  = 26,
    .cell4_raw_adc  = 28
};

#endif // DASTATUS2_OFFSET_0X0072_H
