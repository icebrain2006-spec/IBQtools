/**
 * @file bq78350_v3_00_offsets.h
 * @brief BQ78350 R3 Firmware Version 3.00 DataFlash 오프셋 정의
 * Source: reference/dataflashs/df_bq78350r3_V3_00.csv
 */

#ifndef BQ78350_V3_00_OFFSETS_H
#define BQ78350_V3_00_OFFSETS_H

#include <stdint.h>

typedef struct {
    uint8_t min_len;
    uint8_t cc_gain;        ///< CC Gain Offset: 0 (bytes 3-6 in wire frame, float)
    uint8_t capacity_gain;  ///< Capacity Gain Offset: 4 (bytes 7-10 in wire frame, float)
    uint8_t cell1_offset;   ///< Cell1 Offset: 8 (byte 11 in wire frame)
    uint8_t ext_cell_gain;  ///< Ext Cell Divider Gain Offset: 34 (bytes 37-38 in wire frame)
} bq78350_v3_00_df_offsets_t;

static const bq78350_v3_00_df_offsets_t BQ78350_V3_00_DF_OFFSETS = {
    .min_len        = 34,
    .cc_gain        = 3,
    .capacity_gain  = 7,
    .cell1_offset   = 11,
    .ext_cell_gain  = 37
};

#endif // BQ78350_V3_00_OFFSETS_H
