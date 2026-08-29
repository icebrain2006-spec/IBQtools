/**
 * @file bq4050_v0_01_offsets.h
 * @brief BQ4050 Firmware Version 0.01 DataFlash 오프셋 정의
 * Source: reference/dataflashs/df_bq4050_V0_01.csv
 */

#ifndef BQ4050_V0_01_OFFSETS_H
#define BQ4050_V0_01_OFFSETS_H

#include <stdint.h>

typedef struct {
    uint8_t min_len;
    uint8_t cell1_gain;     ///< Cell Gain Offset: 0 (bytes 3-4 in wire frame)
    uint8_t pack_gain;      ///< Pack Gain Offset: 2 (bytes 5-6 in wire frame)
    uint8_t bat_gain;       ///< Bat Gain Offset: 4 (bytes 7-8 in wire frame)
    uint8_t cc_gain;        ///< CC Gain Offset: 6 (bytes 9-12 in wire frame, float)
    uint8_t capacity_gain;  ///< Capacity Gain Offset: 10 (bytes 13-16 in wire frame, float)
} bq4050_v0_01_df_offsets_t;

static const bq4050_v0_01_df_offsets_t BQ4050_V0_01_DF_OFFSETS = {
    .min_len        = 34,
    .cell1_gain     = 3,
    .pack_gain      = 5,
    .bat_gain       = 7,
    .cc_gain        = 9,
    .capacity_gain  = 13
};

#endif // BQ4050_V0_01_OFFSETS_H
