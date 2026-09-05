/**
 * @file bq78350_calib.h
 * @brief BQ78350 전용 캘리브레이션 모듈 헤더
 */

#ifndef BQ78350_CALIB_H
#define BQ78350_CALIB_H

#include <stdint.h>
#include <stdbool.h>

/** @brief BQ78350 SMBus Target Slave Address (7-bit 0x0B, 8-bit Write 0x16) */
#define BQ78350_ADDRESS 0x0B

/**
 * @brief BQ78350 전압 캘리브레이션 실행 (시퀀스 스크립트 스타일 메인 파이프라인)
 */
void bq78350_start_voltage_calib(uint8_t ch_mask, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]);

/**
 * @brief BQ78350 전류 캘리브레이션 실행 (시퀀스 스크립트 스타일 메인 파이프라인)
 * @param ch_mask 대상 채널 비트마스크
 * @param target_current_ma 채널별 목표 전류 (mA, 예: -2000) 배열
 */
void bq78350_start_current_calib(uint8_t ch_mask, const int16_t target_current_ma[7]);

/**
 * @brief BQ78350 온도 캘리브레이션/측정 실행 (시퀀스 스크립트 스타일 메인 파이프라인)
 * @param ch_mask 대상 채널 비트마스크
 */
void bq78350_start_temp_calib(uint8_t ch_mask);

/**
 * @brief BQ78350 캘리브레이션 전체 파이프라인 통합 진입점
 * @param active_channels 대상 채널 비트마스크
 * @param mode 0: VOLTAGE, 1: CURRENT, 2: TEMP
 */
void bq78350_run_calib_pipeline(uint8_t active_channels, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7], const int16_t target_current_ma[7]);

/**
 * @brief BQ78350 선택된 채널 비트마스크 전체의 CAL_EN (0x0057) 상태 설정 및 검증
 * @param ch_mask 채널 비트마스크 (예: 0x03 -> CH1, CH2)
 * @param enable 활성화 여부 (true: ON, false: OFF)
 * @return 모든 선택 채널 설정 성공 여부
 */
bool bq78350_set_cal_en(uint8_t ch_mask, bool enable);

#endif // BQ78350_CALIB_H
