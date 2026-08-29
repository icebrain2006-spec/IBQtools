#include "smbus.h"
#include "pico/stdlib.h"
#include "hardware/gpio.h"

// Hardware Pin mapping based on schematic
const uint8_t SMBUS_SDA_PINS[SMBUS_NUM_CHANNELS] = {0, 2, 4, 12, 14, 26};
const uint8_t SMBUS_SCL_PINS[SMBUS_NUM_CHANNELS] = {1, 3, 5, 13, 15, 27};

#define I2C_DELAY_US 4 // 4us delay produces approx 83kHz (Safely under 100kHz limit)

// Helper to set SDA state (Open-Drain)
static void i2c_set_sda(uint8_t sda, bool high) {
    if (high) {
        gpio_set_dir(sda, GPIO_IN); // High-Z, let pull-up do the work
    } else {
        gpio_put(sda, 0);
        gpio_set_dir(sda, GPIO_OUT); // Drive low
    }
}

// Helper to set SCL state (Open-Drain) and handle clock stretching
static bool i2c_set_scl(uint8_t scl, bool high) {
    if (high) {
        gpio_set_dir(scl, GPIO_IN); // High-Z
        // Wait for clock stretching and RC rise time
        uint32_t start = to_ms_since_boot(get_absolute_time());
        while (!gpio_get(scl)) {
            if (to_ms_since_boot(get_absolute_time()) - start > SMBUS_TIMEOUT_MS) {
                return false; // Timeout
            }
            tight_loop_contents();
        }
    } else {
        gpio_put(scl, 0);
        gpio_set_dir(scl, GPIO_OUT); // Drive low
    }
    return true;
}

// Cycle-accurate delay for Bit-Banging (Avoids SDK sleep_us timer overhead/bugs)
static inline void i2c_delay_us(uint32_t us) {
    busy_wait_us_32(us);
}

static bool i2c_get_sda(uint8_t sda) {
    return gpio_get(sda);
}

// Ensure bus is idle before start
static void i2c_start(uint8_t sda, uint8_t scl) {
    i2c_set_sda(sda, true);
    i2c_set_scl(scl, true);
    i2c_delay_us(I2C_DELAY_US * 2); // Wait for bus idle state to settle
    
    // Start condition: SDA goes low while SCL is high
    i2c_set_sda(sda, false); 
    i2c_delay_us(I2C_DELAY_US); // Hold start condition
    
    // Drop SCL to prepare for first data bit
    i2c_set_scl(scl, false);
    i2c_delay_us(I2C_DELAY_US);
}

// Repeated Start Condition: Called when SCL is already LOW.
// Ensures Repeated start setup time t_SU(START) > 4.7us is met.
static bool i2c_rep_start(uint8_t sda, uint8_t scl) {
    // Ensure SCL is low and release SDA to High
    i2c_set_sda(sda, true);
    
    // Wait for the slave to release SDA (clock/data stretching)
    uint32_t start = to_ms_since_boot(get_absolute_time());
    while (!i2c_get_sda(sda)) {
        if (to_ms_since_boot(get_absolute_time()) - start > SMBUS_TIMEOUT_MS) {
            return false; // Timeout waiting for SDA release
        }
        tight_loop_contents();
    }
    i2c_delay_us(I2C_DELAY_US);
    
    // Raise SCL to HIGH
    if (!i2c_set_scl(scl, true)) return false;
    
    // Explicitly wait for t_SU(START) (Repeated Start Setup Time) -> 5us to 10us
    i2c_delay_us(8); // Guaranteed 8us setup margin
    
    // Pull SDA LOW while SCL is HIGH (Repeated Start Trigger)
    i2c_set_sda(sda, false);
    i2c_delay_us(I2C_DELAY_US);
    
    // Drop SCL LOW to complete Repeated Start
    i2c_set_scl(scl, false);
    i2c_delay_us(I2C_DELAY_US);
    return true;
}

static void i2c_stop(uint8_t sda, uint8_t scl) {
    // SCL should be low before preparing stop
    i2c_set_sda(sda, false);
    i2c_delay_us(I2C_DELAY_US);
    
    // Raise SCL
    i2c_set_scl(scl, true);
    i2c_delay_us(I2C_DELAY_US);
    
    // Stop condition: SDA goes high while SCL is high
    i2c_set_sda(sda, true);
    i2c_delay_us(I2C_DELAY_US * 2); // Ensure bus is seen as idle
}

static int i2c_tx_byte(uint8_t sda, uint8_t scl, uint8_t byte) {
    // Write 8 bits
    for (int i = 7; i >= 0; i--) {
        // SCL is LOW here. Give a small delay to ensure SCL has fully fallen.
        i2c_delay_us(I2C_DELAY_US);
        
        // Change SDA.
        i2c_set_sda(sda, (byte >> i) & 1);
        
        // Generous Setup Time: Wait for SDA RC rise time to fully charge to High.
        i2c_delay_us(I2C_DELAY_US); 
        
        // Raise SCL for slave to sample.
        if (!i2c_set_scl(scl, true)) return SMBUS_ERR_TIMEOUT;
        
        // Generous Hold Time: Keep SCL high long enough for safe sampling.
        i2c_delay_us(I2C_DELAY_US); 
        
        // Drop SCL.
        i2c_set_scl(scl, false);
    }
    
    // Read ACK from slave
    i2c_delay_us(I2C_DELAY_US);
    i2c_set_sda(sda, true); // Release SDA
    i2c_delay_us(I2C_DELAY_US); // Setup time for slave to pull SDA low
    
    if (!i2c_set_scl(scl, true)) return SMBUS_ERR_TIMEOUT;
    i2c_delay_us(I2C_DELAY_US / 2); // Sample at middle of high pulse
    bool nack = i2c_get_sda(sda);
    i2c_delay_us(I2C_DELAY_US / 2);
    
    i2c_set_scl(scl, false);
    i2c_delay_us(I2C_DELAY_US); // Prepare next operation
    
    return nack ? SMBUS_ERR_NACK : SMBUS_OK;
}

static int i2c_rx_byte(uint8_t sda, uint8_t scl, uint8_t *byte, bool send_nack) {
    uint8_t data = 0;
    
    i2c_delay_us(5);
    i2c_set_sda(sda, true); // Release SDA to read
    
    // Read 8 bits
    for (int i = 7; i >= 0; i--) {
        i2c_delay_us(I2C_DELAY_US); // Setup time for slave to pull SDA
        
        if (!i2c_set_scl(scl, true)) return SMBUS_ERR_TIMEOUT;
        i2c_delay_us(I2C_DELAY_US / 2); // Sample at middle of high pulse
        if (i2c_get_sda(sda)) {
            data |= (1 << i);
        }
        i2c_delay_us(I2C_DELAY_US / 2);
        
        i2c_set_scl(scl, false);
    }
    
    // Send ACK/NACK
    i2c_delay_us(5);
    i2c_set_sda(sda, send_nack); // NACK=true (High), ACK=false (Low)
    i2c_delay_us(I2C_DELAY_US); // Setup time for master ACK/NACK
    
    if (!i2c_set_scl(scl, true)) return SMBUS_ERR_TIMEOUT;
    i2c_delay_us(I2C_DELAY_US);
    
    i2c_set_scl(scl, false);
    i2c_delay_us(I2C_DELAY_US); // Prepare next operation
    
    *byte = data;
    return SMBUS_OK;
}

// PEC CRC-8 (x^8 + x^2 + x^1 + 1)
uint8_t smbus_pec_calculate(const uint8_t *data, size_t len) {
    uint8_t crc = 0;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 0x80) {
                crc = (crc << 1) ^ 0x07;
            } else {
                crc <<= 1;
            }
        }
    }
    return crc;
}

void smbus_init_all(void) {
    for (int i = 0; i < SMBUS_NUM_CHANNELS; i++) {
        uint sda = SMBUS_SDA_PINS[i];
        uint scl = SMBUS_SCL_PINS[i];
        
        gpio_init(sda);
        gpio_init(scl);
        
        // Explicitly set output latch to 0 so when direction is OUT, it pulls LOW immediately.
        gpio_put(sda, 0);
        gpio_put(scl, 0);
        
        gpio_pull_up(sda); // Internal pull-up as fallback
        gpio_pull_up(scl); // Internal pull-up as fallback
        
        // Initial state: released (High-Z / Open-Drain High)
        i2c_set_sda(sda, true);
        i2c_set_scl(scl, true);
    }
}

// SMBus Byte Write
int smbus_write_byte(uint8_t ch, uint8_t addr, uint8_t cmd, uint8_t val, bool use_pec) {
    if (ch < 1 || ch > 6) return SMBUS_ERR_INVALID;
    uint8_t idx = ch - 1;
    uint sda = SMBUS_SDA_PINS[idx];
    uint scl = SMBUS_SCL_PINS[idx];
    uint8_t addr_w = (addr << 1);
    int err;

    i2c_start(sda, scl);

    if ((err = i2c_tx_byte(sda, scl, addr_w)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, cmd)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, val)) != SMBUS_OK) goto error;

    if (use_pec) {
        uint8_t buf[3] = {addr_w, cmd, val};
        uint8_t pec = smbus_pec_calculate(buf, 3);
        if ((err = i2c_tx_byte(sda, scl, pec)) != SMBUS_OK) goto error;
    }

    i2c_stop(sda, scl);
    return SMBUS_OK;

error:
    i2c_stop(sda, scl);
    return err;
}

// SMBus Byte Read
int smbus_read_byte(uint8_t ch, uint8_t addr, uint8_t cmd, uint8_t *val, bool use_pec) {
    if (ch < 1 || ch > 6) return SMBUS_ERR_INVALID;
    uint8_t idx = ch - 1;
    uint sda = SMBUS_SDA_PINS[idx];
    uint scl = SMBUS_SCL_PINS[idx];
    uint8_t addr_w = (addr << 1);
    uint8_t addr_r = (addr << 1) | 0x01;
    int err;

    i2c_start(sda, scl);

    if ((err = i2c_tx_byte(sda, scl, addr_w)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, cmd)) != SMBUS_OK) goto error;

    if (!i2c_rep_start(sda, scl)) { err = SMBUS_ERR_TIMEOUT; goto error; }

    if ((err = i2c_tx_byte(sda, scl, addr_r)) != SMBUS_OK) goto error;

    if (use_pec) {
        if ((err = i2c_rx_byte(sda, scl, val, false)) != SMBUS_OK) goto error; // send ACK
        uint8_t pec_rx;
        if ((err = i2c_rx_byte(sda, scl, &pec_rx, true)) != SMBUS_OK) goto error; // send NACK
        
        uint8_t buf[4] = {addr_w, cmd, addr_r, *val};
        uint8_t pec_calc = smbus_pec_calculate(buf, 4);
        if (pec_rx != pec_calc) {
            err = SMBUS_ERR_PEC;
            goto error;
        }
    } else {
        if ((err = i2c_rx_byte(sda, scl, val, true)) != SMBUS_OK) goto error; // send NACK
    }

    i2c_stop(sda, scl);
    return SMBUS_OK;

error:
    i2c_stop(sda, scl);
    return err;
}

// SMBus Word Write
int smbus_write_word(uint8_t ch, uint8_t addr, uint8_t cmd, uint16_t val, bool use_pec) {
    if (ch < 1 || ch > 6) return SMBUS_ERR_INVALID;
    uint8_t idx = ch - 1;
    uint sda = SMBUS_SDA_PINS[idx];
    uint scl = SMBUS_SCL_PINS[idx];
    uint8_t addr_w = (addr << 1);
    uint8_t low_byte = val & 0xFF;
    uint8_t high_byte = (val >> 8) & 0xFF;
    int err;

    i2c_start(sda, scl);

    if ((err = i2c_tx_byte(sda, scl, addr_w)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, cmd)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, low_byte)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, high_byte)) != SMBUS_OK) goto error;

    if (use_pec) {
        uint8_t buf[4] = {addr_w, cmd, low_byte, high_byte};
        uint8_t pec = smbus_pec_calculate(buf, 4);
        if ((err = i2c_tx_byte(sda, scl, pec)) != SMBUS_OK) goto error;
    }

    i2c_stop(sda, scl);
    return SMBUS_OK;

error:
    i2c_stop(sda, scl);
    return err;
}

// SMBus Word Read
int smbus_read_word(uint8_t ch, uint8_t addr, uint8_t cmd, uint16_t *val, bool use_pec) {
    if (ch < 1 || ch > 6) return SMBUS_ERR_INVALID;
    uint8_t idx = ch - 1;
    uint sda = SMBUS_SDA_PINS[idx];
    uint scl = SMBUS_SCL_PINS[idx];
    uint8_t addr_w = (addr << 1);
    uint8_t addr_r = (addr << 1) | 0x01;
    uint8_t low_byte, high_byte;
    int err;

    i2c_start(sda, scl);

    if ((err = i2c_tx_byte(sda, scl, addr_w)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, cmd)) != SMBUS_OK) goto error;

    if (!i2c_rep_start(sda, scl)) { err = SMBUS_ERR_TIMEOUT; goto error; }

    if ((err = i2c_tx_byte(sda, scl, addr_r)) != SMBUS_OK) goto error;

    if (use_pec) {
        if ((err = i2c_rx_byte(sda, scl, &low_byte, false)) != SMBUS_OK) goto error; // ACK
        if ((err = i2c_rx_byte(sda, scl, &high_byte, false)) != SMBUS_OK) goto error; // ACK
        
        uint8_t pec_rx;
        if ((err = i2c_rx_byte(sda, scl, &pec_rx, true)) != SMBUS_OK) goto error; // NACK
        
        uint8_t buf[5] = {addr_w, cmd, addr_r, low_byte, high_byte};
        uint8_t pec_calc = smbus_pec_calculate(buf, 5);
        if (pec_rx != pec_calc) {
            err = SMBUS_ERR_PEC;
            goto error;
        }
    } else {
        if ((err = i2c_rx_byte(sda, scl, &low_byte, false)) != SMBUS_OK) goto error; // ACK
        if ((err = i2c_rx_byte(sda, scl, &high_byte, true)) != SMBUS_OK) goto error; // NACK
    }

    *val = (uint16_t)low_byte | ((uint16_t)high_byte << 8);
    i2c_stop(sda, scl);
    return SMBUS_OK;

error:
    i2c_stop(sda, scl);
    return err;
}

// SMBus Block Write
int smbus_write_block(uint8_t ch, uint8_t addr, uint8_t cmd, const uint8_t *data, uint8_t len, bool use_pec) {
    if (ch < 1 || ch > 6) return SMBUS_ERR_INVALID;
    if (len > 40) return SMBUS_ERR_INVALID;
    uint8_t idx = ch - 1;
    uint sda = SMBUS_SDA_PINS[idx];
    uint scl = SMBUS_SCL_PINS[idx];
    uint8_t addr_w = (addr << 1);
    int err;

    i2c_start(sda, scl);

    if ((err = i2c_tx_byte(sda, scl, addr_w)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, cmd)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, len)) != SMBUS_OK) goto error;

    for (uint8_t i = 0; i < len; i++) {
        if ((err = i2c_tx_byte(sda, scl, data[i])) != SMBUS_OK) goto error;
    }

    if (use_pec) {
        uint8_t pec_buf[36];
        pec_buf[0] = addr_w;
        pec_buf[1] = cmd;
        pec_buf[2] = len;
        for (uint8_t i = 0; i < len; i++) {
            pec_buf[3 + i] = data[i];
        }
        uint8_t pec = smbus_pec_calculate(pec_buf, 3 + len);
        if ((err = i2c_tx_byte(sda, scl, pec)) != SMBUS_OK) goto error;
    }

    i2c_stop(sda, scl);
    return SMBUS_OK;

error:
    i2c_stop(sda, scl);
    return err;
}

// SMBus Block Read
int smbus_read_block(uint8_t ch, uint8_t addr, uint8_t cmd, uint8_t *data, uint8_t *len, bool use_pec) {
    if (ch < 1 || ch > 6) return SMBUS_ERR_INVALID;
    uint8_t idx = ch - 1;
    uint sda = SMBUS_SDA_PINS[idx];
    uint scl = SMBUS_SCL_PINS[idx];
    uint8_t addr_w = (addr << 1);
    uint8_t addr_r = (addr << 1) | 0x01;
    uint8_t rx_len;
    int err;

    i2c_start(sda, scl);

    if ((err = i2c_tx_byte(sda, scl, addr_w)) != SMBUS_OK) goto error;
    if ((err = i2c_tx_byte(sda, scl, cmd)) != SMBUS_OK) goto error;

    if (!i2c_rep_start(sda, scl)) { err = SMBUS_ERR_TIMEOUT; goto error; }

    if ((err = i2c_tx_byte(sda, scl, addr_r)) != SMBUS_OK) goto error;

    // 1. Read SMBus Block Length byte
    // [참고] 이 Length 바이트(Byte 0)는 *len 변수로 분리되며, 
    // 실제 반환되는 data[] 배열에는 포함되지 않고 제외됩니다.
    if ((err = i2c_rx_byte(sda, scl, &rx_len, false)) != SMBUS_OK) goto error; // ACK
    if (rx_len > 36 || rx_len == 0) {
        err = -rx_len; // Return -rx_len to debug what BQ40Z50 is actually sending!
        if (err == 0) err = SMBUS_ERR_INVALID; // if 0, return -4
        goto error;
    }

    for (uint8_t i = 0; i < rx_len; i++) {
        bool is_last = (i == rx_len - 1);
        bool send_nack = is_last && !use_pec;
        if ((err = i2c_rx_byte(sda, scl, &data[i], send_nack)) != SMBUS_OK) goto error;
    }

    if (use_pec) {
        uint8_t pec_rx;
        if ((err = i2c_rx_byte(sda, scl, &pec_rx, true)) != SMBUS_OK) goto error; // NACK
        
        uint8_t pec_buf[64];
        pec_buf[0] = addr_w;
        pec_buf[1] = cmd;
        pec_buf[2] = addr_r;
        pec_buf[3] = rx_len;
        for (uint8_t i = 0; i < rx_len; i++) {
            pec_buf[4 + i] = data[i];
        }
        uint8_t pec_calc = smbus_pec_calculate(pec_buf, 4 + rx_len);
        if (pec_rx != pec_calc) {
            err = SMBUS_ERR_PEC;
            goto error;
        }
    }

    *len = rx_len;
    i2c_stop(sda, scl);
    return SMBUS_OK;

error:
    i2c_stop(sda, scl);
    return err;
}

// Raw I2C Write for Flash Stream flashing
int smbus_i2c_write(uint8_t ch, uint8_t addr, const uint8_t *data, uint8_t len) {
    if (ch < 1 || ch > 6) return SMBUS_ERR_INVALID;
    uint8_t idx = ch - 1;
    uint sda = SMBUS_SDA_PINS[idx];
    uint scl = SMBUS_SCL_PINS[idx];
    uint8_t addr_w = (addr << 1);
    int err;

    i2c_start(sda, scl);

    if ((err = i2c_tx_byte(sda, scl, addr_w)) != SMBUS_OK) goto error;

    for (uint8_t i = 0; i < len; i++) {
        if ((err = i2c_tx_byte(sda, scl, data[i])) != SMBUS_OK) goto error;
    }

    i2c_stop(sda, scl);
    return SMBUS_OK;

error:
    i2c_stop(sda, scl);
    return err;
}

// Raw I2C Read for Flash Stream flashing
int smbus_i2c_read(uint8_t ch, uint8_t addr, uint8_t *data, uint8_t len) {
    if (ch < 1 || ch > 6) return SMBUS_ERR_INVALID;
    uint8_t idx = ch - 1;
    uint sda = SMBUS_SDA_PINS[idx];
    uint scl = SMBUS_SCL_PINS[idx];
    uint8_t addr_r = (addr << 1) | 0x01;
    int err;

    i2c_start(sda, scl);

    if ((err = i2c_tx_byte(sda, scl, addr_r)) != SMBUS_OK) goto error;

    for (uint8_t i = 0; i < len; i++) {
        bool send_nack = (i == len - 1);
        if ((err = i2c_rx_byte(sda, scl, &data[i], send_nack)) != SMBUS_OK) goto error;
    }

    i2c_stop(sda, scl);
    return SMBUS_OK;

error:
    i2c_stop(sda, scl);
    return err;
}

// Raw I2C Write then Read (Repeated Start) for Flash Stream flashing
int smbus_i2c_write_read(uint8_t ch, uint8_t addr, const uint8_t *tx_data, uint8_t tx_len, uint8_t *rx_data, uint8_t rx_len) {
    if (ch < 1 || ch > 6) return SMBUS_ERR_INVALID;
    uint8_t idx = ch - 1;
    uint sda = SMBUS_SDA_PINS[idx];
    uint scl = SMBUS_SCL_PINS[idx];
    uint8_t addr_w = (addr << 1);
    uint8_t addr_r = (addr << 1) | 0x01;
    int err;

    // 1. Write Phase
    i2c_start(sda, scl);
    if ((err = i2c_tx_byte(sda, scl, addr_w)) != SMBUS_OK) goto error;
    
    for (uint8_t i = 0; i < tx_len; i++) {
        if ((err = i2c_tx_byte(sda, scl, tx_data[i])) != SMBUS_OK) goto error;
    }

    // 2. Read Phase (Repeated Start)
    if (!i2c_rep_start(sda, scl)) {
        err = SMBUS_ERR_TIMEOUT;
        goto error;
    }
    
    if ((err = i2c_tx_byte(sda, scl, addr_r)) != SMBUS_OK) goto error;

    for (uint8_t i = 0; i < rx_len; i++) {
        bool send_nack = (i == rx_len - 1);
        if ((err = i2c_rx_byte(sda, scl, &rx_data[i], send_nack)) != SMBUS_OK) goto error;
    }

    i2c_stop(sda, scl);
    return SMBUS_OK;

error:
    i2c_stop(sda, scl);
    return err;
}
