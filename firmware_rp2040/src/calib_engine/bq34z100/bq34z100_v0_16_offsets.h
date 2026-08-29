/**
 * @file bq34z100_v0_16_offsets.h
 * @brief BQ34Z100-G1 Firmware Version 0.16 DataFlash 오프셋 정의
 * Source: reference/dataflashs/df_bq34z100g1_V0_16.csv
 */

#ifndef BQ34Z100_V0_16_OFFSETS_H
#define BQ34Z100_V0_16_OFFSETS_H

#include <stdint.h>

typedef struct {
    uint8_t min_len;
    uint8_t cc_gain;        ///< CC Gain Offset: 0 (bytes 3-6 in wire frame, float)
    uint8_t capacity_gain;  ///< Capacity Gain Offset: 4 (bytes 7-10 in wire frame, float)
    uint8_t voltage_divider;///< Voltage Divider Offset: 14 (bytes 17-18 in wire frame)
} bq34z100_v0_16_df_offsets_t;

static const bq34z100_v0_16_df_offsets_t BQ34Z100_V0_16_DF_OFFSETS = {
    .min_len        = 34,
    .cc_gain        = 3,
    .capacity_gain  = 7,
    .voltage_divider= 17
};

#endif // BQ34Z100_V0_16_OFFSETS_H
