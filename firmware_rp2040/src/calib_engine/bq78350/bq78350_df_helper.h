/**
 * @file bq78350_df_helper.h
 * @brief BQ78350 DataFlash 읽기/쓰기/검증/캐싱 헬퍼 모듈 헤더
 */

#ifndef BQ78350_DF_HELPER_H
#define BQ78350_DF_HELPER_H

#include <stdint.h>
#include <stdbool.h>

/** @brief 채널별 DataFlash 0x4000 블록(32 Bytes) 캐싱 버퍼 전역 변수 */
extern uint8_t g_cached_df4000_bq78350[7][36];

/** @brief 전압 Gain 연산 결과 구조체 */
typedef struct {
    uint16_t g_cell1;
    uint16_t g_pack;
    uint16_t g_bat;
    uint16_t cell1_avg;
    uint16_t pack_avg;
    uint16_t bat_avg;
    uint8_t  volt_bytes[6];
    bool     valid;
} bq78350_volt_gains_t;

/** @brief 전류 Gain 연산 결과 구조체 */
typedef struct {
    float    new_cc_gain;
    float    new_cap_gain;
    int16_t  cc_avg;
    uint8_t  cur_bytes[8];
    bool     valid;
} bq78350_curr_gains_t;

/**
 * @brief DataFlash 0x4000 블록 데이터 사전 백업 및 버퍼 정렬
 * @param ch_mask 채널 비트마스크
 */
void bq78350_precache_df4000(uint8_t ch_mask);

/**
 * @brief DataFlash 특정 서브클래스 블록 내 필드 데이터 갱신 및 검증 (Write & Read-back Verify)
 */
bool bq78350_update_df_block_offset(uint8_t ch, uint16_t subclass_addr, uint8_t field_offset, const uint8_t *new_data, uint8_t data_len);

/**
 * @brief 연산된 전압 Gain 데이터를 DataFlash 0x4000 블록에 쓰기 및 검증 (Write Domain)
 */
void bq78350_write_voltage_gains_df(uint8_t ch_mask, const bq78350_volt_gains_t gains[7]);

/**
 * @brief 연산된 전류 Gain 데이터를 DataFlash 0x4000 블록에 쓰기 및 검증 (Write Domain)
 */
void bq78350_write_current_gains_df(uint8_t ch_mask, const bq78350_curr_gains_t gains[7]);

#endif // BQ78350_DF_HELPER_H
