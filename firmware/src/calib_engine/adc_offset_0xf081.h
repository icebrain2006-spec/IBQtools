#ifndef ADC_OFFSET_0XF081_H
#define ADC_OFFSET_0XF081_H

#include <stdint.h>

// BQ40Z50 Raw ADC (MAC 0xF081) Output Byte Offset Configuration
// Based on TI BQ40Z50 / BQ78350 Technical Reference Manual (TRM)
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
    .min_len = 16,
    .current = 2,
    .cell1   = 4,
    .cell2   = 6,
    .cell3   = 8,
    .cell4   = 10,
    .pack    = 12,
    .bat     = 14
};

#endif // ADC_OFFSET_0XF081_H
