/**
 * @file bq_updater.c
 * @brief Core 1 독립 실행형 6채널 동시 BQ IC SLFS 펌웨어 업데이터 구현부
 */

#include "bq_updater.h"
#include "smbus.h"
#include "flash_store.h"
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include <string.h>
#include <stdlib.h>

/// 전역 업데이트 상태 구조체 초기화 (Core 0과 공유)
volatile update_status_t update_status = {
    .state = UPDATER_STATE_IDLE,
    .current_line = 0,
    .total_lines = 0,
    .active_channels = 0,
    .error_channels = 0,
    .error_code = 0,
    .current_delay_ms = 0
};

/**
 * @brief 16진수 문자열 2자리를 1바이트 정수로 파싱하는 헬퍼 함수
 */
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

/**
 * @brief RP2040 플래시 메모리 영역에서 1줄(Line) 단위로 텍스트 명령을 읽어오는 함수
 */
static uint32_t get_next_line(uint32_t flash_offset, char *line_buf, uint32_t max_len, uint32_t file_size) {
    if (flash_offset >= file_size) return 0;
    uint32_t idx = 0;
    const uint8_t *flash_data_ptr = (const uint8_t *)(XIP_BASE + FLASH_SLFS_DATA_OFFSET);
    
    while (flash_offset < file_size && idx < max_len - 1) {
        uint8_t byte = flash_data_ptr[flash_offset++];
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

/**
 * @brief 공백 및 탭 문자를 기준으로 1줄을 토큰으로 분리하는 함수
 */
static int tokenize(char *line, char **tokens, int max_tokens) {
    int count = 0;
    char *tok = strtok(line, " \t");
    while (tok != NULL && count < max_tokens) {
        tokens[count++] = tok;
        tok = strtok(NULL, " \t");
    }
    return count;
}

static char line_buf[512];
static char *tokens[128];
static uint8_t i2c_payload[255];

/**
 * @brief RP2040 Core 1 전용 메인 루프 (SLFS 파일 파싱 및 6채널 동시 쓰기/검증 실행)
 */
static void core1_entry(void) {

    while (true) {
        // Core 0으로부터 신호 수신 대기 (FIFO 키 값: 0x57415254 = 'WART')
        uint32_t cmd = multicore_fifo_pop_blocking();
        if (cmd != 0x57415254) continue;

        uint32_t file_size = flash_store_get_size();
        if (file_size == 0) {
            update_status.state = UPDATER_STATE_ERROR;
            update_status.error_code = -10; // 업로드된 SLFS 파일 없음
            continue;
        }

        // Phase 1: 전체 SLFS 파일의 총 라인 수 산출
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
        update_status.state = UPDATER_STATE_RUNNING;

        // Phase 2: SLFS 스크립트를 한 줄씩 읽어 실행
        uint32_t flash_offset = 0;
        while (flash_offset < file_size && (update_status.state == UPDATER_STATE_RUNNING || update_status.state == UPDATER_STATE_DELAYING)) {
            update_status.current_line++;
            flash_offset = get_next_line(flash_offset, line_buf, sizeof(line_buf), file_size);

            // 빈 줄 및 주석(';') 제거
            if (line_buf[0] == '\0' || line_buf[0] == ';') {
                continue;
            }

            int num_tokens = tokenize(line_buf, tokens, 128);
            if (num_tokens < 2) continue;

            char cmd_type = tokens[0][0];

            if (cmd_type == 'W' && num_tokens >= 3) {
                // 쓰기 명령 (W: <addr> <reg> <data...>)
                uint8_t addr_8bit = parse_hex_byte(tokens[1]);
                uint8_t addr_7bit = addr_8bit >> 1;
                
                uint16_t payload_len = num_tokens - 2;
                if (payload_len > 255) payload_len = 255;

                for (uint16_t i = 0; i < payload_len; i++) {
                    i2c_payload[i] = parse_hex_byte(tokens[2 + i]);
                }

                // 활성화된 채널들에 대해 I2C 쓰기 수행 (플래시 소거를 고려하여 최대 500회 1초 재시도)
                for (uint8_t ch = 1; ch <= 6; ch++) {
                    uint8_t ch_mask = (1 << (ch - 1));
                    if ((update_status.active_channels & ch_mask) && !(update_status.error_channels & ch_mask)) {
                        int err = SMBUS_ERR_TIMEOUT;
                        int retries = 500; // 느린 플래시 소거 대기 (최대 1000ms)
                        do {
                            err = smbus_i2c_write(ch, addr_7bit, i2c_payload, payload_len);
                            if (err == SMBUS_OK) break;
                            sleep_ms(2); // 재시도 전 2ms 대기
                            retries--;
                        } while (retries > 0);
                        
                        if (err != SMBUS_OK) {
                            update_status.error_channels |= ch_mask;
                        }
                    }
                }
            } 
            else if (cmd_type == 'C' && num_tokens >= 3) {
                // 검증 명령 (C: <addr> <reg> <expected_data...>)
                uint8_t addr_8bit = parse_hex_byte(tokens[1]);
                uint8_t addr_7bit = addr_8bit >> 1;
                uint8_t reg = parse_hex_byte(tokens[2]);

                uint16_t expected_len = num_tokens - 3;
                if (expected_len > 128) expected_len = 128;

                uint8_t expected_data[128];
                for (uint16_t i = 0; i < expected_len; i++) {
                    expected_data[i] = parse_hex_byte(tokens[3 + i]);
                }

                // 활성화된 채널들에 대해 읽기 및 기대값 비교 수행
                for (uint8_t ch = 1; ch <= 6; ch++) {
                    uint8_t ch_mask = (1 << (ch - 1));
                    if ((update_status.active_channels & ch_mask) && !(update_status.error_channels & ch_mask)) {
                        uint8_t rx_data[128];
                        memset(rx_data, 0, sizeof(rx_data));
                        
                        int err = SMBUS_ERR_TIMEOUT;
                        bool match = false;
                        int retries = 1000; // 최대 2초 재시도
                        
                        do {
                            // 레지스터 주소 전송 후 데이터 읽기 (Repeated Start 적용)
                            err = smbus_i2c_write_read(ch, addr_7bit, &reg, 1, rx_data, expected_len);
                            
                            if (err == SMBUS_OK) {
                                match = true;
                                for (uint16_t i = 0; i < expected_len; i++) {
                                    if (rx_data[i] != expected_data[i]) {
                                        // 마지막 바이트 예외 처리 (PEC 허용)
                                        if (i == expected_len - 1) {
                                            if (rx_data[i] == 0xFF) continue; // PEC 누락 허용
                                            
                                            // Read-Only PEC 계산 검증 (0x67 등)
                                            uint8_t crc = 0;
                                            uint8_t addr_r = (addr_7bit << 1) | 0x01;
                                            crc ^= addr_r;
                                            for (int j=0; j<8; j++) crc = (crc & 0x80) ? (crc << 1) ^ 0x07 : (crc << 1);
                                            for (uint16_t k=0; k < expected_len - 1; k++) {
                                                crc ^= rx_data[k];
                                                for (int j=0; j<8; j++) crc = (crc & 0x80) ? (crc << 1) ^ 0x07 : (crc << 1);
                                            }
                                            if (rx_data[i] == crc) continue;
                                        }
                                        match = false;
                                        break;
                                    }
                                }
                                
                                if (match) break;
                            }
                            
                            sleep_ms(2);
                            retries--;
                        } while (retries > 0);
                        
                        if (err != SMBUS_OK) {
                            update_status.error_channels |= ch_mask;
                        }
                    }
                }
            } 
            else if (cmd_type == 'X' && num_tokens >= 2) {
                // 지연 명령 (X: <ms>)
                uint32_t delay_ms = strtoul(tokens[1], NULL, 10);
                update_status.state = UPDATER_STATE_DELAYING;
                update_status.current_delay_ms = delay_ms;
                sleep_ms(delay_ms);
                if (update_status.state == UPDATER_STATE_DELAYING) {
                    update_status.state = UPDATER_STATE_RUNNING;
                }
            }

            // 모든 대상 채널이 실패했는지 점검
            if ((update_status.active_channels & ~update_status.error_channels) == 0) {
                update_status.error_code = -11; // 전체 채널 실패
                update_status.state = UPDATER_STATE_ERROR;
                break;
            }
        }

        if (update_status.state == UPDATER_STATE_RUNNING) {
            update_status.state = UPDATER_STATE_DONE;
        }
    }
}

/**
 * @brief 업데이터 초기화 (Core 1 엔트리 포인트 실행)
 */
void bq_updater_init(void) {
    multicore_launch_core1(core1_entry);
}

/**
 * @brief BQ 펌웨어 업데이터 시작
 */
bool bq_updater_start(uint8_t channel_mask) {
    if (update_status.state == UPDATER_STATE_RUNNING || update_status.state == UPDATER_STATE_DELAYING) return false;
    if (channel_mask == 0) return false;

    update_status.active_channels = channel_mask;
    update_status.error_channels = 0;
    update_status.error_code = 0;
    update_status.state = UPDATER_STATE_RUNNING;

    // Core 1로 작업 시작 명령(FIFO) 송신
    multicore_fifo_push_blocking(0x57415254);
    return true;
}

/**
 * @brief BQ 펌웨어 업데이터 정지
 */
void bq_updater_stop(void) {
    if (update_status.state == UPDATER_STATE_RUNNING || update_status.state == UPDATER_STATE_DELAYING) {
        update_status.state = UPDATER_STATE_IDLE;
    }
}
