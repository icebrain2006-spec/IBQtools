#include "bq_updater.h"
#include "smbus.h"
#include "flash_store.h"
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include <string.h>
#include <stdlib.h>

volatile update_status_t update_status = {
    .is_running = false,
    .current_line = 0,
    .total_lines = 0,
    .active_channels = 0,
    .error_channels = 0,
    .error_code = 0
};

static uint8_t parse_hex_byte(const char *str) {
    uint8_t val = 0;
    for (int i = 0; i < 2; i++) {
        if (str[i] == '\0') break;
        val <<= 4;
        if (str[i] >= '0' && str[i] <= '9') val |= (str[i] - '0');
        else if (str[i] >= 'A' && str[i] <= 'F') val |= (str[i] - 'A' + 10);
        else if (str[i] >= 'a' && str[i] <= 'f') val |= (str[i] - 'a' + 10);
    }
    return val;
}

static uint32_t get_next_line(uint32_t flash_offset, char *line_buf, uint32_t max_len, uint32_t file_size) {
    if (flash_offset >= file_size) return 0;
    uint32_t idx = 0;
    while (flash_offset < file_size && idx < max_len - 1) {
        uint8_t byte;
        flash_store_read_data(flash_offset++, &byte, 1);
        if (byte == '\n') {
            break;
        }
        if (byte != '\r') {
            line_buf[idx++] = (char)byte;
        }
    }
    line_buf[idx] = '\0';
    return flash_offset;
}

static int tokenize(char *line, char **tokens, int max_tokens) {
    int count = 0;
    char *tok = strtok(line, " \t");
    while (tok != NULL && count < max_tokens) {
        tokens[count++] = tok;
        tok = strtok(NULL, " \t");
    }
    return count;
}

// Core 1 Main Entry
static void core1_entry(void) {
    char line_buf[256];
    char *tokens[64];
    uint8_t i2c_payload[64];

    while (true) {
        // Wait for start signal from Core 0 via FIFO
        uint32_t cmd = multicore_fifo_pop_blocking();
        if (cmd != 0x57415254) continue;

        uint32_t file_size = flash_store_get_size();
        if (file_size == 0) {
            update_status.is_running = false;
            update_status.error_code = -10; // No file uploaded
            continue;
        }

        // Phase 1: Calculate total lines in the file
        uint32_t temp_offset = 0;
        uint32_t lines_count = 0;
        while (temp_offset < file_size) {
            temp_offset = get_next_line(temp_offset, line_buf, sizeof(line_buf), file_size);
            lines_count++;
        }

        update_status.total_lines = lines_count;
        update_status.current_line = 0;
        update_status.error_channels = 0;
        update_status.error_code = 0;
        update_status.is_running = true;

        // Phase 2: Parse and execute SLFS instructions line-by-line
        uint32_t flash_offset = 0;
        while (flash_offset < file_size && update_status.is_running) {
            update_status.current_line++;
            flash_offset = get_next_line(flash_offset, line_buf, sizeof(line_buf), file_size);

            // Skip empty lines or comment lines starting with ';'
            if (line_buf[0] == '\0' || line_buf[0] == ';') {
                continue;
            }

            int num_tokens = tokenize(line_buf, tokens, 64);
            if (num_tokens < 2) continue;

            char cmd_type = tokens[0][0];

            if (cmd_type == 'W' && num_tokens >= 3) {
                // Write command: W: <addr> <reg> <data...>
                uint8_t addr_8bit = parse_hex_byte(tokens[1]);
                uint8_t addr_7bit = addr_8bit >> 1;
                
                uint16_t payload_len = num_tokens - 2;
                if (payload_len > 64) payload_len = 64;

                for (uint16_t i = 0; i < payload_len; i++) {
                    i2c_payload[i] = parse_hex_byte(tokens[2 + i]);
                }

                // Execute write on all active and non-errored channels
                for (uint8_t ch = 1; ch <= 6; ch++) {
                    uint8_t ch_mask = (1 << (ch - 1));
                    if ((update_status.active_channels & ch_mask) && !(update_status.error_channels & ch_mask)) {
                        int err = smbus_i2c_write(ch, addr_7bit, i2c_payload, payload_len);
                        if (err != SMBUS_OK) {
                            update_status.error_channels |= ch_mask;
                        }
                    }
                }
            } 
            else if (cmd_type == 'C' && num_tokens >= 3) {
                // Compare command: C: <addr> <reg> <expected_data...>
                uint8_t addr_8bit = parse_hex_byte(tokens[1]);
                uint8_t addr_7bit = addr_8bit >> 1;
                uint8_t reg = parse_hex_byte(tokens[2]);

                uint16_t expected_len = num_tokens - 3;
                if (expected_len > 64) expected_len = 64;

                uint8_t expected_data[64];
                for (uint16_t i = 0; i < expected_len; i++) {
                    expected_data[i] = parse_hex_byte(tokens[3 + i]);
                }

                // Execute read compare on all active and non-errored channels
                for (uint8_t ch = 1; ch <= 6; ch++) {
                    uint8_t ch_mask = (1 << (ch - 1));
                    if ((update_status.active_channels & ch_mask) && !(update_status.error_channels & ch_mask)) {
                        uint8_t rx_data[64];
                        memset(rx_data, 0, sizeof(rx_data));
                        
                        // Send Register Address first
                        int err = smbus_i2c_write(ch, addr_7bit, &reg, 1);
                        if (err == SMBUS_OK) {
                            // Read expected number of bytes
                            err = smbus_i2c_read(ch, addr_7bit, rx_data, expected_len);
                        }
                        
                        if (err != SMBUS_OK || memcmp(rx_data, expected_data, expected_len) != 0) {
                            update_status.error_channels |= ch_mask;
                        }
                    }
                }
            } 
            else if (cmd_type == 'X' && num_tokens >= 2) {
                // Delay command: X: <ms>
                uint32_t delay_ms = strtoul(tokens[1], NULL, 10);
                sleep_ms(delay_ms);
            }

            // Check if all active channels have errored out
            if ((update_status.active_channels & ~update_status.error_channels) == 0) {
                update_status.error_code = -11; // All target channels failed
                break;
            }
        }

        update_status.is_running = false;
    }
}

void bq_updater_init(void) {
    // Launch Core 1 entry function
    multicore_launch_core1(core1_entry);
}

bool bq_updater_start(uint8_t channel_mask) {
    if (update_status.is_running) return false;
    if (channel_mask == 0) return false;

    update_status.active_channels = channel_mask;
    update_status.error_channels = 0;
    update_status.error_code = 0;

    // Send start command to Core 1
    multicore_fifo_push_blocking(0x57415254);
    return true;
}

void bq_updater_stop(void) {
    if (update_status.is_running) {
        update_status.is_running = false;
    }
}
