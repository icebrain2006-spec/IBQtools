/**
 * @file calib_engine.h
 * @brief RP2040 하드웨어 가속 기반 BQ IC 자동 캘리브레이션 엔진 헤더
 */

#ifndef CALIB_ENGINE_H
#define CALIB_ENGINE_H

#include <stdint.h>
#include <stdbool.h>

#define CMD_CALIB_RUN    0x60  ///< 캘리브레이션 시작 명령
#define CMD_CALIB_STATUS 0x61  ///< 캘리브레이션 결과 조회 명령

/**
 * @brief 채널별 캘리브레이션 연산 결과 구조체
 */
typedef struct {
    uint16_t cell1_gain;       ///< 계산된 Cell 1 Gain 값
    uint16_t pack_gain;        ///< 계산된 Pack Gain 값
    uint16_t bat_gain;         ///< 계산된 Bat Gain 값
    bool success;              ///< 캘리브레이션 성공 여부
    uint16_t raw_cell1_adc;    ///< 측정된 Cell 1 raw ADC 값
    uint16_t raw_pack_adc;     ///< 측정된 Pack raw ADC 값
    uint16_t raw_bat_adc;      ///< 측정된 Bat raw ADC 값
    uint8_t raw_bytes[18];     ///< 수신된 레지스터 Raw 응답 데이터
} ch_calib_result_t;

/**
 * @brief 전체 캘리브레이션 실행 상태 정보 구조체
 */
typedef struct {
    uint8_t state;                 ///< 현재 상태 (0: IDLE, 1: RUNNING, 2: DONE, 3: ERROR)
    uint8_t active_channels;       ///< 실행 대상 채널 비트마스크
    uint8_t error_channels;        ///< 실패한 채널 비트마스크
    uint8_t mode;                  ///< 캘리브레이션 모드 (0: VOLTAGE, 1: CURRENT, 2: TEMP)
    ch_calib_result_t results[7];  ///< 채널별 계산 결과 (인덱스 1~6 사용)
} calib_status_t;

/// 전역 캘리브레이션 상태 변수
extern volatile calib_status_t calib_status;

/**
 * @brief 캘리브레이션 엔진 초기화
 */
void calib_engine_init(void);

/**
 * @brief 지정된 채널 및 기준 목표 전압값으로 캘리브레이션 시작
 * @param channel_mask 대상 채널 비트마스크 (bit 0~5)
 * @param mode 캘리브레이션 모드 (0: Voltage)
 * @param target_cell1_mv 채널별 Cell 1 목표 전압 (mV) 배열
 * @param target_pack_mv 채널별 Pack 목표 전압 (mV) 배열
 * @param target_bat_mv 채널별 Bat 목표 전압 (mV) 배열
 * @return 시작 성공 여부
 */
bool calib_engine_start(uint8_t channel_mask, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]);

/**
 * @brief BQ40Z50 IC의 CAL_EN (Calibration Enable 0x0057) 상태 설정
 * @param ch 대상 채널 번호 (1 ~ 6)
 * @param enable 활성화 여부
 * @return 성공 여부
 */
bool bq40z50_set_cal_en(uint8_t ch, bool enable);

#endif // CALIB_ENGINE_H
