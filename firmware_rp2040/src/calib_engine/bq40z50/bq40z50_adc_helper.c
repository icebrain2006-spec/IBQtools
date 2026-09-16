/**
 * @file bq40z50_adc_helper.c
 * @brief BQ40Z50 Raw ADC 및 DAStatus2 샘플링 수집 모듈 구현부
 */

#include "bq40z50_adc_helper.h"
#include "bq40z50_calib.h"
#include "bq40z50_mac_cmds.h"
#include "bq40z50_offsets.h"
#include "calib_engine.h"
#include "smbus.h"
#include "pico/stdlib.h"
#include <string.h>

/**
 * @brief Raw ADC 6회 샘플링 수집 루프
 */
static void bq40z50_read_adc_samples_loop(uint8_t ch_mask, bq40z50_adc_sums_t *sums) {
    uint8_t c1_off   = get_payload_offset(BQ40Z50_ADC_OFFSETS.cell1);
    uint8_t pack_off = get_payload_offset(BQ40Z50_ADC_OFFSETS.pack);
    uint8_t bat_off  = get_payload_offset(BQ40Z50_ADC_OFFSETS.bat);
    uint8_t cc_off   = get_payload_offset(BQ40Z50_ADC_OFFSETS.current);

    for (int sample = 0; sample < 6; sample++) {
        uint32_t start_ms = to_ms_since_boot(get_absolute_time());
        for (uint8_t ch = 1; ch <= 6; ch++) {
            if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
                uint8_t rx_buf[32];
                uint8_t rx_len = 0;
                if (smbus_read_block(ch, BQ40Z50_ADDRESS, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= BQ40Z50_ADC_OFFSETS.min_len) {
                    uint16_t cell1 = rx_buf[c1_off] | (rx_buf[c1_off + 1] << 8);
                    uint16_t pack  = rx_buf[pack_off] | (rx_buf[pack_off + 1] << 8);
                    uint16_t bat   = rx_buf[bat_off] | (rx_buf[bat_off + 1] << 8);
                    int16_t cc = (int16_t)(rx_buf[cc_off] | (rx_buf[cc_off + 1] << 8));
                    
                    if (calib_status.mode == 1) {
                        if (sample < 6) {
                            calib_status.results[ch].raw_bytes[sample * 2] = rx_buf[cc_off];
                            calib_status.results[ch].raw_bytes[sample * 2 + 1] = rx_buf[cc_off + 1];
                        }
                        if (sums->sample_cnt[ch] == 0) {
                            calib_status.results[ch].raw_bytes[12] = rx_buf[2];
                            calib_status.results[ch].raw_bytes[13] = rx_buf[3];
                            calib_status.results[ch].raw_bytes[14] = rx_buf[pack_off];
                            calib_status.results[ch].raw_bytes[15] = rx_buf[pack_off + 1];
                            calib_status.results[ch].raw_bytes[16] = rx_buf[bat_off];
                            calib_status.results[ch].raw_bytes[17] = rx_buf[bat_off + 1];
                        }
                    } else if (sums->sample_cnt[ch] == 0) {
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
}

/**
 * @brief Raw ADC 모드 진입 및 6회 샘플링 수집 (MAC 0xF081 -> Read -> MAC 0xF080)
 */
void bq40z50_collect_raw_adc_samples(uint8_t ch_mask, bq40z50_adc_sums_t *sums) {
    memset(sums, 0, sizeof(bq40z50_adc_sums_t));

    // 1. Raw ADC 시작 (W 0x00 0xF081, B 0x44 0x81 0xF0)
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            smbus_write_word(ch, BQ40Z50_ADDRESS, 0x00, BQ40Z50_MAC_RAW_ADC_START, false);
        }
    }
    sleep_ms(225);
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            smbus_write_block(ch, BQ40Z50_ADDRESS, 0x44, MAC_CMD(BQ40Z50_MAC_RAW_ADC_START), 2, false);
        }
    }
    sleep_ms(20);

    // 2. 6회 샘플링 수집 (A 0x44 200 6)
    bq40z50_read_adc_samples_loop(ch_mask, sums);

    // 3. 샘플링 수신 여부 검증
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (sums->sample_cnt[ch] == 0) {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE104; // Raw ADC 수신 실패
            }
        }
    }

    // 4. Raw ADC 정지 (W 0x00 0xF080, B 0x44 0x80 0xF0)
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_word(ch, BQ40Z50_ADDRESS, 0x00, BQ40Z50_MAC_RAW_ADC_STOP, false);
            smbus_write_block(ch, BQ40Z50_ADDRESS, 0x44, MAC_CMD(BQ40Z50_MAC_RAW_ADC_STOP), 2, false);
        }
    }
    bq40z50_set_cal_en(ch_mask, false);
    sleep_ms(200);
}

/**
 * @brief DAStatus2 (MAC 0x0072) 조회 및 수집 (6회 샘플링)
 */
void bq40z50_collect_dastatus2_samples(uint8_t ch_mask) {
    for (int sample = 0; sample < 6; sample++) {
        for (uint8_t ch = 1; ch <= 6; ch++) {
            if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
                uint8_t rx_buf[32] = {0};
                uint8_t rx_len = 0;
                smbus_write_block(ch, BQ40Z50_ADDRESS, 0x44, MAC_CMD(BQ40Z50_MAC_DASTATUS2), 2, false);
                sleep_ms(25);
                if (smbus_read_block(ch, BQ40Z50_ADDRESS, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= BQ40Z50_DASTATUS2_OFFSETS.min_len) {
                    uint8_t int_off = get_payload_offset(BQ40Z50_DASTATUS2_OFFSETS.int_temp);
                    uint16_t int_temp_k = rx_buf[int_off] | (rx_buf[int_off + 1] << 8);
                    
                    calib_status.results[ch].raw_cell1_adc = int_temp_k;
                    calib_status.results[ch].success = true;
                } else {
                    calib_status.error_channels |= (1 << (ch - 1));
                    calib_status.results[ch].cell1_gain = 0xE104;
                }
            }
        }
        sleep_ms(100);
    }
}
