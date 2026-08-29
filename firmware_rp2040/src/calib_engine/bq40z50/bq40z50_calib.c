/**
 * @file bq40z50_calib.c
 * @brief BQ40Z50 IC 전용 캘리브레이션 파이프라인 및 DataFlash 레지스터 갱신 모듈 구현부
 */

#include "bq40z50_calib.h"
#include "bq40z50_offsets.h"
#include "calib_engine.h"
#include "smbus.h"
#include "relay/relay.h"
#include "pico/stdlib.h"
#include <string.h>
#include <math.h>

/** @brief 채널별 DataFlash 0x4000 블록(32 Bytes) 캐싱 버퍼 (1~6번 채널) */
static uint8_t g_cached_df4000[7][36];

/**
 * @brief BQ40Z50 CAL_EN (ManufacturingStatus Calibration Mode) 활성화/비활성화 제어
 * @details 0x0057 ManufacturingStatus 레지스터를 조회하여 0x80(CAL_EN) 비트를 확인하고,
 *          설정하고자 하는 상태와 다를 경우 0x002D 명령을 전송하여 상태를 토글(Toggle)합니다.
 * @param ch SMBus 채널 번호 (1 ~ 6)
 * @param enable true: CAL_EN 활성화, false: 비활성화
 * @return true: 원하는 CAL_EN 상태 진입 성공, false: 설정 실패
 */
bool bq40z50_set_cal_en(uint8_t ch, bool enable) {
    uint8_t mfg_cmd[2] = {0x57, 0x00};        // ManufacturingStatus 읽기 명령 (MAC 0x0057)
    uint8_t cal_toggle_cmd[2] = {0x2D, 0x00}; // CAL_EN 토글 명령 (MAC 0x002D)

    for (int retry = 0; retry < 3; retry++) {
        uint8_t rx_buf[32] = {0};
        uint8_t rx_len = 0;
        bool is_on = false;

        // 1. ManufacturingStatus 읽기 요청
        smbus_write_block(ch, 0x0B, 0x44, mfg_cmd, 2, false);
        sleep_ms(25);
        if (smbus_read_block(ch, 0x0B, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= 2) {
            uint8_t msb = (rx_len >= 4) ? rx_buf[3] : rx_buf[1];
            if (msb & 0x80) { // MSB의 0x80 비트가 CAL_EN 플래그
                is_on = true;
            }
        }

        // 2. 이미 목표 상태와 일치하면 즉시 리턴
        if (is_on == enable) {
            return true;
        }

        // 3. 상태가 다르면 토글 명령 전송 후 대기
        smbus_write_block(ch, 0x0B, 0x44, cal_toggle_cmd, 2, false);
        sleep_ms(100);
    }

    // 최종 상태 재검증
    uint8_t rx_buf[32] = {0};
    uint8_t rx_len = 0;
    smbus_write_block(ch, 0x0B, 0x44, mfg_cmd, 2, false);
    sleep_ms(25);
    if (smbus_read_block(ch, 0x0B, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= 2) {
        uint8_t msb = (rx_len >= 4) ? rx_buf[3] : rx_buf[1];
        bool is_on = (msb & 0x80) != 0;
        if (is_on == enable) {
            return true;
        }
    }
    return false;
}

/**
 * @brief DataFlash 특정 서브클래스(Subclass) 블록 내 필드 데이터 갱신 및 검증 (Write & Read-back Verify)
 * @details 0x4000 등 DataFlash 블록 데이터의 특정 오프셋 값을 변경한 뒤 32바이트 전체에 대해
 *          BQ40Z50 규칙에 맞춰 Write하고, 다시 Read-back하여 정상 기록되었는지 비교 검증합니다.
 * @param ch SMBus 채널 번호 (1 ~ 6)
 * @param subclass_addr DataFlash 서브클래스 주소 (예: 0x4000)
 * @param field_offset 블록 내 갱신할 바이트 오프셋
 * @param new_data 갱신할 데이터 포인터
 * @param data_len 갱신할 데이터 바이트 길이
 * @return true: DataFlash 쓰기 및 재검증 성공, false: 실패
 */
static bool bq40z50_update_df_block_offset(uint8_t ch, uint16_t subclass_addr, uint8_t field_offset, const uint8_t *new_data, uint8_t data_len) {
    if (ch < 1 || ch > 6 || !new_data || data_len == 0 || (field_offset + data_len) > 32) {
        return false;
    }

    uint8_t df_block[36];
    memcpy(df_block, g_cached_df4000[ch], 34);

    // 1. 버퍼 및 캐시 내 오프셋 데이터 덮어쓰기
    memcpy(df_block + 2 + field_offset, new_data, data_len);
    memcpy(g_cached_df4000[ch] + 2 + field_offset, new_data, data_len);

    // 2. Gain 값 무효화 방지용 안전 검사 (Cell1, Bat, Pack Gain이 정상 범위인지 확인)
    uint8_t c1_idx   = get_payload_offset(BQ40Z50_DF4000_OFFSETS.cell1_gain);
    uint8_t bat_idx  = get_payload_offset(BQ40Z50_DF4000_OFFSETS.bat_gain);
    uint8_t pack_idx = get_payload_offset(BQ40Z50_DF4000_OFFSETS.pack_gain);

    uint16_t c1_g = df_block[c1_idx] | (df_block[c1_idx + 1] << 8);
    uint16_t bat_g = df_block[bat_idx] | (df_block[bat_idx + 1] << 8);
    uint16_t pack_g = df_block[pack_idx] | (df_block[pack_idx + 1] << 8);

    // 손상된 Gain 값이 발견되면 IC에서 실제 레지스터를 재조회하여 복구
    if (c1_g < 5000 || c1_g > 60000 || bat_g < 5000 || pack_g < 5000) {
        uint8_t df_cmd[2] = { (uint8_t)(subclass_addr & 0xFF), (uint8_t)((subclass_addr >> 8) & 0xFF) };
        uint8_t ref_block[36] = {0};
        uint8_t ref_len = 0;
        smbus_write_block(ch, 0x0B, 0x44, df_cmd, 2, true);
        sleep_ms(40);
        if (smbus_read_block(ch, 0x0B, 0x44, ref_block, &ref_len, true) == SMBUS_OK && ref_len >= 16) {
            uint16_t ref_c1 = ref_block[2] | (ref_block[3] << 8);
            if (ref_c1 >= 5000 && ref_c1 <= 60000) {
                memcpy(df_block + 2, ref_block + 2, 6);
                memcpy(g_cached_df4000[ch] + 2, ref_block + 2, 6);
            }
        }
    }

    // 3. DataFlash 32바이트 블록 쓰기 페이로드 생성 (주소 2바이트 + 데이터 32바이트)
    uint8_t wr_payload[36];
    wr_payload[0] = (uint8_t)(subclass_addr & 0xFF);
    wr_payload[1] = (uint8_t)((subclass_addr >> 8) & 0xFF);
    memcpy(wr_payload + 2, df_block + 2, 32);

    // DataFlash 쓰기 실행
    smbus_write_block(ch, 0x0B, 0x44, wr_payload, 34, false);
    sleep_ms(240); // DataFlash Flash Programming 지연시간 대기

    // 4. 재읽기(Read-back)를 통한 쓰기 검증
    uint8_t df_cmd[2] = { (uint8_t)(subclass_addr & 0xFF), (uint8_t)((subclass_addr >> 8) & 0xFF) };
    smbus_write_block(ch, 0x0B, 0x44, df_cmd, 2, true);
    sleep_ms(30);
    uint8_t verify_block[36] = {0};
    uint8_t verify_len = 0;
    if (smbus_read_block(ch, 0x0B, 0x44, verify_block, &verify_len, true) == SMBUS_OK && verify_len >= (2 + field_offset + data_len)) {
        if (memcmp(verify_block + 2 + field_offset, new_data, data_len) == 0) {
            return true; // 성공적으로 갱신됨
        }
    }
    return false;
}

/**
 * @brief DataFlash 0x4000 블록 데이터 사전 백업 및 버퍼 정렬 (Step 2)
 * @param ch_mask 채널 비트마스크
 */
static void bq40z50_precache_df4000(uint8_t ch_mask) {
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            uint8_t df_cmd[2] = {0x00, 0x40};
            uint8_t rx_len = 0;
            smbus_write_block(ch, 0x0B, 0x44, df_cmd, 2, true);
            sleep_ms(40);
            if (smbus_read_block(ch, 0x0B, 0x44, g_cached_df4000[ch], &rx_len, true) == SMBUS_OK && rx_len >= 16) {
                for (int i = 0; i < rx_len - 14; i++) {
                    if (g_cached_df4000[ch][i] == 0x00 && g_cached_df4000[ch][i+1] == 0x40) {
                        if (i > 0) {
                            memmove(g_cached_df4000[ch], g_cached_df4000[ch] + i, rx_len - i);
                        }
                        break;
                    }
                }
            }
        }
    }
}

/** @brief Raw ADC 6회 샘플링 누적 구조체 */
typedef struct {
    uint32_t cell1_sum[7];
    uint32_t pack_sum[7];
    uint32_t bat_sum[7];
    int32_t  cc_sum[7];
    uint8_t  sample_cnt[7];
} bq40z50_adc_sums_t;

/**
 * @brief Raw ADC 모드 진입 및 6회 샘플링 데이터 수집 (Step 4 ~ 6)
 * @param ch_mask 채널 비트마스크
 * @param sums 샘플링 누적 결과 저장 구조체 포인터
 */
static void bq40z50_collect_raw_adc_samples(uint8_t ch_mask, bq40z50_adc_sums_t *sums) {
    memset(sums, 0, sizeof(bq40z50_adc_sums_t));

    // 1. Raw ADC 모드 진입 (MAC 0xF081)
    uint8_t raw_start_cmd[2] = {0x81, 0xF0};
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            smbus_write_word(ch, 0x0B, 0x00, 0xF081, false);
        }
    }
    sleep_ms(225);
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            smbus_write_block(ch, 0x0B, 0x44, raw_start_cmd, 2, false);
        }
    }
    sleep_ms(20);

    // 2. 6회 샘플링 수집
    for (int sample = 0; sample < 6; sample++) {
        uint32_t start_ms = to_ms_since_boot(get_absolute_time());
        for (uint8_t ch = 1; ch <= 6; ch++) {
            if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
                uint8_t rx_buf[32];
                uint8_t rx_len = 0;
                if (smbus_read_block(ch, 0x0B, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= BQ40Z50_ADC_OFFSETS.min_len) {
                    uint8_t c1_off   = get_payload_offset(BQ40Z50_ADC_OFFSETS.cell1);
                    uint8_t pack_off = get_payload_offset(BQ40Z50_ADC_OFFSETS.pack);
                    uint8_t bat_off  = get_payload_offset(BQ40Z50_ADC_OFFSETS.bat);
                    uint8_t cc_off   = get_payload_offset(BQ40Z50_ADC_OFFSETS.current);

                    uint16_t cell1 = rx_buf[c1_off] | (rx_buf[c1_off + 1] << 8);
                    uint16_t pack  = rx_buf[pack_off] | (rx_buf[pack_off + 1] << 8);
                    uint16_t bat   = rx_buf[bat_off] | (rx_buf[bat_off + 1] << 8);
                    int16_t cc = (int16_t)(rx_buf[cc_off] | (rx_buf[cc_off + 1] << 8));
                    
                    if (sums->sample_cnt[ch] == 0) {
                        uint8_t c_len = (rx_len > 18) ? 18 : rx_len;
                        memcpy((void*)calib_status.results[ch].raw_bytes, rx_buf, c_len);
                    }
                    sums->cell1_sum[ch] += cell1;
                    sums->pack_sum[ch] += pack;
                    sums->bat_sum[ch] += bat;
                    sums->cc_sum[ch] += cc;
                    sums->sample_cnt[ch]++;
                }
            }
        }
        uint32_t elapsed = to_ms_since_boot(get_absolute_time()) - start_ms;
        if (elapsed < 200) {
            sleep_ms(200 - elapsed);
        }
    }

    // 3. 샘플링 개수 검증
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (sums->sample_cnt[ch] == 0) {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE104; // Raw ADC 수신 실패 에러코드
            }
        }
    }

    // 4. Raw ADC 모드 정지 (MAC 0xF080)
    uint8_t raw_stop_cmd[2] = {0x80, 0xF0};
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_word(ch, 0x0B, 0x00, 0xF080, false);
            smbus_write_block(ch, 0x0B, 0x44, raw_stop_cmd, 2, false);
            bq40z50_set_cal_en(ch, false);
        }
    }
    sleep_ms(200);
}

/**
 * @brief 모드별 Gain 연산 및 DataFlash 0x4000 기록 (Step 7)
 */
static void bq40z50_calculate_and_apply_gains(uint8_t ch_mask, uint8_t mode, const bq40z50_adc_sums_t *sums, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]) {
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (sums->sample_cnt[ch] > 0) {
                if (mode == 1) { // [전류 캘리브레이션 연산]
                    double cc_avg = (double)sums->cc_sum[ch] / sums->sample_cnt[ch];
                    float target_ma = -2000.0f; // -2000mA 로드 기준
                    if (cc_avg != 0) {
                        float new_cc_gain = fabsf(target_ma / (float)cc_avg);
                        if (new_cc_gain < 0.1f) new_cc_gain = 0.1f;
                        if (new_cc_gain > 20.0f) new_cc_gain = 20.0f;
                        float new_cap_gain = new_cc_gain * 298261.6178f; // Capacity Gain 비례 계수 곱

                        uint8_t cur_bytes[8];
                        memcpy(cur_bytes, &new_cc_gain, 4);
                        memcpy(cur_bytes + 4, &new_cap_gain, 4);

                        // CC Gain 및 Capacity Gain 쓰기 (오프셋 6)
                        if (bq40z50_update_df_block_offset(ch, 0x4000, 6, cur_bytes, 8)) {
                            calib_status.results[ch].cell1_gain = (uint16_t)(int16_t)cc_avg;
                            calib_status.results[ch].pack_gain = (uint16_t)(new_cc_gain * 1000.0f);
                            calib_status.results[ch].success = true;
                        } else {
                            calib_status.error_channels |= (1 << (ch - 1));
                            calib_status.results[ch].cell1_gain = 0xE106; // DF 쓰기 검증 실패
                        }
                    } else {
                        calib_status.error_channels |= (1 << (ch - 1));
                        calib_status.results[ch].cell1_gain = 0xE105; // CC ADC 0 분모 에러
                    }
                } else { // [전압 캘리브레이션 연산]
                    double cell1_avg = (double)sums->cell1_sum[ch] / sums->sample_cnt[ch];
                    double pack_avg = (double)sums->pack_sum[ch] / sums->sample_cnt[ch];
                    double bat_avg = (double)sums->bat_sum[ch] / sums->sample_cnt[ch];

                    // BQ40Z50 전압 Gain 연산 공식: (Target_mV / Raw_ADC_Avg) * 65536 + 0.5
                    uint16_t g_cell1 = (cell1_avg > 0) ? (uint16_t)((((double)target_cell1_mv[ch] / cell1_avg) * 65536.0) + 0.5) : 32768;
                    uint16_t g_pack = (pack_avg > 0) ? (uint16_t)((((double)target_pack_mv[ch] / pack_avg) * 65536.0) + 0.5) : 12800;
                    uint16_t g_bat = (bat_avg > 0) ? (uint16_t)((((double)target_bat_mv[ch] / bat_avg) * 65536.0) + 0.5) : 12800;

                    calib_status.results[ch].cell1_gain = g_cell1;
                    calib_status.results[ch].pack_gain = g_pack;
                    calib_status.results[ch].bat_gain = g_bat;
                    calib_status.results[ch].raw_cell1_adc = (uint16_t)cell1_avg;
                    calib_status.results[ch].raw_pack_adc = (uint16_t)pack_avg;
                    calib_status.results[ch].raw_bat_adc = (uint16_t)bat_avg;

                    uint8_t volt_bytes[6];
                    volt_bytes[0] = g_cell1 & 0xFF;
                    volt_bytes[1] = (g_cell1 >> 8) & 0xFF;
                    volt_bytes[2] = g_bat & 0xFF;
                    volt_bytes[3] = (g_bat >> 8) & 0xFF;
                    volt_bytes[4] = g_pack & 0xFF;
                    volt_bytes[5] = (g_pack >> 8) & 0xFF;

                    // Cell1, Bat, Pack Gain 쓰기 (오프셋 0)
                    if (bq40z50_update_df_block_offset(ch, 0x4000, 0, volt_bytes, 6)) {
                        calib_status.results[ch].success = true;
                    } else {
                        calib_status.error_channels |= (1 << (ch - 1));
                        calib_status.results[ch].cell1_gain = 0xE106; // DF 쓰기 검증 실패
                    }
                }
            } else {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE104;
            }
        }
    }
    sleep_ms(250);
}

/**
 * @brief 파이프라인 마감, IC Reset 및 릴레이 안전 복구 (Step 8 ~ 9)
 */
static void bq40z50_finalize_pipeline(uint8_t ch_mask) {
    uint8_t pipeline_stop_cmd[2] = {0x80, 0xF0};
    uint8_t reset_cmd[2] = {0x12, 0x00};

    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_block(ch, 0x0B, 0x44, pipeline_stop_cmd, 2, false);
            sleep_ms(20);
            bq40z50_set_cal_en(ch, false);
            sleep_ms(20);
            smbus_write_block(ch, 0x0B, 0x44, reset_cmd, 2, false); // BQ40Z50 칩 리셋으로 새 Gain 적용
            sleep_ms(50);
        }
    }
    sleep_ms(250);

    // 하드웨어 릴레이 OFF 안전 복구
    relay_set_mask(0);
}

/**
 * @brief BQ40Z50 전용 캘리브레이션 전체 파이프라인 메인 실행 함수 (Core1 비동기 실행)
 */
void bq40z50_run_calib_pipeline(uint8_t ch_mask, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]) {
    // 1. 전류 모드일 경우 하드웨어 부하 릴레이(Relay) ON
    if (mode == 1) {
        relay_set_mask(ch_mask);
        sleep_ms(1000); // 릴레이 접점 접촉 및 전류 안정을 위한 1초 대기
    } else {
        relay_set_mask(0);
    }

    // 2. DataFlash 0x4000 블록 데이터 사전 읽기 (Pre-caching)
    bq40z50_precache_df4000(ch_mask);

    // 3. ManufacturingStatus CAL_EN 진입
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            if (!bq40z50_set_cal_en(ch, true)) {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE102; // CAL_EN 진입 실패 에러코드
            }
        }
    }

    // 4 ~ 6. Raw ADC 6회 샘플링 수집
    bq40z50_adc_sums_t sums;
    bq40z50_collect_raw_adc_samples(ch_mask, &sums);

    // 7. 모드별 Gain 연산 및 DataFlash 0x4000 기록
    bq40z50_calculate_and_apply_gains(ch_mask, mode, &sums, target_cell1_mv, target_pack_mv, target_bat_mv);

    // 8 ~ 9. 파이프라인 마감, IC Reset 및 릴레이 OFF
    bq40z50_finalize_pipeline(ch_mask);
}
