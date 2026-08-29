#include "protocol.h"
#include "pico/stdlib.h"
#include <stdio.h>
#include <string.h>

typedef enum {
    STATE_STX,
    STATE_LEN_H,
    STATE_LEN_L,
    STATE_CMD,
    STATE_PAYLOAD,
    STATE_CRC_H,
    STATE_CRC_L,
    STATE_ETX
} rx_state_t;

static rx_state_t rx_state = STATE_STX;
static uint16_t rx_len = 0;
static uint16_t rx_idx = 0;
static uint8_t rx_cmd = 0;
static uint8_t rx_buf[PROTOCOL_MAX_PAYLOAD];
static uint16_t rx_crc = 0;

uint16_t crc16_calculate(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

bool protocol_parse_byte(uint8_t byte, rx_packet_t *pkt) {
    switch (rx_state) {
        case STATE_STX:
            if (byte == PROTOCOL_STX) {
                rx_state = STATE_LEN_H;
                rx_len = 0;
                rx_idx = 0;
                rx_crc = 0;
            }
            break;
            
        case STATE_LEN_H:
            rx_len = (uint16_t)byte << 8;
            rx_state = STATE_LEN_L;
            break;
            
        case STATE_LEN_L:
            rx_len |= byte;
            if (rx_len > PROTOCOL_MAX_PAYLOAD || rx_len == 0) {
                // Invalid length, reset parser
                rx_state = STATE_STX;
            } else {
                rx_state = STATE_CMD;
            }
            break;
            
        case STATE_CMD:
            rx_cmd = byte;
            rx_idx = 0;
            if (rx_len == 1) { // Only command, no payload
                rx_state = STATE_CRC_H;
            } else {
                rx_state = STATE_PAYLOAD;
            }
            break;
            
        case STATE_PAYLOAD:
            rx_buf[rx_idx++] = byte;
            if (rx_idx == rx_len - 1) { // Payload complete (length includes command byte)
                rx_state = STATE_CRC_H;
            }
            break;
            
        case STATE_CRC_H:
            rx_crc = (uint16_t)byte << 8;
            rx_state = STATE_CRC_L;
            break;
            
        case STATE_CRC_L:
            rx_crc |= byte;
            rx_state = STATE_ETX;
            break;
            
        case STATE_ETX:
            rx_state = STATE_STX;
            if (byte == PROTOCOL_ETX) {
                // Verify CRC16 (CRC is calculated over Cmd + Payload)
                uint8_t crc_data[PROTOCOL_MAX_PAYLOAD + 1];
                crc_data[0] = rx_cmd;
                if (rx_len > 1) {
                    memcpy(crc_data + 1, rx_buf, rx_len - 1);
                }
                uint16_t computed_crc = crc16_calculate(crc_data, rx_len);
                
                if (computed_crc == rx_crc) {
                    pkt->cmd = rx_cmd;
                    pkt->length = rx_len;
                    if (rx_len > 1) {
                        memcpy(pkt->payload, rx_buf, rx_len - 1);
                    }
                    return true;
                }
            }
            break;
    }
    return false;
}

void protocol_send_packet(uint8_t cmd, const uint8_t *payload, uint16_t len) {
    if (len > PROTOCOL_MAX_PAYLOAD) return;
    
    uint16_t total_len = len + 1; // cmd + payload
    uint8_t header[4];
    header[0] = PROTOCOL_STX;
    header[1] = (total_len >> 8) & 0xFF;
    header[2] = total_len & 0xFF;
    header[3] = cmd;
    
    // Calculate CRC (Cmd + Payload)
    uint8_t crc_data[PROTOCOL_MAX_PAYLOAD + 1];
    crc_data[0] = cmd;
    if (len > 0) {
        memcpy(crc_data + 1, payload, len);
    }
    uint16_t crc = crc16_calculate(crc_data, total_len);
    
    uint8_t footer[3];
    footer[0] = (crc >> 8) & 0xFF;
    footer[1] = crc & 0xFF;
    footer[2] = PROTOCOL_ETX;
    
    // Write packet to stdout (mapped to USB Serial)
    fwrite(header, 1, 4, stdout);
    if (len > 0) {
        fwrite(payload, 1, len, stdout);
    }
    fwrite(footer, 1, 3, stdout);
    
    // Flush stdout to send packet immediately
    fflush(stdout);
}
