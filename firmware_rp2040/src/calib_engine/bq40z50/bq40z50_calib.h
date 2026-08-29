/**
 * @file bq40z50_calib.h
 * @brief BQ40Z50 전용 캘리브레이션 모듈 헤더
 */

#ifndef BQ40Z50_CALIB_H
#define BQ40Z50_CALIB_H

#include <stdint.h>
#include <stdbool.h>

/**
 * @brief BQ40Z50 캘리브레이션 파이프라인 실행
 * @param active_channels 대상 채널 비트마스크
 * @param mode 0: VOLTAGE, 1: CURRENT
 * @param target_cell1_mv Cell1 목표 전압 배열
 * @param target_pack_mv Pack 목표 전압 배열
 * @param target_bat_mv Bat 목표 전압 배열
 */
void bq40z50_run_calib_pipeline(uint8_t active_channels, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]);

/**
 * @brief BQ40Z50 CAL_EN (0x0057) 상태 설정 및 검증
 */
bool bq40z50_set_cal_en(uint8_t ch, bool enable);

#endif // BQ40Z50_CALIB_H
