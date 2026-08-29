/**
 * @file protocol.h
 * @brief PC-RP2040 간 시리얼 통신 프로토콜 정의 및 이진 패킷 파서 헤더
 */

#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/// 패킷 프레임 시작 바이트 (STX)
#define PROTOCOL_STX 0x02
/// 패킷 프레임 종료 바이트 (ETX)
#define PROTOCOL_ETX 0x03

/// 최대 페이로드 버퍼 크기 (바이트 단위)
#define PROTOCOL_MAX_PAYLOAD 512

// 프로토콜 명령어(Command) 정의
#define CMD_GET_VERSION      0x01  ///< 펌웨어 버전 조회
#define CMD_REBOOT_BOOTSEL   0x02  ///< RP2040 BOOTSEL 다운로드 모드로 소프트 리셋
#define CMD_RELAY_SET        0x10  ///< 릴레이 상태 제어 (ON/OFF)
#define CMD_RELAY_GET        0x11  ///< 현재 릴레이 상태 읽기
#define CMD_SMBUS_CMD        0x20  ///< SMBus 트랜잭션 요청 (Read/Write Word, Block 등)
#define CMD_I2C_RAW          0x21  ///< Raw I2C 트랜잭션
#define CMD_SMBUS_POLL_BLOCK 0x23  ///< SMBus 블록 폴링 요청
#define CMD_FW_UPLOAD_START  0x30  ///< BQ 펌웨어(SLFS 파일) 업로드 시작
#define CMD_FW_UPLOAD_DATA   0x31  ///< SLFS 데이터 블록 수신 및 플래시 기록
#define CMD_FW_UPLOAD_END    0x32  ///< SLFS 데이터 업로드 마감 및 검증
#define CMD_FW_GET_FILE_INFO 0x35  ///< 플래시에 수신된 SLFS 파일 정보 확인
#define CMD_FW_UPDATE_RUN    0x40  ///< Core 1 기반 6채널 동시 BQ 펌웨어 업데이트 시작
#define CMD_FW_UPDATE_STATUS 0x41  ///< BQ 펌웨어 업데이트 진행 상태 조회
#define CMD_FW_UPDATE_STOP   0x42  ///< BQ 펌웨어 업데이트 정지
#define CMD_SET_LED_STATE    0x50  ///< WS2812 RGB LED 상태 변경
#define CMD_CALIB_RUN        0x60  ///< 캘리브레이션 시퀀스 실행
#define CMD_CALIB_STATUS     0x61  ///< 캘리브레이션 실행 상태 조회
#define CMD_CAL_EN_SET       0x62  ///< 캘리브레이션 활성화(CAL_EN) 설정

// 명령 실행 결과 응답 코드 (Response Status)
#define RESP_OK              0x00  ///< 정상 완료
#define RESP_ERR_CRC         0x01  ///< 수신된 패킷 CRC 오류
#define RESP_ERR_UNKNOWN_CMD 0x02  ///< 미지원 명령어
#define RESP_ERR_PARAM       0x03  ///< 유효하지 않은 매개변수
#define RESP_ERR_HW          0x04  ///< 하드웨어/SMBus 오류
#define RESP_ERR_BUSY        0x05  ///< 장치가 바쁨 (다른 작업 진행 중)

/**
 * @brief 수신 패킷 구조체
 */
typedef struct {
    uint8_t cmd;                           ///< 수신된 명령어 코드
    uint16_t length;                        ///< 페이로드 바이트 길이
    uint8_t payload[PROTOCOL_MAX_PAYLOAD]; ///< 페이로드 버퍼
} rx_packet_t;

/**
 * @brief 시리얼 바이트 스트림을 1바이트씩 입력받아 패킷 조립 및 CRC 검증
 * @param byte 수신된 1바이트 데이터
 * @param pkt 완전한 패킷 수신 시 데이터가 채워질 구조체 포인터
 * @return true: 완전하고 검증된 패킷 수신 완료, false: 수신 진행 중
 */
bool protocol_parse_byte(uint8_t byte, rx_packet_t *pkt);

/**
 * @brief 응답 패킷을 조립하여 USB CDC (시리얼 포트)로 전송
 * @param cmd 응답 명령어 코드
 * @param payload 전송할 페이로드 데이터 포인터
 * @param len 페이로드 바이트 길이
 */
void protocol_send_packet(uint8_t cmd, const uint8_t *payload, uint16_t len);

/**
 * @brief 프로토콜 검증용 CRC16 (MODBUS 0xA001) 계산
 * @param data 계산할 데이터 배열
 * @param len 데이터 바이트 수
 * @return 16비트 CRC 값
 */
uint16_t crc16_calculate(const uint8_t *data, size_t len);

#endif // PROTOCOL_H
