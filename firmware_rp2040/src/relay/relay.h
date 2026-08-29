/**
 * @file relay.h
 * @brief RP2040 6채널 릴레이 제어 드라이버 헤더
 */

#ifndef RELAY_H
#define RELAY_H

#include <stdint.h>
#include <stdbool.h>

/// 지원 릴레이 채널 수 (1 ~ 6)
#define RELAY_NUM_CHANNELS 6

/**
 * @brief 릴레이 제어용 GPIO 핀 초기화 (GP6, GP7, GP8, GP9, GP10, GP11)
 */
void relay_init(void);

/**
 * @brief 개별 릴레이 채널 상태 설정
 * @param ch 채널 번호 (1 ~ 6)
 * @param state true: 릴레이 켜짐(ON/High), false: 릴레이 꺼짐(OFF/Low)
 */
void relay_set_state(uint8_t ch, bool state);

/**
 * @brief 비트마스크를 사용하여 6개 릴레이 전체 상태 한 번에 설정
 * @param mask 채널 1~6에 대응하는 비트마스크 (bits 0~5)
 */
void relay_set_mask(uint8_t mask);

/**
 * @brief 현재 릴레이 6개 전체의 ON/OFF 상태를 비트마스크로 읽기
 * @return 6채널 릴레이 상태 비트마스크 (bits 0~5)
 */
uint8_t relay_get_mask(void);

#endif // RELAY_H
