/**
 * @file bq40z80_calib.c
 * @brief BQ40Z80 전용 캘리브레이션 모듈 구현부 (스텁)
 */

#include "bq40z80_calib.h"
#include "calib_engine.h"

void bq40z80_run_calib_pipeline(uint8_t ch_mask, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7], const int16_t target_current_ma[7]) {
    // BQ40Z80 캘리브레이션 로직 구현 예정 (독립 유지)
    (void)ch_mask; (void)mode; (void)target_cell1_mv; (void)target_pack_mv; (void)target_bat_mv; (void)target_current_ma;
}
