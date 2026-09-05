/**
 * @file bq78350_df_helper.c
 * @brief BQ78350 DataFlash 읽기/쓰기/검증/캐싱 헬퍼 모듈 구현부
 */

#include "bq78350_df_helper.h"
#include "bq78350_offsets.h"
#include "calib_engine.h"
#include "smbus.h"
#include "pico/stdlib.h"
#include <string.h>

/** @brief 채널별 DataFlash 0x4000 블록(32 Bytes) 캐싱 버퍼 (1~6번 채널) */
uint8_t g_cached_df4000_bq78350[7][36];

/**
 * @brief DataFlash 0x4000 블록 데이터 사전 백업 및 버퍼 정렬
 * @param ch_mask 채널 비트마스크
 */
void bq78350_precache_df4000(uint8_t ch_mask) {
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            uint8_t df_cmd[2] = {0x00, 0x40};
            uint8_t rx_len = 0;
            smbus_write_block(ch, 0x0B, 0x44, df_cmd, 2, true);
            sleep_ms(40);
            if (smbus_read_block(ch, 0x0B, 0x44, g_cached_df4000_bq78350[ch], &rx_len, true) == SMBUS_OK && rx_len >= 16) {
                for (int i = 0; i < rx_len - 14; i++) {
                    if (g_cached_df4000_bq78350[ch][i] == 0x00 && g_cached_df4000_bq78350[ch][i+1] == 0x40) {
                        if (i > 0) {
                            memmove(g_cached_df4000_bq78350[ch], g_cached_df4000_bq78350[ch] + i, rx_len - i);
                        }
                        break;
                    }
                }
            }
        }
    }
}

/**
 * @brief DataFlash 특정 서브클래스 블록 내 필드 데이터 갱신 및 검증 (Write & Read-back Verify)
 * @param ch SMBus 채널 번호 (1 ~ 6)
 * @param subclass_addr DataFlash 서브클래스 주소 (예: 0x4000)
 * @param field_offset 블록 내 갱신할 바이트 오프셋
 * @param new_data 갱신할 데이터 포인터
 * @param data_len 갱신할 데이터 바이트 길이
 * @return true: DataFlash 쓰기 및 재검증 성공, false: 실패
 */
bool bq78350_update_df_block_offset(uint8_t ch, uint16_t subclass_addr, uint8_t field_offset, const uint8_t *new_data, uint8_t data_len) {
    if (ch < 1 || ch > 6 || !new_data || data_len == 0 || (field_offset + data_len) > 32) {
        return false;
    }

    uint8_t df_block[36];
    memcpy(df_block, g_cached_df4000_bq78350[ch], 34);

    // 1. 버퍼 및 캐시 내 오프셋 데이터 덮어쓰기
    memcpy(df_block + 2 + field_offset, new_data, data_len);
    memcpy(g_cached_df4000_bq78350[ch] + 2 + field_offset, new_data, data_len);

    // 2. DataFlash 32바이트 블록 쓰기 페이로드 생성 (주소 2바이트 + 데이터 32바이트)
    uint8_t wr_payload[36];
    wr_payload[0] = (uint8_t)(subclass_addr & 0xFF);
    wr_payload[1] = (uint8_t)((subclass_addr >> 8) & 0xFF);
    memcpy(wr_payload + 2, df_block + 2, 32);

    // DataFlash 쓰기 실행
    smbus_write_block(ch, 0x0B, 0x44, wr_payload, 34, false);
    sleep_ms(240); // DataFlash Flash Programming 지연시간 대기

    // 3. 재읽기(Read-back)를 통한 쓰기 검증
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
 * @brief 연산된 전압 Gain 데이터를 DataFlash 0x4000 블록에 쓰기 및 검증 (Write Domain)
 */
void bq78350_write_voltage_gains_df(uint8_t ch_mask, const bq78350_volt_gains_t gains[7]) {
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (!gains[ch].valid) continue;

            calib_status.results[ch].cell1_gain = gains[ch].g_cell1;
            calib_status.results[ch].pack_gain  = gains[ch].g_pack;
            calib_status.results[ch].bat_gain   = gains[ch].g_bat;
            calib_status.results[ch].raw_cell1_adc = gains[ch].cell1_avg;
            calib_status.results[ch].raw_pack_adc  = gains[ch].pack_avg;
            calib_status.results[ch].raw_bat_adc   = gains[ch].bat_avg;

            if (bq78350_update_df_block_offset(ch, 0x4000, 0, gains[ch].volt_bytes, 6)) {
                calib_status.results[ch].success = true;
            } else {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE106; // DF 쓰기 실패
            }
        }
    }
}

/**
 * @brief 연산된 전류 Gain 데이터를 DataFlash 0x4000 블록에 쓰기 및 검증 (Write Domain)
 */
void bq78350_write_current_gains_df(uint8_t ch_mask, const bq78350_curr_gains_t gains[7]) {
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (!gains[ch].valid) continue;

            if (bq78350_update_df_block_offset(ch, 0x4000, 6, gains[ch].cur_bytes, 8)) {
                calib_status.results[ch].cell1_gain = (uint16_t)gains[ch].cc_avg;
                calib_status.results[ch].pack_gain  = (uint16_t)(gains[ch].new_cc_gain * 1000.0f);
                calib_status.results[ch].success    = true;
            } else {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE106; // DF 쓰기 실패
            }
        }
    }
}
