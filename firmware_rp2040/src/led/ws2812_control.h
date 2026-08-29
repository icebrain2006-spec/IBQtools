/**
 * @file ws2812_control.h
 * @brief RP2040-Zero 온보드 WS2812 RGB LED PIO 제어 드라이버 헤더
 */

#ifndef WS2812_CONTROL_H
#define WS2812_CONTROL_H

#include <stdint.h>
#include <stdbool.h>

/// RP28040-Zero RGB LED GPIO 핀 번호 (GP16)
#define WS2812_PIN 16

// 사전 정의된 색상 (0x00RRGGBB 포맷)
#define COLOR_WHITE   0x00333333  ///< 은은한 흰색
#define COLOR_CYAN    0x0000FFFF  ///< 청록색
#define COLOR_MAGENTA 0x00FF00FF  ///< 자홍색
#define COLOR_YELLOW  0x00FFFF00  ///< 노란색
#define COLOR_GREEN   0x0000FF00  ///< 초록색 (정상/완료)
#define COLOR_RED     0x00FF0000  ///< 빨간색 (에러)
#define COLOR_BLUE    0x000000FF  ///< 파란색 (통신 중)
#define COLOR_OFF     0x00000000  ///< LED 소등

/**
 * @brief LED 점등 모드
 */
typedef enum {
    LED_MODE_SOLID = 0,  ///< 고정 색상 지속 점등
    LED_MODE_BLINK = 1,  ///< 깜빡임 모드 (지정 시간 후 이전 색상 복귀)
} led_mode_t;

/**
 * @brief PIO를 사용한 WS2812 RGB LED 초기화 (GP16)
 */
void led_init(void);

/**
 * @brief LED 색상 및 점등 모드 설정
 * @param color 24비트 RGB 색상값 (0x00RRGGBB)
 * @param mode SOLID 또는 BLINK 모드
 * @param duration_ms BLINK 모드일 때 깜빡임 유지 시간 (ms)
 */
void led_set_state(uint32_t color, led_mode_t mode, uint32_t duration_ms);

/**
 * @brief 메인 루프에서 비동기 깜빡임을 처리하기 위해 호출하는 주기적 타이머 태스크
 */
void led_task(void);

#endif // WS2812_CONTROL_H
