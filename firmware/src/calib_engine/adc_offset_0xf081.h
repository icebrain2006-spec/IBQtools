#ifndef ADC_OFFSET_0XF081_H
#define ADC_OFFSET_0XF081_H

#include <stdint.h>

// BQ40Z50 Raw ADC (MAC 0xF081) Output Byte Offset Configuration
// Note: SMBus Block Read (0x44) prepends a 2-byte MAC Echo (0x81 0xF0) at bytes 0-1,
// shifting all TRM offsets by +2 bytes.
typedef struct {
    uint8_t min_len;
    uint8_t current;
    uint8_t cell1;
    uint8_t cell2;
    uint8_t cell3;
    uint8_t cell4;
    uint8_t pack;
    uint8_t bat;
} bq_raw_adc_offsets_t;

static const bq_raw_adc_offsets_t BQ40Z50_ADC_OFFSETS = {
    .min_len = 18,
    .current = 4,
    .cell1   = 6,
    .cell2   = 8,
    .cell3   = 10,
    .cell4   = 12,
    .pack    = 14,
    .bat     = 16
};

#endif // ADC_OFFSET_0XF081_H
