/**
 * @file bq40z50_v3_09_offsets.h
 * @brief BQ40Z50 Firmware Version 3.09 DataFlash 및 MAC 오프셋 정의
 * Source: reference/dataflashs/df_bq40z50_V3_09.csv
 */

#ifndef BQ40Z50_V3_09_OFFSETS_H
#define BQ40Z50_V3_09_OFFSETS_H

#include <stdint.h>

typedef struct {
    uint8_t min_len;
    uint8_t cell1_gain;     ///< Cell Gain Offset: 0 (bytes 3-4 in wire frame)
    uint8_t pack_gain;      ///< Pack Gain Offset: 2 (bytes 5-6 in wire frame)
    uint8_t bat_gain;       ///< Bat Gain Offset: 4 (bytes 7-8 in wire frame)
    uint8_t cc_gain;        ///< CC Gain Offset: 6 (bytes 9-12 in wire frame, float)
    uint8_t capacity_gain;  ///< Capacity Gain Offset: 10 (bytes 13-16 in wire frame, float)
} bq40z50_v3_09_df_offsets_t;

static const bq40z50_v3_09_df_offsets_t BQ40Z50_V3_09_DF_OFFSETS = {
    .min_len        = 34,
    .cell1_gain     = 3,
    .pack_gain      = 5,
    .bat_gain       = 7,
    .cc_gain        = 9,
    .capacity_gain  = 13
};

#endif // BQ40Z50_V3_09_OFFSETS_H
