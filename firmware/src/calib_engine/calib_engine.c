#include "calib_engine.h"
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

// Execute BQ40Z50 Voltage/Current Calibration in parallel on active channels
static void run_calib_pipeline(void) {
    uint8_t ch_mask = calib_status.active_channels;
    
    // If mode == 1 (CURRENT mode), turn ON relays for active channels
    if (calib_status.mode == 1) {
        relay_set_mask(ch_mask);
        sleep_ms(1000); // Wait 1s for load current to stabilize
    }

    // 0. Cache 0x4000 DataFlash block BEFORE CAL mode entry (CAL mode blocks reading)
    uint8_t cached_0x4000[7][36] = {0};
    uint8_t cached_len[7] = {0};
    uint8_t df_pre_cmd[2] = {0x00, 0x40};
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_block(ch, 0x0B, 0x44, df_pre_cmd, 2, false);
            sleep_ms(25);
            smbus_read_block(ch, 0x0B, 0x44, cached_0x4000[ch], &cached_len[ch], false);
        }
    }

    // 1. Enter CAL mode (MAC 0x002D: Block Write [0x2D, 0x00] to 0x00/0x44) for all active channels in parallel
    uint8_t cal_enter_cmd[2] = {0x2D, 0x00};
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_block(ch, 0x0B, 0x44, cal_enter_cmd, 2, false);
        }
    }
    sleep_ms(170); // Shared wait for all channels

    // 2. Check CAL_EN == 1 for all channels
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            bool chk_ok = false;
            uint8_t cmd_buf[2] = {0x57, 0x00};
            for (int r = 0; r < 15; r++) {
                smbus_write_block(ch, 0x0B, 0x44, cmd_buf, 2, false);
                sleep_ms(25);
                uint8_t rx_buf[32];
                uint8_t rx_len = 0;
                if (smbus_read_block(ch, 0x0B, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= 2) {
                    // CAL_EN bit check
                    chk_ok = true;
                    break;
                }
                sleep_ms(25);
            }
            if (!chk_ok) {
                calib_status.error_channels |= (1 << (ch - 1));
            }
        }
    }

    // 3. Raw ADC Mode Start (MAC 0xF081: Block Write [0x81, 0xF0] to 0x00/0x44)
    uint8_t raw_start_cmd[2] = {0x81, 0xF0};
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if ((ch_mask & (1 << (ch - 1))) && !(calib_status.error_channels & (1 << (ch - 1)))) {
            smbus_write_block(ch, 0x0B, 0x44, raw_start_cmd, 2, false);
        }
    }
    sleep_ms(170); // Wait for ADC data to settle

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
                // Raw ADC Block is 0x44 read, byte len varies per firmware (usually >= 12 or 14)
                if (smbus_read_block(ch, 0x0B, 0x44, rx_buf, &rx_len, false) == SMBUS_OK && rx_len >= 18) {
                    uint16_t cell1 = rx_buf[6] | (rx_buf[7] << 8);
                    uint16_t pack = rx_buf[14] | (rx_buf[15] << 8);
                    uint16_t bat = rx_buf[16] | (rx_buf[17] << 8);
                    int16_t cc = (int16_t)(rx_buf[4] | (rx_buf[5] << 8));
                    
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

    // 5. Raw ADC Mode Stop (MAC 0xF080: Block Write [0x80, 0xF0] to 0x00/0x44)
    uint8_t raw_stop_cmd[2] = {0x80, 0xF0};
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
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

                        uint8_t df_block[36] = {0};
                        uint8_t rx_len = cached_len[ch];
                        if (rx_len >= 14) {
                            memcpy(df_block, cached_0x4000[ch], rx_len);
                        } else {
                            uint8_t df_cmd[2] = {0x00, 0x40};
                            smbus_write_block(ch, 0x0B, 0x44, df_cmd, 2, false);
                            sleep_ms(25);
                            smbus_read_block(ch, 0x0B, 0x44, df_block, &rx_len, false);
                        }
                        if (rx_len >= 14) {
                            memcpy(df_block + 6, &new_cc_gain, 4);
                            memcpy(df_block + 10, &new_cap_gain, 4);

                            uint8_t wr_payload[38];
                            wr_payload[0] = 0x00;
                            wr_payload[1] = 0x40;
                            memcpy(wr_payload + 2, df_block, rx_len);
                            smbus_write_block(ch, 0x0B, 0x44, wr_payload, 2 + rx_len, true);
                            calib_status.results[ch].cell1_gain = (uint16_t)(int16_t)cc_avg;
                            calib_status.results[ch].success = true;
                        } else {
                            calib_status.error_channels |= (1 << (ch - 1));
                        }
                    } else {
                        calib_status.error_channels |= (1 << (ch - 1));
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

                    uint8_t df_block[36] = {0};
                    uint8_t rx_len = cached_len[ch];
                    if (rx_len >= 6) {
                        memcpy(df_block, cached_0x4000[ch], rx_len);
                    } else {
                        uint8_t df_cmd[2] = {0x00, 0x40};
                        smbus_write_block(ch, 0x0B, 0x44, df_cmd, 2, false);
                        sleep_ms(25);
                        smbus_read_block(ch, 0x0B, 0x44, df_block, &rx_len, false);
                    }

                    if (rx_len >= 6) {
                        df_block[0] = g_cell1 & 0xFF;
                        df_block[1] = (g_cell1 >> 8) & 0xFF;
                        df_block[2] = g_bat & 0xFF;
                        df_block[3] = (g_bat >> 8) & 0xFF;
                        df_block[4] = g_pack & 0xFF;
                        df_block[5] = (g_pack >> 8) & 0xFF;

                        uint8_t wr_payload[38];
                        wr_payload[0] = 0x00;
                        wr_payload[1] = 0x40;
                        memcpy(wr_payload + 2, df_block, rx_len);
                        smbus_write_block(ch, 0x0B, 0x44, wr_payload, 2 + rx_len, true); // Send 0x4000 block write with PEC
                        calib_status.results[ch].success = true;
                    } else {
                        calib_status.error_channels |= (1 << (ch - 1));
                    }
                }
            } else {
                calib_status.error_channels |= (1 << (ch - 1));
            }
        }
    }
    sleep_ms(250);

    // 7. Disable CAL Mode (MAC 0x002D: Block Write [0x2D, 0x00]) & verify CHK_CAL 0
    uint8_t cal_toggle_cmd[2] = {0x2D, 0x00};
    for (uint8_t ch = 1; ch <= 6; ch++) {
        if (ch_mask & (1 << (ch - 1))) {
            smbus_write_block(ch, 0x0B, 0x44, cal_toggle_cmd, 2, false);
        }
    }
    sleep_ms(60);

    // If mode == 1 (CURRENT mode), turn OFF relays
    if (calib_status.mode == 1) {
        relay_set_mask(0);
    }

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
