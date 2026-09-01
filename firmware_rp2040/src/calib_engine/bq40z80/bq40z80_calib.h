/**
 * @file bq40z80_calib.h
 * @brief BQ40Z80 전용 캘리브레이션 모듈 헤더 (스텁)
 */

#ifndef BQ40Z80_CALIB_H
#define BQ40Z80_CALIB_H

#include <stdint.h>
#include <stdbool.h>

void bq40z80_run_calib_pipeline(uint8_t active_channels, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7], const int16_t target_current_ma[7]);

#endif // BQ40Z80_CALIB_H
