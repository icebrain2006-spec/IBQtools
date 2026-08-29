/**
 * @file bq40z50_calib.c
 * @brief BQ40Z50 전용 캘리브레이션 모듈 구현부
 */

#include "bq40z50_calib.h"
#include "bq40z50_offsets.h"
#include "calib_engine.h"
#include "smbus.h"
#include "relay/relay.h"
#include "pico/stdlib.h"
#include <string.h>
#include <math.h>

static uint8_t g_cached_df4000[7][36];

bool bq40z50_set_cal_en(uint8_t ch, bool enable) {
    uint8_t mfg_cmd[2] = {0x57, 0x00};
    uint8_t cal_toggle_cmd[2] = {0x2D, 0x00};

    for (int retry = 0; retry < 3; retry++) {
        uint8_t rx_buf[32] = {0};
        uint8_t rx_len = 0;
        bool is_on = false;

        smbus_write_block(ch, 0x0B, 0x44, mfg_cmd, 2, false);
        sleep_ms(25);
        if (smbus_read_block(ch, 0x0B, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= 2) {
            uint8_t msb = (rx_len >= 4) ? rx_buf[3] : rx_buf[1];
            if (msb & 0x80) {
                is_on = true;
            }
        }

        if (is_on == enable) {
            return true;
        }

        smbus_write_block(ch, 0x0B, 0x44, cal_toggle_cmd, 2, false);
        sleep_ms(100);
    }

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

static bool bq40z50_update_df_block_offset(uint8_t ch, uint16_t subclass_addr, uint8_t field_offset, const uint8_t *new_data, uint8_t data_len) {
    if (ch < 1 || ch > 6 || !new_data || data_len == 0 || (field_offset + data_len) > 32) {
        return false;
    }

    uint8_t df_block[36];
    memcpy(df_block, g_cached_df4000[ch], 34);

    memcpy(df_block + 2 + field_offset, new_data, data_len);
    memcpy(g_cached_df4000[ch] + 2 + field_offset, new_data, data_len);

    uint16_t c1_g = df_block[2] | (df_block[3] << 8);
    uint16_t bat_g = df_block[4] | (df_block[5] << 8);
    uint16_t pack_g = df_block[6] | (df_block[7] << 8);

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

    uint8_t wr_payload[36];
    wr_payload[0] = (uint8_t)(subclass_addr & 0xFF);
    wr_payload[1] = (uint8_t)((subclass_addr >> 8) & 0xFF);
    memcpy(wr_payload + 2, df_block + 2, 32);

    smbus_write_block(ch, 0x0B, 0x44, wr_payload, 34, false);
    sleep_ms(240);

    uint8_t df_cmd[2] = { (uint8_t)(subclass_addr & 0xFF), (uint8_t)((subclass_addr >> 8) & 0xFF) };
    smbus_write_block(ch, 0x0B, 0x44, df_cmd, 2, true);
    sleep_ms(30);
    uint8_t verify_block[36] = {0};
    uint8_t verify_len = 0;
    if (smbus_read_block(ch, 0x0B, 0x44, verify_block, &verify_len, true) == SMBUS_OK && verify_len >= (2 + field_offset + data_len)) {
        if (memcmp(verify_block + 2 + field_offset, new_data, data_len) == 0) {
            return true;
        }
    }
    return false;
}

void bq40z50_run_calib_pipeline(uint8_t ch_mask, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]) {
    if (mode == 1) {
        relay_set_mask(ch_mask);
        sleep_ms(1000);
    } else {
        relay_set_mask(0);
    }

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

    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            if (!bq40z50_set_cal_en(ch, true)) {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE102;
            }
        }
    }

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

    uint32_t cell1_sum[7] = {0};
    uint32_t pack_sum[7] = {0};
    uint32_t bat_sum[7] = {0};
    int32_t  cc_sum[7] = {0};
    uint8_t sample_cnt[7] = {0};

    for (int sample = 0; sample < 6; sample++) {
        uint32_t start_ms = to_ms_since_boot(get_absolute_time());
        for (uint8_t ch = 1; ch <= 6; ch++) {
            if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
                uint8_t rx_buf[32];
                uint8_t rx_len = 0;
                if (smbus_read_block(ch, 0x0B, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= BQ40Z50_ADC_OFFSETS.min_len) {
                    uint8_t c1_off = BQ40Z50_ADC_OFFSETS.cell1;
                    uint8_t pack_off = BQ40Z50_ADC_OFFSETS.pack;
                    uint8_t bat_off = BQ40Z50_ADC_OFFSETS.bat;
                    uint8_t cc_off = BQ40Z50_ADC_OFFSETS.current;

                    uint16_t cell1 = rx_buf[c1_off] | (rx_buf[c1_off + 1] << 8);
                    uint16_t pack  = rx_buf[pack_off] | (rx_buf[pack_off + 1] << 8);
                    uint16_t bat   = rx_buf[bat_off] | (rx_buf[bat_off + 1] << 8);
                    int16_t cc = (int16_t)(rx_buf[cc_off] | (rx_buf[cc_off + 1] << 8));
                    
                    if (sample_cnt[ch] == 0) {
                        uint8_t c_len = (rx_len > 18) ? 18 : rx_len;
                        memcpy((void*)calib_status.results[ch].raw_bytes, rx_buf, c_len);
                    }
                    cell1_sum[ch] += cell1;
                    pack_sum[ch] += pack;
                    bat_sum[ch] += bat;
                    cc_sum[ch] += cc;
                    sample_cnt[ch]++;
                }
            }
        }
        uint32_t elapsed = to_ms_since_boot(get_absolute_time()) - start_ms;
        if (elapsed < 200) {
            sleep_ms(200 - elapsed);
        }
    }

    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (sample_cnt[ch] == 0) {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE104;
            }
        }
    }

    uint8_t raw_stop_cmd[2] = {0x80, 0xF0};
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_word(ch, 0x0B, 0x00, 0xF080, false);
            smbus_write_block(ch, 0x0B, 0x44, raw_stop_cmd, 2, false);
            bq40z50_set_cal_en(ch, false);
        }
    }
    sleep_ms(200);

    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (sample_cnt[ch] > 0) {
                if (mode == 1) {
                    double cc_avg = (double)cc_sum[ch] / sample_cnt[ch];
                    float target_ma = -2000.0f;
                    if (cc_avg != 0) {
                        float new_cc_gain = fabsf(target_ma / (float)cc_avg);
                        if (new_cc_gain < 0.1f) new_cc_gain = 0.1f;
                        if (new_cc_gain > 20.0f) new_cc_gain = 20.0f;
                        float new_cap_gain = new_cc_gain * 298261.6178f;

                        uint8_t cur_bytes[8];
                        memcpy(cur_bytes, &new_cc_gain, 4);
                        memcpy(cur_bytes + 4, &new_cap_gain, 4);

                        if (bq40z50_update_df_block_offset(ch, 0x4000, 6, cur_bytes, 8)) {
                            calib_status.results[ch].cell1_gain = (uint16_t)(int16_t)cc_avg;
                            calib_status.results[ch].pack_gain = (uint16_t)(new_cc_gain * 1000.0f);
                            calib_status.results[ch].success = true;
                        } else {
                            calib_status.error_channels |= (1 << (ch - 1));
                            calib_status.results[ch].cell1_gain = 0xE106;
                        }
                    } else {
                        calib_status.error_channels |= (1 << (ch - 1));
                        calib_status.results[ch].cell1_gain = 0xE105;
                    }
                } else {
                    double cell1_avg = (double)cell1_sum[ch] / sample_cnt[ch];
                    double pack_avg = (double)pack_sum[ch] / sample_cnt[ch];
                    double bat_avg = (double)bat_sum[ch] / sample_cnt[ch];

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

                    if (bq40z50_update_df_block_offset(ch, 0x4000, 0, volt_bytes, 6)) {
                        calib_status.results[ch].success = true;
                    } else {
                        calib_status.error_channels |= (1 << (ch - 1));
                        calib_status.results[ch].cell1_gain = 0xE106;
                    }
                }
            } else {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE104;
            }
        }
    }
    sleep_ms(250);

    uint8_t pipeline_stop_cmd[2] = {0x80, 0xF0};
    uint8_t reset_cmd[2] = {0x12, 0x00};

    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_block(ch, 0x0B, 0x44, pipeline_stop_cmd, 2, false);
            sleep_ms(20);
            bq40z50_set_cal_en(ch, false);
            sleep_ms(20);
            smbus_write_block(ch, 0x0B, 0x44, reset_cmd, 2, false);
            sleep_ms(50);
        }
    }
    sleep_ms(250);

    relay_set_mask(0);
}
