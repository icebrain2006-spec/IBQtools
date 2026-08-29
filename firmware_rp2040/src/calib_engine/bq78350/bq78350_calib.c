/**
 * @file bq78350_calib.c
 * @brief BQ78350 전용 캘리브레이션 모듈 구현부 (스텁)
 */

#include "bq78350_calib.h"
#include "calib_engine.h"

void bq78350_run_calib_pipeline(uint8_t ch_mask, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]) {
    // BQ78350 캘리브레이션 로직 구현 예정 (독립 유지)
    (void)ch_mask; (void)mode; (void)target_cell1_mv; (void)target_pack_mv; (void)target_bat_mv;
}
