/**
 * @file bq_updater.h
 * @brief Core 1 독립 실행형 6채널 동시 BQ IC SLFS 펌웨어 업데이터 헤더
 */

#ifndef BQ_UPDATER_H
#define BQ_UPDATER_H

#include <stdint.h>
#include <stdbool.h>

/**
 * @brief BQ 펌웨어 업데이터 진행 상태 열거형
 */
typedef enum {
    UPDATER_STATE_IDLE = 0,     ///< 대기 상태
    UPDATER_STATE_RUNNING = 1,  ///< 펌웨어 업데이트 진행 중
    UPDATER_STATE_DELAYING = 2, ///< 명령 간 지연(Delay) 대기 중
    UPDATER_STATE_ERROR = 3,    ///< 업데이트 중 오류 발생
    UPDATER_STATE_DONE = 4      ///< 6채널 펌웨어 업데이트 정상 완료
} updater_state_e;

/**
 * @brief BQ 펌웨어 업데이터 실시간 상태 정보 구조체 (듀얼 코어 동기화 volatile 적용)
 */
typedef struct {
    volatile updater_state_e state;      ///< 현재 진행 상태
    volatile uint32_t current_line;      ///< 현재 처리 중인 SLFS 명령 줄 번호
    volatile uint32_t total_lines;       ///< 전체 SLFS 명령 줄 수
    volatile uint8_t active_channels;    ///< 활성화된 채널 비트마스크 (bit 0~5 -> CH1~CH6)
    volatile uint8_t error_channels;     ///< 실패/에러 발생한 채널 비트마스크
    volatile int error_code;             ///< 발생한 에러 코드
    volatile uint32_t current_delay_ms;  ///< 지연 대기 중일 때 남은 지연 시간(ms)
} update_status_t;

/// 전역 업데이트 상태 변수 (Core 0과 Core 1 공유)
extern volatile update_status_t update_status;

/**
 * @brief 업데이터 모듈 초기화 및 RP2040 Core 1 엔트리 포인트 등록
 */
void bq_updater_init(void);

/**
 * @brief 지정된 채널 마스크로 BQ IC 펌웨어 업데이트 시작 (Core 1 비동기 실행)
 * @param channel_mask 업데이트 대상 채널 비트마스크 (예: 0x3F = 6개 전 채널)
 * @return 시작 성공 여부 (bool)
 */
bool bq_updater_start(uint8_t channel_mask);

/**
 * @brief 강제로 진행 중인 펌웨어 업데이트 정지
 */
void bq_updater_stop(void);

#endif // BQ_UPDATER_H
