/**
 * @file smbus.h
 * @brief RP2040 PIO 기반 6채널 SMBus / I2C 통신 드라이버 헤더
 */

#ifndef SMBUS_H
#define SMBUS_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/// 지원되는 SMBus 채널 수 (CH1 ~ CH6)
#define SMBUS_NUM_CHANNELS 6
/// SMBus 통신 타임아웃 제한 (기본값: 50ms)
#define SMBUS_TIMEOUT_MS   50

// 에러 코드 정의
#define SMBUS_OK            0  ///< 정상 처리 완료
#define SMBUS_ERR_TIMEOUT  -1  ///< 통신 타임아웃 발생 (50ms 초과)
#define SMBUS_ERR_NACK     -2  ///< 슬레이브 장치로부터 NACK 응답 수신
#define SMBUS_ERR_PEC      -3  ///< PEC (CRC-8) 오류 발생
#define SMBUS_ERR_INVALID  -4  ///< 유효하지 않은 채널 번호 또는 파라미터

// SMBus 채널별 GPIO 핀 맵 정의
// CH1: GP0 (SDA), GP1 (SCL)
// CH2: GP2 (SDA), GP3 (SCL)
// CH3: GP4 (SDA), GP5 (SCL)
// CH4: GP12 (SDA), GP13 (SCL)
// CH5: GP14 (SDA), GP15 (SCL)
// CH6: GP26 (SDA), GP27 (SCL)
extern const uint8_t SMBUS_SDA_PINS[SMBUS_NUM_CHANNELS];
extern const uint8_t SMBUS_SCL_PINS[SMBUS_NUM_CHANNELS];

/**
 * @brief PIO0, PIO1을 사용하여 6개 SMBus 채널 전체 초기화
 */
void smbus_init_all(void);

// SMBus 기본 API
/**
 * @brief SMBus 1바이트 쓰기 (Write Byte 프로토콜)
 * @param ch 채널 번호 (0 ~ 5)
 * @param addr I2C 7비트 슬레이브 주소
 * @param cmd 명령 레지스터 주소
 * @param val 전송할 1바이트 값
 * @param use_pec PEC(CRC-8) 전송 여부
 * @return 0: 성공, 음수: 에러 코드
 */
int smbus_write_byte(uint8_t ch, uint8_t addr, uint8_t cmd, uint8_t val, bool use_pec);

/**
 * @brief SMBus 1바이트 읽기 (Read Byte 프로토콜)
 * @param ch 채널 번호 (0 ~ 5)
 * @param addr I2C 7비트 슬레이브 주소
 * @param cmd 명령 레지스터 주소
 * @param val 읽어온 1바이트 저장 변수 포인터
 * @param use_pec PEC(CRC-8) 검증 여부
 * @return 0: 성공, 음수: 에러 코드
 */
int smbus_read_byte(uint8_t ch, uint8_t addr, uint8_t cmd, uint8_t *val, bool use_pec);

/**
 * @brief SMBus 2바이트(Word) 쓰기 (Write Word 프로토콜)
 * @param ch 채널 번호 (0 ~ 5)
 * @param addr I2C 7비트 슬레이브 주소
 * @param cmd 명령 레지스터 주소
 * @param val 전송할 16비트 Word 값 (Little-Endian)
 * @param use_pec PEC(CRC-8) 전송 여부
 * @return 0: 성공, 음수: 에러 코드
 */
int smbus_write_word(uint8_t ch, uint8_t addr, uint8_t cmd, uint16_t val, bool use_pec);

/**
 * @brief SMBus 2바이트(Word) 읽기 (Read Word 프로토콜)
 * @param ch 채널 번호 (0 ~ 5)
 * @param addr I2C 7비트 슬레이브 주소
 * @param cmd 명령 레지스터 주소
 * @param val 읽어온 16비트 Word 저장 변수 포인터 (Little-Endian)
 * @param use_pec PEC(CRC-8) 검증 여부
 * @return 0: 성공, 음수: 에러 코드
 */
int smbus_read_word(uint8_t ch, uint8_t addr, uint8_t cmd, uint16_t *val, bool use_pec);

/**
 * @brief SMBus 블록 쓰기 (Block Write 프로토콜)
 * @param ch 채널 번호 (0 ~ 5)
 * @param addr I2C 7비트 슬레이브 주소
 * @param cmd 명령 레지스터 주소
 * @param data 전송할 바이트 배열 포인터
 * @param len 전송할 데이터 길이
 * @param use_pec PEC(CRC-8) 전송 여부
 * @return 0: 성공, 음수: 에러 코드
 */
int smbus_write_block(uint8_t ch, uint8_t addr, uint8_t cmd, const uint8_t *data, uint8_t len, bool use_pec);

/**
 * @brief SMBus 블록 읽기 (Block Read 프로토콜)
 * @param ch 채널 번호 (0 ~ 5)
 * @param addr I2C 7비트 슬레이브 주소
 * @param cmd 명령 레지스터 주소
 * @param data 읽어온 바이트 데이터 저장 배열 포인터
 * @param len 수신된 실제 데이터 길이 저장 포인터
 * @param use_pec PEC(CRC-8) 검증 여부
 * @return 0: 성공, 음수: 에러 코드
 */
int smbus_read_block(uint8_t ch, uint8_t addr, uint8_t cmd, uint8_t *data, uint8_t *len, bool use_pec);

// SLFS 펌웨어 업로드용 직접 I2C 제어 API
/**
 * @brief 레지스터 주소 없는 Raw I2C 쓰기
 */
int smbus_i2c_write(uint8_t ch, uint8_t addr, const uint8_t *data, uint8_t len);

/**
 * @brief 레지스터 주소 없는 Raw I2C 읽기
 */
int smbus_i2c_read(uint8_t ch, uint8_t addr, uint8_t *data, uint8_t len);

/**
 * @brief Raw I2C Write 후 연속 Read (Combined format)
 */
int smbus_i2c_write_read(uint8_t ch, uint8_t addr, const uint8_t *tx_data, uint8_t tx_len, uint8_t *rx_data, uint8_t rx_len);

/**
 * @brief SMBus PEC (Packet Error Checking / CRC-8) 계산 함수
 * @param data CRC 계산할 데이터 배열
 * @param len 데이터 바이트 수
 * @return 8비트 PEC CRC 값
 */
uint8_t smbus_pec_calculate(const uint8_t *data, size_t len);

#endif // SMBUS_H
