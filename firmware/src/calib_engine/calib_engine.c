#include "calib_engine.h"
#include "adc_offset_0xf081.h"
#include "smbus.h"
#include "relay/relay.h"
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include <string.h>
#include <math.h>

volatile calib_status_t calib_status = {
    .state = 0,
    .active_channels = 0,
    .error_channels = 0,
    .mode = 0
};

static uint16_t g_target_cell1_mv[7];
static uint16_t g_target_pack_mv[7];
static uint16_t g_target_bat_mv[7];

// Helper function to set CAL_EN state on BQ40Z50 with 0x0057 check and up to 3 retries
bool bq40z50_set_cal_en(uint8_t ch, bool enable) {
    uint8_t mfg_cmd[2] = {0x57, 0x00};
    uint8_t cal_toggle_cmd[2] = {0x2D, 0x00};

    for (int retry = 0; retry < 3; retry++) {
        uint8_t rx_buf[32] = {0};
        uint8_t rx_len = 0;
        bool is_on = false;

        // 1. Check 0x0057 (ManufacturingStatus)
        smbus_write_block(ch, 0x0B, 0x44, mfg_cmd, 2, false);
        sleep_ms(25);
        if (smbus_read_block(ch, 0x0B, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= 2) {
            uint8_t msb = (rx_len >= 4) ? rx_buf[3] : rx_buf[1];
            if (msb & 0x80) {
                is_on = true;
            }
        }

        // If current state matches target 'enable', return PASS (true)
        if (is_on == enable) {
            return true;
        }

        // 2. State mismatch -> Send 0x002D toggle command
        smbus_write_block(ch, 0x0B, 0x44, cal_toggle_cmd, 2, false);
        sleep_ms(100);
    }

    // 3. Final verification check
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
    return false; // Fail after 3 attempts
}

// Execute BQ40Z50 Voltage/Current Calibration in parallel on active channels
static void run_calib_pipeline(void) {
    uint8_t ch_mask = calib_status.active_channels;
    if (calib_status.mode == 1) {
        relay_set_mask(ch_mask); // Enable relays for Current mode
        sleep_ms(1000);
    } else {
        relay_set_mask(0); // Explicitly ensure relays OFF for Voltage Mode
    }

    // 1. Enable CAL_EN mode for active channels
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            if (!bq40z50_set_cal_en(ch, true)) {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE102; // CAL_EN Entry FAIL
            }
        }
    }

    // 3. Raw ADC Mode Start (MAC 0xF081: Word Write 0xF081 to 0x00, then Block Write [0x81, 0xF0] to 0x44)
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
    sleep_ms(20); // Wait for ADC data to settle

    // 4. Sample Raw ADC Data across active channels
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
                // Raw ADC Block read (0x44) length is typically 14 or 16 bytes for BQ40Z50
                if (smbus_read_block(ch, 0x0B, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= BQ40Z50_ADC_OFFSETS.min_len) {
                    uint8_t c1_off = BQ40Z50_ADC_OFFSETS.cell1;
                    uint8_t pack_off = BQ40Z50_ADC_OFFSETS.pack;
                    uint8_t bat_off = BQ40Z50_ADC_OFFSETS.bat;
                    uint8_t cc_off = BQ40Z50_ADC_OFFSETS.current;

                    uint16_t cell1 = rx_buf[c1_off] | (rx_buf[c1_off + 1] << 8);     // Cell voltage 1 (bbBB)
                    uint16_t pack  = rx_buf[pack_off] | (rx_buf[pack_off + 1] << 8); // PACK voltage (ffFF)
                    uint16_t bat   = rx_buf[bat_off] | (rx_buf[bat_off + 1] << 8);   // BAT voltage (ggGG)
                    int16_t  cc    = (int16_t)(rx_buf[cc_off] | (rx_buf[cc_off + 1] << 8)); // Current (aaAA)
                    
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

    // Check if sampling failed for active channels
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (sample_cnt[ch] == 0) {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE104; // Stage 4 ADC sampling FAIL flag
            }
        }
    }

    // 5. Raw ADC Mode Stop (MAC 0xF080: Word Write 0xF080 to 0x00, then Block Write [0x80, 0xF0] to 0x44)
    uint8_t raw_stop_cmd[2] = {0x80, 0xF0};
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_word(ch, 0x0B, 0x00, 0xF080, false);
            smbus_write_block(ch, 0x0B, 0x44, raw_stop_cmd, 2, false);
        }
    }
    sleep_ms(160);

    // 6. Calculate Gain & Write 0x4000 block per channel
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            if (sample_cnt[ch] > 0) {
                if (calib_status.mode == 1) { // CURRENT CALIBRATION
                    double cc_avg = (double)cc_sum[ch] / sample_cnt[ch];
                    if (cc_avg != 0.0) {
                        int16_t target_ma = (int16_t)g_target_cell1_mv[ch]; // We pass target_ma via cell1 target
                        if (target_ma == 0) target_ma = -2000; // default fallback
                        float new_cc_gain = (float)fabs((double)target_ma / cc_avg);
                        float new_cap_gain = new_cc_gain * 298261.6178f;

                        // 1. Stop Raw ADC Mode (0xF080) so BQ40Z50 returns genuine 0x4000 DataFlash block instead of F081 stream
                        uint8_t stop_adc_cmd[2] = {0x80, 0xF0};
                        smbus_write_block(ch, 0x0B, 0x44, stop_adc_cmd, 2, false);
                        smbus_write_word(ch, 0x0B, 0x00, 0xF080, false);
                        sleep_ms(40);

                        // 2. Fetch FRESH 0x4000 DataFlash block from BQ40Z50
                        uint8_t df_block[36] = {0};
                        uint8_t rx_len = 0;
                        uint8_t df_cmd[2] = {0x00, 0x40};
                        smbus_write_block(ch, 0x0B, 0x44, df_cmd, 2, false);
                        sleep_ms(25);
                        smbus_read_block(ch, 0x0B, 0x44, df_block, &rx_len, false);

                        if (rx_len >= 14) {
                            memcpy(df_block + 6, &new_cc_gain, 4);
                            memcpy(df_block + 10, &new_cap_gain, 4);

                            // 6. Save Current Calibration Data (updates 0x4000 block)
                            uint8_t wr_payload[36];
                            wr_payload[0] = 0x00;
                            wr_payload[1] = 0x40;
                            uint8_t copy_len = (rx_len > 32) ? 32 : rx_len;
                            memcpy(wr_payload + 2, df_block, copy_len);
                            
                            smbus_write_block(ch, 0x0B, 0x44, wr_payload, 2 + copy_len, true);
                            sleep_ms(250); // X 250 from script

                            calib_status.results[ch].cell1_gain = (uint16_t)(int16_t)cc_avg;
                            calib_status.results[ch].pack_gain = (uint16_t)(new_cc_gain * 1000.0f);
                            calib_status.results[ch].success = true;
                        } else {
                            calib_status.error_channels |= (1 << (ch - 1));
                            calib_status.results[ch].cell1_gain = 0xE106; // Stage 6 DF cache FAIL
                        }
                    } else {
                        calib_status.error_channels |= (1 << (ch - 1));
                        calib_status.results[ch].cell1_gain = 0xE105; // Stage 5 Zero Avg FAIL
                    }
                } else { // VOLTAGE CALIBRATION
                    double cell1_avg = (double)cell1_sum[ch] / sample_cnt[ch];
                    double pack_avg = (double)pack_sum[ch] / sample_cnt[ch];
                    double bat_avg = (double)bat_sum[ch] / sample_cnt[ch];

                    uint16_t g_cell1 = (cell1_avg > 0) ? (uint16_t)((((double)g_target_cell1_mv[ch] / cell1_avg) * 65536.0) + 0.5) : 32768;
                    uint16_t g_pack = (pack_avg > 0) ? (uint16_t)((((double)g_target_pack_mv[ch] / pack_avg) * 65536.0) + 0.5) : 12800;
                    uint16_t g_bat = (bat_avg > 0) ? (uint16_t)((((double)g_target_bat_mv[ch] / bat_avg) * 65536.0) + 0.5) : 12800;

                    calib_status.results[ch].cell1_gain = g_cell1;
                    calib_status.results[ch].pack_gain = g_pack;
                    calib_status.results[ch].bat_gain = g_bat;
                    calib_status.results[ch].raw_cell1_adc = (uint16_t)cell1_avg;
                    calib_status.results[ch].raw_pack_adc = (uint16_t)pack_avg;
                    calib_status.results[ch].raw_bat_adc = (uint16_t)bat_avg;

                    // Stop Raw ADC Mode (0xF080) so BQ40Z50 returns genuine 0x4000 DataFlash block
                    uint8_t stop_adc_cmd[2] = {0x80, 0xF0};
                    smbus_write_block(ch, 0x0B, 0x44, stop_adc_cmd, 2, false);
                    smbus_write_word(ch, 0x0B, 0x00, 0xF080, false);
                    sleep_ms(40);

                    // Fetch FRESH 0x4000 DataFlash block from BQ40Z50
                    uint8_t df_block[36] = {0};
                    uint8_t rx_len = 0;
                    uint8_t df_cmd[2] = {0x00, 0x40};
                    smbus_write_block(ch, 0x0B, 0x44, df_cmd, 2, false);
                    sleep_ms(25);
                    smbus_read_block(ch, 0x0B, 0x44, df_block, &rx_len, false);

                    if (rx_len >= 6) {
                        df_block[0] = g_cell1 & 0xFF;
                        df_block[1] = (g_cell1 >> 8) & 0xFF;
                        df_block[2] = g_bat & 0xFF;
                        df_block[3] = (g_bat >> 8) & 0xFF;
                        df_block[4] = g_pack & 0xFF;
                        df_block[5] = (g_pack >> 8) & 0xFF;

                        // 6. Save Voltage Calibration Data (updates 0x4000 block: Cell1Gain, BatGain, PackGain)
                        uint8_t wr_payload[36];
                        wr_payload[0] = 0x00;
                        wr_payload[1] = 0x40;
                        uint8_t copy_len = (rx_len > 32) ? 32 : rx_len;
                        memcpy(wr_payload + 2, df_block, copy_len);
                        
                        smbus_write_block(ch, 0x0B, 0x44, wr_payload, 2 + copy_len, true); // Send 0x4000 block write with PEC
                        sleep_ms(250);
                        calib_status.results[ch].success = true;
                    } else {
                        calib_status.error_channels |= (1 << (ch - 1));
                        calib_status.results[ch].cell1_gain = 0xE106; // Stage 6 DF cache FAIL
                    }
                }
            } else {
                calib_status.error_channels |= (1 << (ch - 1));
                calib_status.results[ch].cell1_gain = 0xE104; // Stage 4 Sample Count 0 FAIL
            }
        }
    }
    sleep_ms(250);

    // 7. CAL_EN & Raw ADC Exit: Use bq40z50_set_cal_en(ch, false) with 3-retry verification and reset MAC
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

    // Always turn OFF relays upon calibration pipeline completion
    relay_set_mask(0);

    calib_status.state = 2; // DONE
}

static void calib_worker_entry(void) {
    run_calib_pipeline();
}

bool calib_engine_start(uint8_t channel_mask, uint8_t mode, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]) {
    if (calib_status.state == 1) return false;
    calib_status.active_channels = channel_mask;
    calib_status.error_channels = 0;
    calib_status.mode = mode;
    calib_status.state = 1; // RUNNING
    memset((void*)calib_status.results, 0, sizeof(calib_status.results));
    for (uint8_t ch = 1; ch <= 6; ch++) {
        g_target_cell1_mv[ch] = target_cell1_mv[ch];
        g_target_pack_mv[ch] = target_pack_mv[ch];
        g_target_bat_mv[ch] = target_bat_mv[ch];
    }

    multicore_reset_core1();
    multicore_launch_core1(calib_worker_entry);
    return true;
}
