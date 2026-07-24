#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define PROTOCOL_STX 0x02
#define PROTOCOL_ETX 0x03

#define PROTOCOL_MAX_PAYLOAD 512

// Commands
#define CMD_GET_VERSION      0x01
#define CMD_REBOOT_BOOTSEL   0x02
#define CMD_RELAY_SET        0x10
#define CMD_RELAY_GET        0x11
#define CMD_SMBUS_CMD        0x20
#define CMD_I2C_RAW          0x21
#define CMD_FW_UPLOAD_START  0x30
#define CMD_FW_UPLOAD_DATA   0x31
#define CMD_FW_UPLOAD_END    0x32
#define CMD_FW_GET_FILE_INFO 0x35
#define CMD_FW_UPDATE_RUN    0x40
#define CMD_FW_UPDATE_STATUS 0x41
#define CMD_FW_UPDATE_STOP   0x42
#define CMD_SET_LED_STATE    0x50

// Command execution status response codes
#define RESP_OK              0x00
#define RESP_ERR_CRC         0x01
#define RESP_ERR_UNKNOWN_CMD 0x02
#define RESP_ERR_PARAM       0x03
#define RESP_ERR_HW          0x04
#define RESP_ERR_BUSY        0x05

typedef struct {
    uint8_t cmd;
    uint16_t length;
    uint8_t payload[PROTOCOL_MAX_PAYLOAD];
} rx_packet_t;

// Parses serial input stream byte-by-byte
// Returns true when a complete packet is received and verified
bool protocol_parse_byte(uint8_t byte, rx_packet_t *pkt);

// Send packet via USB CDC
void protocol_send_packet(uint8_t cmd, const uint8_t *payload, uint16_t len);

// Helper for CRC16
uint16_t crc16_calculate(const uint8_t *data, size_t len);

#endif // PROTOCOL_H
