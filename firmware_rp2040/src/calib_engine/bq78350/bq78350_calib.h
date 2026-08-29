/**
 * @file bq78350_calib.h
 * @brief BQ78350 전용 캘리브레이션 모듈 헤더 (스텁)
 */

#ifndef BQ78350_CALIB_H
#define BQ78350_CALIB_H

#include <stdint.h>
#include <stdbool.h>

void bq78350_run_calib_pipeline(uint8_t active_channels, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]);

#endif // BQ78350_CALIB_H
