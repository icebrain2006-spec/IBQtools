#ifndef SMBUS_H
#define SMBUS_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define SMBUS_NUM_CHANNELS 6
#define SMBUS_TIMEOUT_MS   50

// Error Codes
#define SMBUS_OK            0
#define SMBUS_ERR_TIMEOUT  -1
#define SMBUS_ERR_NACK     -2
#define SMBUS_ERR_PEC      -3
#define SMBUS_ERR_INVALID  -4

// SMBus Channel Pin Definitions
// CH1: GP0 (SDA), GP1 (SCL)
// CH2: GP2 (SDA), GP3 (SCL)
// CH3: GP4 (SDA), GP5 (SCL)
// CH4: GP12 (SDA), GP13 (SCL)
// CH5: GP14 (SDA), GP15 (SCL)
// CH6: GP26 (SDA), GP27 (SCL)
extern const uint8_t SMBUS_SDA_PINS[SMBUS_NUM_CHANNELS];
extern const uint8_t SMBUS_SCL_PINS[SMBUS_NUM_CHANNELS];

// Initialize all 6 SMBus channels using PIO
void smbus_init_all(void);

// SMBus APIs
int smbus_write_byte(uint8_t ch, uint8_t addr, uint8_t cmd, uint8_t val, bool use_pec);
int smbus_read_byte(uint8_t ch, uint8_t addr, uint8_t cmd, uint8_t *val, bool use_pec);

int smbus_write_word(uint8_t ch, uint8_t addr, uint8_t cmd, uint16_t val, bool use_pec);
int smbus_read_word(uint8_t ch, uint8_t addr, uint8_t cmd, uint16_t *val, bool use_pec);

int smbus_write_block(uint8_t ch, uint8_t addr, uint8_t cmd, const uint8_t *data, uint8_t len, bool use_pec);
int smbus_read_block(uint8_t ch, uint8_t addr, uint8_t cmd, uint8_t *data, uint8_t *len, bool use_pec);

// Direct I2C commands for SLFS flashing
int smbus_i2c_write(uint8_t ch, uint8_t addr, const uint8_t *data, uint8_t len);
int smbus_i2c_read(uint8_t ch, uint8_t addr, uint8_t *data, uint8_t len);
int smbus_i2c_write_read(uint8_t ch, uint8_t addr, const uint8_t *tx_data, uint8_t tx_len, uint8_t *rx_data, uint8_t rx_len);

// Helper function to calculate SMBus PEC (CRC-8)
uint8_t smbus_pec_calculate(const uint8_t *data, size_t len);

#endif // SMBUS_H
