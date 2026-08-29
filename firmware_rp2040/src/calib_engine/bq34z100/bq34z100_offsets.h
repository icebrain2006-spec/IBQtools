/**
 * @file bq34z100_offsets.h
 * @brief BQ34Z100 IC 전용 오프셋 헤더 (공통 시프트 정의 및 버전별 오프셋 포함)
 */

#ifndef BQ34Z100_OFFSETS_H
#define BQ34Z100_OFFSETS_H

#include <stdint.h>

#ifndef SMBUS_PAYLOAD_OFFSET_SHIFT
#define SMBUS_PAYLOAD_OFFSET_SHIFT (-1)

static inline uint8_t get_payload_offset(uint8_t wire_offset) {
    return (uint8_t)(wire_offset + SMBUS_PAYLOAD_OFFSET_SHIFT);
}
#endif

#include "bq34z100_v0_16_offsets.h"

#endif // BQ34Z100_OFFSETS_H
