#include "bq_updater.h"
#include "calib_engine.h"
#include "flash_store.h"
#include "pico/bootrom.h"
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "protocol.h"
#include "relay.h"
#include "smbus.h"
#include "ws2812_control.h"
#include <string.h>

static inline uint32_t read_u32_be(const uint8_t *buf) {
  return ((uint32_t)buf[0] << 24) | ((uint32_t)buf[1] << 16) |
         ((uint32_t)buf[2] << 8) | buf[3];
}

static inline void write_u32_be(uint8_t *buf, uint32_t val) {
  buf[0] = (val >> 24) & 0xFF;
  buf[1] = (val >> 16) & 0xFF;
  buf[2] = (val >> 8) & 0xFF;
  buf[3] = val & 0xFF;
}

static inline uint16_t read_u16_be(const uint8_t *buf) {
  return ((uint16_t)buf[0] << 8) | buf[1];
}

static inline void write_u16_be(uint8_t *buf, uint16_t val) {
  buf[0] = (val >> 8) & 0xFF;
  buf[1] = val & 0xFF;
}

static void handle_packet(const rx_packet_t *pkt) {
  uint8_t resp_payload[256];
  uint16_t resp_len = 0;

  switch (pkt->cmd) {
  case CMD_GET_VERSION: {
    const char *version = "v1.0.114";
    resp_payload[0] = RESP_OK;
    strcpy((char *)(resp_payload + 1), version);
    protocol_send_packet(CMD_GET_VERSION, resp_payload, 1 + strlen(version));
    break;
  }

  case CMD_REBOOT_BOOTSEL: {
    resp_payload[0] = RESP_OK;
    protocol_send_packet(CMD_REBOOT_BOOTSEL, resp_payload, 1);
    sleep_ms(100);        // Allow UART/USB transmit to finish
    reset_usb_boot(0, 0); // Reboot into BOOTSEL mode
    break;
  }

  case CMD_SET_LED_STATE: {
    if (pkt->length < 7) { // 1 cmd + 4 color + 1 mode + 1 duration
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_SET_LED_STATE, resp_payload, 1);
      break;
    }
    uint32_t color = read_u32_be(pkt->payload);
    led_mode_t mode = (led_mode_t)pkt->payload[4];
    uint32_t duration_ms = pkt->payload[5] * 1000; // Received in seconds
    
    led_set_state(color, mode, duration_ms);
    
    resp_payload[0] = RESP_OK;
    protocol_send_packet(CMD_SET_LED_STATE, resp_payload, 1);
    break;
  }

  case CMD_RELAY_SET: {
    if (pkt->length < 2) { // 1 byte cmd + 1 byte payload
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_RELAY_SET, resp_payload, 1);
      break;
    }
    uint8_t mask = pkt->payload[0];
    relay_set_mask(mask);

    resp_payload[0] = RESP_OK;
    resp_payload[1] = relay_get_mask();
    protocol_send_packet(CMD_RELAY_SET, resp_payload, 2);
    break;
  }

  case CMD_RELAY_GET: {
    resp_payload[0] = RESP_OK;
    resp_payload[1] = relay_get_mask();
    protocol_send_packet(CMD_RELAY_GET, resp_payload, 2);
    break;
  }

  case CMD_SMBUS_CMD: {
    if (pkt->length <
        7) { // ch(1), addr(1), cmd(1), rw(1), len(1), pec(1) + data(at least 1)
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_SMBUS_CMD, resp_payload, 1);
      break;
    }
    uint8_t ch = pkt->payload[0];
    uint8_t addr = pkt->payload[1];
    uint8_t cmd_reg = pkt->payload[2];
    uint8_t rw = pkt->payload[3];
    uint8_t len = pkt->payload[4];
    uint8_t use_pec = pkt->payload[5];
    const uint8_t *data = pkt->payload + 6;

    int err = SMBUS_OK;

    if (rw == 0) { // Write
      if (len == 1) {
        err = smbus_write_byte(ch, addr, cmd_reg, data[0], use_pec != 0);
      } else if (len == 2) {
        uint16_t val = (uint16_t)data[0] | ((uint16_t)data[1] << 8);
        err = smbus_write_word(ch, addr, cmd_reg, val, use_pec != 0);
      } else {
        err = smbus_write_block(ch, addr, cmd_reg, data, len, use_pec != 0);
      }

      resp_payload[0] = (err == SMBUS_OK) ? RESP_OK : RESP_ERR_HW;
      resp_payload[1] = (uint8_t)(-err); // Detail error code
      resp_len = 2;
    } else { // Read
      if (len == 1) {
        uint8_t val = 0;
        err = smbus_read_byte(ch, addr, cmd_reg, &val, use_pec != 0);
        resp_payload[1] = val;
        resp_len = 2;
      } else if (len == 2) {
        uint16_t val = 0;
        err = smbus_read_word(ch, addr, cmd_reg, &val, use_pec != 0);
        resp_payload[1] = val & 0xFF;
        resp_payload[2] = (val >> 8) & 0xFF;
        resp_len = 3;
      } else {
        uint8_t rx_len = 0;
        err = smbus_read_block(ch, addr, cmd_reg, resp_payload + 2, &rx_len,
                               use_pec != 0);
        resp_payload[1] = rx_len;
        resp_len = 2 + rx_len;
      }

      resp_payload[0] = (err == SMBUS_OK) ? RESP_OK : RESP_ERR_HW;
      if (err != SMBUS_OK) {
        resp_payload[1] = (uint8_t)(-err);
        resp_len = 2;
      }
    }
    protocol_send_packet(CMD_SMBUS_CMD, resp_payload, resp_len);
    break;
  }
  case CMD_I2C_RAW: {
    if (pkt->length < 4) {
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_I2C_RAW, resp_payload, 1);
      break;
    }
    uint8_t ch = pkt->payload[0];
    uint8_t addr = pkt->payload[1];
    uint8_t tx_len = pkt->payload[2];
    uint8_t rx_len = pkt->payload[3];

    if (pkt->length < 4 + tx_len || rx_len > (PROTOCOL_MAX_PAYLOAD - 2)) {
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_I2C_RAW, resp_payload, 1);
      break;
    }

    const uint8_t *tx_data = pkt->payload + 4;
    int err = SMBUS_OK;

    if (tx_len > 0 && rx_len == 0) {
      err = smbus_i2c_write(ch, addr, tx_data, tx_len);
      resp_len = 2;
    } else if (tx_len == 0 && rx_len > 0) {
      err = smbus_i2c_read(ch, addr, resp_payload + 2, rx_len);
      resp_len = 2 + rx_len;
    } else if (tx_len > 0 && rx_len > 0) {
      err = smbus_i2c_write_read(ch, addr, tx_data, tx_len, resp_payload + 2,
                                 rx_len);
      resp_len = 2 + rx_len;
    } else {
      err = SMBUS_ERR_INVALID;
      resp_len = 2;
    }

    resp_payload[0] = (err == SMBUS_OK) ? RESP_OK : RESP_ERR_HW;
    resp_payload[1] = (uint8_t)(-err);
    protocol_send_packet(CMD_I2C_RAW, resp_payload, resp_len);
    break;
  }
  case CMD_SMBUS_POLL_BLOCK: {
    if (pkt->length < 5) {
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_SMBUS_POLL_BLOCK, resp_payload, 1);
      break;
    }
    uint8_t ch = pkt->payload[0];
    uint8_t addr = pkt->payload[1];
    uint8_t cmd_reg = pkt->payload[2];
    uint8_t interval_ms = pkt->payload[3];
    uint8_t count = pkt->payload[4];

    int err = SMBUS_OK;
    resp_payload[0] = RESP_OK;
    resp_len = 1;

    for (uint8_t i = 0; i < count; i++) {
      if (interval_ms > 0 && i > 0) {
        sleep_ms(interval_ms);
      }
      uint8_t rx_len = 0;
      // max space check to prevent overflow
      if (resp_len + 33 > PROTOCOL_MAX_PAYLOAD) {
        break; // Stop collecting if buffer is full
      }
      err = smbus_read_block(ch, addr, cmd_reg, resp_payload + resp_len + 1, &rx_len, false);
      if (err == SMBUS_OK) {
        resp_payload[resp_len] = rx_len;
        resp_len += (1 + rx_len);
      } else {
        resp_payload[0] = RESP_ERR_HW;
        resp_payload[1] = (uint8_t)(-err);
        resp_len = 2;
        break;
      }
    }
    protocol_send_packet(CMD_SMBUS_POLL_BLOCK, resp_payload, resp_len);
    break;
  }

  case CMD_FW_UPLOAD_START: {
    if (pkt->length < 5) {
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_FW_UPLOAD_START, resp_payload, 1);
      break;
    }
    uint32_t file_size = read_u32_be(pkt->payload);
    int res = flash_store_upload_start(file_size);

    resp_payload[0] = (res == 0) ? RESP_OK : RESP_ERR_HW;
    protocol_send_packet(CMD_FW_UPLOAD_START, resp_payload, 1);
    break;
  }

  case CMD_FW_UPLOAD_DATA: {
    if (pkt->length < 7) {
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_FW_UPLOAD_DATA, resp_payload, 1);
      break;
    }
    uint32_t offset = read_u32_be(pkt->payload);
    uint16_t chunk_len = read_u16_be(pkt->payload + 4);
    const uint8_t *chunk_data = pkt->payload + 6;

    int res = flash_store_upload_chunk(offset, chunk_data, chunk_len);

    resp_payload[0] = (res == 0) ? RESP_OK : RESP_ERR_HW;
    protocol_send_packet(CMD_FW_UPLOAD_DATA, resp_payload, 1);
    break;
  }

  case CMD_FW_UPLOAD_END: {
    if (pkt->length < 9) { // 4(CRC) + 4(Timestamp) + 1(min string len)
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_FW_UPLOAD_END, resp_payload, 1);
      break;
    }
    uint32_t expected_crc = read_u32_be(pkt->payload);
    uint32_t timestamp = read_u32_be(pkt->payload + 4);

    // Default empty strings
    char filename[64] = {0};
    char ic_type[32] = {0};
    char version[32] = {0};
    
    // We expect the payload to be either the old format (variable length filename only)
    // or the new format: filename(null-terminated, max 64) + ic_type(max 32) + version(max 32).
    // Let's support the new format robustly: if length >= 8 + 64 + 32 + 32 = 136 bytes,
    // we use fixed offsets, otherwise we fallback to legacy behavior.
    if (pkt->length >= 8 + 64 + 32 + 32) {
        memcpy(filename, pkt->payload + 8, 64);
        memcpy(ic_type, pkt->payload + 8 + 64, 32);
        memcpy(version, pkt->payload + 8 + 64 + 32, 32);
    } else {
        uint16_t str_len = pkt->length - 8;
        if (str_len > 63) str_len = 63;
        memcpy(filename, pkt->payload + 8, str_len);
    }

    // Sanitize filename
    for (int i = 63; i >= 0; i--) {
      if (filename[i] > 0 && (filename[i] < ' ' || filename[i] > '~')) {
        filename[i] = '\0';
      }
    }
    
    // Sanitize ic_type and version
    for(int i=0; i<32; i++) {
        if(ic_type[i] > 0 && (ic_type[i] < ' ' || ic_type[i] > '~')) ic_type[i] = '\0';
        if(version[i] > 0 && (version[i] < ' ' || version[i] > '~')) version[i] = '\0';
    }

    int res = flash_store_upload_end(expected_crc, timestamp, filename, ic_type, version);

    resp_payload[0] = (res == 0) ? RESP_OK : RESP_ERR_HW;
    protocol_send_packet(CMD_FW_UPLOAD_END, resp_payload, 1);
    break;
  }

  case CMD_FW_GET_FILE_INFO: {
    flash_meta_t meta;
    if (flash_store_get_meta(&meta)) {
      resp_payload[0] = RESP_OK;
      write_u32_be(resp_payload + 1, meta.magic);
      write_u32_be(resp_payload + 5, meta.size);
      write_u32_be(resp_payload + 9, meta.crc32);
      write_u32_be(resp_payload + 13, meta.timestamp);
      memcpy(resp_payload + 17, meta.filename, 64);
      memcpy(resp_payload + 17 + 64, meta.ic_type, 32);
      memcpy(resp_payload + 17 + 64 + 32, meta.version, 32);
      protocol_send_packet(CMD_FW_GET_FILE_INFO, resp_payload, 1 + 16 + 64 + 32 + 32);
    } else {
      resp_payload[0] = RESP_ERR_HW; // Or not found
      protocol_send_packet(CMD_FW_GET_FILE_INFO, resp_payload, 1);
    }
    break;
  }

  case CMD_FW_UPDATE_RUN: {
    if (pkt->length < 2) {
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_FW_UPDATE_RUN, resp_payload, 1);
      break;
    }
    uint8_t ch_mask = pkt->payload[0];
    bool success = bq_updater_start(ch_mask);

    resp_payload[0] = success ? RESP_OK : RESP_ERR_BUSY;
    protocol_send_packet(CMD_FW_UPDATE_RUN, resp_payload, 1);
    break;
  }

  case CMD_FW_UPDATE_STATUS: {
    resp_payload[0] = RESP_OK;
    resp_payload[1] = (uint8_t)update_status.state;
    write_u32_be(resp_payload + 2, update_status.current_line);
    write_u32_be(resp_payload + 6, update_status.total_lines);
    resp_payload[10] = update_status.active_channels;
    resp_payload[11] = update_status.error_channels;
    write_u32_be(resp_payload + 12, (uint32_t)update_status.error_code);
    protocol_send_packet(CMD_FW_UPDATE_STATUS, resp_payload, 16);
    break;
  }

  case CMD_FW_UPDATE_STOP: {
    bq_updater_stop();
    resp_payload[0] = RESP_OK;
    protocol_send_packet(CMD_FW_UPDATE_STOP, resp_payload, 1);
    break;
  }

  case CMD_CALIB_RUN: {
    if (pkt->length < 8) {
      resp_payload[0] = RESP_ERR_PARAM;
      protocol_send_packet(CMD_CALIB_RUN, resp_payload, 1);
      break;
    }
    uint8_t ch_mask = pkt->payload[0];
    uint8_t mode = pkt->payload[1];
    uint16_t t_cell1[7] = {0};
    uint16_t t_pack[7] = {0};
    uint16_t t_bat[7] = {0};

    if (pkt->length >= 2 + (6 * 6)) { // 2 + 36 = 38 bytes payload for per-channel targets
      uint16_t idx = 2;
      for (uint8_t ch = 1; ch <= 6; ch++) {
        t_cell1[ch] = read_u16_be(pkt->payload + idx); idx += 2;
        t_pack[ch] = read_u16_be(pkt->payload + idx); idx += 2;
        t_bat[ch] = read_u16_be(pkt->payload + idx); idx += 2;
      }
    } else {
      uint16_t target_cell1 = read_u16_be(pkt->payload + 2);
      uint16_t target_pack = read_u16_be(pkt->payload + 4);
      uint16_t target_bat = read_u16_be(pkt->payload + 6);
      for (uint8_t ch = 1; ch <= 6; ch++) {
        t_cell1[ch] = target_cell1;
        t_pack[ch] = target_pack;
        t_bat[ch] = target_bat;
      }
    }

    bool ok = calib_engine_start(ch_mask, mode, t_cell1, t_pack, t_bat);
    resp_payload[0] = ok ? RESP_OK : RESP_ERR_BUSY;
    protocol_send_packet(CMD_CALIB_RUN, resp_payload, 1);
    break;
  }

  case CMD_CALIB_STATUS: {
    resp_payload[0] = RESP_OK;
    resp_payload[1] = calib_status.state;
    resp_payload[2] = calib_status.active_channels;
    resp_payload[3] = calib_status.error_channels;
    
    // Fill channel 1..6 results (6 * 29 = 174 bytes)
    uint16_t idx = 4;
    for (uint8_t ch = 1; ch <= 6; ch++) {
      resp_payload[idx++] = calib_status.results[ch].cell1_gain & 0xFF;
      resp_payload[idx++] = (calib_status.results[ch].cell1_gain >> 8) & 0xFF;
      resp_payload[idx++] = calib_status.results[ch].pack_gain & 0xFF;
      resp_payload[idx++] = (calib_status.results[ch].pack_gain >> 8) & 0xFF;
      resp_payload[idx++] = calib_status.results[ch].bat_gain & 0xFF;
      resp_payload[idx++] = (calib_status.results[ch].bat_gain >> 8) & 0xFF;
      resp_payload[idx++] = calib_status.results[ch].success ? 1 : 0;
      resp_payload[idx++] = calib_status.results[ch].raw_cell1_adc & 0xFF;
      resp_payload[idx++] = (calib_status.results[ch].raw_cell1_adc >> 8) & 0xFF;
      resp_payload[idx++] = calib_status.results[ch].raw_pack_adc & 0xFF;
      resp_payload[idx++] = (calib_status.results[ch].raw_pack_adc >> 8) & 0xFF;
      resp_payload[idx++] = calib_status.results[ch].raw_bat_adc & 0xFF;
      resp_payload[idx++] = (calib_status.results[ch].raw_bat_adc >> 8) & 0xFF;
      memcpy(resp_payload + idx, (const void*)calib_status.results[ch].raw_bytes, 18);
      idx += 18;
    }
    protocol_send_packet(CMD_CALIB_STATUS, resp_payload, idx);
    break;
  }

  default: {
    resp_payload[0] = RESP_ERR_UNKNOWN_CMD;
    protocol_send_packet(pkt->cmd, resp_payload, 1);
    break;
  }
  }
}

int main() {
  // Enable system and USB Serial IO
  stdio_init_all();
  stdio_set_translate_crlf(&stdio_usb, false); // Fix binary packet corruption

  // Initialize custom hardware modules
  smbus_init_all();
  relay_init();
  flash_store_init();
  led_init(); // Initialize WS2812 LED

  // Initialize multicore firmware updater
  bq_updater_init();

  rx_packet_t rx_pkt;

  while (true) {
    // Process async tasks
    led_task();
    
    // Read character from USB CDC with 1ms timeout to prevent 100% CPU spinning
    // (reduces heat/power draw)
    int c = getchar_timeout_us(1000);
    if (c != PICO_ERROR_TIMEOUT) {
      if (protocol_parse_byte((uint8_t)c, &rx_pkt)) {
        handle_packet(&rx_pkt);
      }
    }
  }

  return 0;
}
