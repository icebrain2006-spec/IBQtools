#include "calib_engine.h"
#include "bq40z50/bq40z50_calib.h"
#include "bq78350/bq78350_calib.h"
#include "bq40z80/bq40z80_calib.h"
#include "relay/relay.h"
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include <string.h>

volatile calib_status_t calib_status = {
    .state = 0,
    .active_channels = 0,
    .error_channels = 0,
    .mode = 0,
    .ic_type = 0
};

static uint16_t g_target_cell1_mv[7];
static uint16_t g_target_pack_mv[7];
static uint16_t g_target_bat_mv[7];

static void run_calib_pipeline(void) {
    switch (calib_status.ic_type) {
        case IC_TYPE_BQ40Z50:
            bq40z50_run_calib_pipeline(calib_status.active_channels, calib_status.mode, g_target_cell1_mv, g_target_pack_mv, g_target_bat_mv);
            break;
        case IC_TYPE_BQ78350:
            bq78350_run_calib_pipeline(calib_status.active_channels, calib_status.mode, g_target_cell1_mv, g_target_pack_mv, g_target_bat_mv);
            break;
        case IC_TYPE_BQ40Z80:
            bq40z80_run_calib_pipeline(calib_status.active_channels, calib_status.mode, g_target_cell1_mv, g_target_pack_mv, g_target_bat_mv);
            break;
        default:
            bq40z50_run_calib_pipeline(calib_status.active_channels, calib_status.mode, g_target_cell1_mv, g_target_pack_mv, g_target_bat_mv);
            break;
    }

    relay_set_mask(0);
    calib_status.state = 2; // DONE
}

static void calib_worker_entry(void) {
    run_calib_pipeline();
}

void calib_engine_init(void) {
    calib_status.state = 0;
}

bool calib_engine_start(uint8_t channel_mask, uint8_t mode, uint8_t ic_type, const uint16_t target_cell1_mv[7], const uint16_t target_pack_mv[7], const uint16_t target_bat_mv[7]) {
    if (calib_status.state == 1) return false;
    calib_status.active_channels = channel_mask;
    calib_status.error_channels = 0;
    calib_status.mode = mode;
    calib_status.ic_type = ic_type;
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
