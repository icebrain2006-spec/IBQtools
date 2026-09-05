/**
 * @file bq78350_adc_helper.h
 * @brief BQ78350 Raw ADC 및 DAStatus2 샘플링 수집 모듈 헤더
 */

#ifndef BQ78350_ADC_HELPER_H
#define BQ78350_ADC_HELPER_H

#include <stdint.h>
#include <stdbool.h>

/** @brief Raw ADC 6회 샘플링 누적 구조체 */
typedef struct {
    uint32_t cell1_sum[7];
    uint32_t pack_sum[7];
    uint32_t bat_sum[7];
    int32_t  cc_sum[7];
    uint8_t  sample_cnt[7];
} bq78350_adc_sums_t;

/**
 * @brief Raw ADC 모드 진입 및 6회 샘플링 수집 (MAC 0xF081 -> Read -> MAC 0xF080)
 */
void bq78350_collect_raw_adc_samples(uint8_t ch_mask, bq78350_adc_sums_t *sums);

/**
 * @brief DAStatus2 (MAC 0x0072) 조회 및 수집 (6회 샘플링)
 */
void bq78350_collect_dastatus2_samples(uint8_t ch_mask);

#endif // BQ78350_ADC_HELPER_H
