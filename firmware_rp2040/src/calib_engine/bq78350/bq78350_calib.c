/**
 * @file bq78350_calib.c
 * @brief BQ78350 IC 전용 캘리브레이션 파이프라인 및 DataFlash 레지스터 갱신 모듈 구현부
 */

#include "bq78350_calib.h"
#include "bq78350_mac_cmds.h"
#include "bq78350_df_helper.h"
#include "bq78350_adc_helper.h"
#include "bq78350_offsets.h"
#include "calib_engine.h"
#include "smbus.h"
#include "relay/relay.h"
#include "pico/stdlib.h"
#include <string.h>
#include <math.h>

/**
 * @brief 단일 채널 BQ78350 ManufacturingStatus(MAC 0x0057) 읽기 및 CAL_EN 상태 조회 헬퍼 함수
 */
static bool bq78350_get_cal_en_status_single(uint8_t ch) {
    uint8_t rx_buf[32] = {0};
    uint8_t rx_len = 0;

    smbus_write_block(ch, BQ78350_ADDRESS, 0x44, MAC_CMD(BQ78350_MAC_MANUFACTURING_STATUS), 2, false);
    sleep_ms(25);
    if (smbus_read_block(ch, BQ78350_ADDRESS, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= 2) {
        uint8_t msb = (rx_len >= 4) ? rx_buf[3] : rx_buf[1];
        return (msb & 0x80) != 0; // Bit 7가 CAL_EN 플래그
    }
    return false;
}

/**
 * @brief 단일 채널 BQ78350 CAL_EN 활성화/비활성화 제어
 */
static bool bq78350_set_cal_en_single(uint8_t ch, bool enable) {
    for (int retry = 0; retry < 3; retry++) {
        if (bq78350_get_cal_en_status_single(ch) == enable) {
            return true;
        }
        smbus_write_block(ch, BQ78350_ADDRESS, 0x44, MAC_CMD(BQ78350_MAC_CAL_TOGGLE), 2, false);
        sleep_ms(100);
    }
    return (bq78350_get_cal_en_status_single(ch) == enable);
}

/**
 * @brief 선택된 채널 비트마스크 전체의 BQ78350 CAL_EN (ManufacturingStatus) 설정 및 에러 기록
 */
bool bq78350_set_cal_en(uint8_t ch_mask, bool enable) {
    bool all_ok = true;
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            if (!bq78350_set_cal_en_single(ch, enable)) {
                all_ok = false;
                if (enable) {
                    calib_status.error_channels |= (1 << (ch - 1));
                    calib_status.results[ch].cell1_gain = 0xE102; // CAL_EN 진입 실패 에러코드
                }
            }
        }
    }
    return all_ok;
}

/* ========================================================================= */
/* [1. 계산 영역 (Compute Domain)] - 순수 수학적 Gain 연산 및 변환         */
/* ========================================================================= */

/**
 * @brief 전압 Gain 순수 수학적 연산 (Compute Only)
 */
static void bq78350_compute_voltage_gains(uint8_t ch_mask, const bq78350_adc_sums_t *sums, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7], bq78350_volt_gains_t gains[7]) {
    memset(gains, 0, sizeof(bq78350_volt_gains_t) * 7);

    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (sums->sample_cnt[ch] == 0) continue;

            double cell1_avg = (double)sums->cell1_sum[ch] / sums->sample_cnt[ch];
            double pack_avg  = (double)sums->pack_sum[ch] / sums->sample_cnt[ch];
            double bat_avg   = (double)sums->bat_sum[ch] / sums->sample_cnt[ch];

            gains[ch].g_cell1 = (cell1_avg > 0) ? (uint16_t)((((double)target_cell1_mv[ch] / cell1_avg) * 65536.0) + 0.5) : 32768;
            gains[ch].g_pack  = (pack_avg > 0)  ? (uint16_t)((((double)target_pack_mv[ch] / pack_avg) * 65536.0) + 0.5)  : 12800;
            gains[ch].g_bat   = (bat_avg > 0)   ? (uint16_t)((((double)target_bat_mv[ch] / bat_avg) * 65536.0) + 0.5)   : 12800;

            gains[ch].cell1_avg = (uint16_t)cell1_avg;
            gains[ch].pack_avg  = (uint16_t)pack_avg;
            gains[ch].bat_avg   = (uint16_t)bat_avg;

            gains[ch].volt_bytes[0] = gains[ch].g_cell1 & 0xFF;
            gains[ch].volt_bytes[1] = (gains[ch].g_cell1 >> 8) & 0xFF;
            gains[ch].volt_bytes[2] = gains[ch].g_bat & 0xFF;
            gains[ch].volt_bytes[3] = (gains[ch].g_bat >> 8) & 0xFF;
            gains[ch].volt_bytes[4] = gains[ch].g_pack & 0xFF;
            gains[ch].volt_bytes[5] = (gains[ch].g_pack >> 8) & 0xFF;

            gains[ch].valid = true;
        }
    }
}

/**
 * @brief 전류 Gain 순수 수학적 연산 (Compute Only)
 */
static void bq78350_compute_current_gains(uint8_t ch_mask, const bq78350_adc_sums_t *sums, const int16_t target_current_ma[7], bq78350_curr_gains_t gains[7]) {
    memset(gains, 0, sizeof(bq78350_curr_gains_t) * 7);

    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (sums->sample_cnt[ch] == 0) continue;

            double cc_avg = (double)sums->cc_sum[ch] / sums->sample_cnt[ch];
            float target_ma = (float)target_current_ma[ch];
            if (target_ma == 0.0f) target_ma = -2000.0f; // 예외 기본값

            gains[ch].cc_avg = (int16_t)cc_avg;

            if (cc_avg != 0) {
                float new_cc_gain = fabsf(target_ma / (float)cc_avg);
                if (new_cc_gain < 0.1f)  new_cc_gain = 0.1f;
                if (new_cc_gain > 20.0f) new_cc_gain = 20.0f;

                gains[ch].new_cc_gain = new_cc_gain;
                gains[ch].new_cap_gain = new_cc_gain * 298261.6178f;

                memcpy(gains[ch].cur_bytes, &gains[ch].new_cc_gain, 4);
                memcpy(gains[ch].cur_bytes + 4, &gains[ch].new_cap_gain, 4);

                gains[ch].valid = true;
            } else {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE105; // CC ADC 0 에러
            }
        }
    }
}

/**
 * @brief 파이프라인 마감, IC Reset 및 릴레이 안전 복구 (Step 8 ~ 9)
 */
static void bq78350_finalize_pipeline(uint8_t ch_mask) {
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_block(ch, BQ78350_ADDRESS, 0x44, MAC_CMD(BQ78350_MAC_RAW_ADC_STOP), 2, false);
            sleep_ms(20);
        }
    }
    bq78350_set_cal_en(ch_mask, false);
    sleep_ms(20);
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_block(ch, BQ78350_ADDRESS, 0x44, MAC_CMD(BQ78350_MAC_RESET), 2, false); // BQ78350 Reset
            sleep_ms(50);
        }
    }
    sleep_ms(250);
    relay_set_mask(0); // 릴레이 안전 OFF
}

/**
 * @brief BQ78350 전압 캘리브레이션 시퀀스 (Calib 매크로 스타일 직관적 파이프라인)
 */
void bq78350_start_voltage_calib(uint8_t ch_mask, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]) {
    // 1. 릴레이 안전 OFF
    relay_set_mask(0);

    // 2. DataFlash 0x4000 블록 사전 백업 (B 0x44 0x00 0x40)
    bq78350_precache_df4000(ch_mask);

    // 3. CAL_EN 활성화 (CHK_CAL 1, MAC 0x002D Toggle)
    bq78350_set_cal_en(ch_mask, true);

    // 4. Raw ADC 샘플링 수집 (W 0x00 0xF081 -> A 0x44 200 6 -> W 0x00 0xF080)
    bq78350_adc_sums_t sums;
    bq78350_collect_raw_adc_samples(ch_mask, &sums);

    // 5-1. 전압 Gain 수학 연산 (Compute)
    bq78350_volt_gains_t volt_gains[7];
    bq78350_compute_voltage_gains(ch_mask, &sums, target_cell1_mv, target_pack_mv, target_bat_mv, volt_gains);

    // 5-2. DataFlash 0x4000 쓰기 및 검증 (Write Domain)
    bq78350_write_voltage_gains_df(ch_mask, volt_gains);
    sleep_ms(250);

    // 6. 파이프라인 마감, IC Reset 및 릴레이 OFF
    bq78350_finalize_pipeline(ch_mask);
}

/**
 * @brief BQ78350 전류 캘리브레이션 시퀀스 (Calib 매크로 스타일 직관적 파이프라인)
 */
void bq78350_start_current_calib(uint8_t ch_mask, const int16_t target_current_ma[7]) {
    // 1. 하드웨어 부하 릴레이 ON 및 안정화 대기 (Relay ON, X 1000)
    relay_set_mask(ch_mask);
    sleep_ms(1000);

    // 2. DataFlash 0x4000 블록 사전 백업 (B 0x44 0x00 0x40)
    bq78350_precache_df4000(ch_mask);

    // 3. CAL_EN 활성화 (CHK_CAL 1, MAC 0x002D Toggle)
    bq78350_set_cal_en(ch_mask, true);

    // 4. Raw ADC 샘플링 수집 (W 0x00 0xF081 -> A 0x44 200 6 -> W 0x00 0xF080)
    bq78350_adc_sums_t sums;
    bq78350_collect_raw_adc_samples(ch_mask, &sums);

    // 5-1. 전류 Gain 수학 연산 (Compute)
    bq78350_curr_gains_t curr_gains[7];
    bq78350_compute_current_gains(ch_mask, &sums, target_current_ma, curr_gains);

    // 5-2. DataFlash 0x4000 쓰기 및 검증 (Write Domain)
    bq78350_write_current_gains_df(ch_mask, curr_gains);
    sleep_ms(250);

    // 6. 파이프라인 마감, IC Reset 및 릴레이 OFF
    bq78350_finalize_pipeline(ch_mask);
}

/**
 * @brief BQ78350 온도 캘리브레이션/측정 시퀀스 (DAStatus2 MAC 0x0072 기반 파이프라인)
 */
void bq78350_start_temp_calib(uint8_t ch_mask) {
    // 1. 릴레이 안전 OFF
    relay_set_mask(0);

    // 2. DataFlash 0x4000 블록 사전 백업
    bq78350_precache_df4000(ch_mask);

    // 3. DAStatus2 (MAC 0x0072) 조회 및 수집 (6회 샘플링)
    bq78350_collect_dastatus2_samples(ch_mask);

    // 4. 파이프라인 마감, IC Reset 및 릴레이 OFF
    bq78350_finalize_pipeline(ch_mask);
}

/**
 * @brief BQ78350 전용 캘리브레이션 전체 파이프라인 메인 실행 함수
 */
void bq78350_run_calib_pipeline(uint8_t ch_mask, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7], const int16_t target_current_ma[7]) {
    if (mode == 1) {
        bq78350_start_current_calib(ch_mask, target_current_ma);
    } else if (mode == 2) {
        bq78350_start_temp_calib(ch_mask);
    } else {
        bq78350_start_voltage_calib(ch_mask, target_cell1_mv, target_pack_mv, target_bat_mv);
    }
}
