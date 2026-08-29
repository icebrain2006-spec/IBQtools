/**
 * @file flash_store.h
 * @brief RP2040 온칩 플래시 메모리 기반 SLFS BQ 펌웨어 저장소 헤더
 */

#ifndef FLASH_STORE_H
#define FLASH_STORE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/// SLFS 메타데이터 저장 플래시 오프셋 (1MB 지점)
#define FLASH_SLFS_META_OFFSET  (1024 * 1024)       // 1MB
/// SLFS 바이너리 데이터 시작 오프셋 (1MB + 4KB 지점)
#define FLASH_SLFS_DATA_OFFSET  (FLASH_SLFS_META_OFFSET + 4096) // 1MB + 4KB

/// SLFS 파일 매직 식별자 ("SLFS" = 0x534C4653)
#define SLFS_MAGIC 0x534C4653

/**
 * @brief 플래시에 저장되는 SLFS 파일 메타데이터 구조체
 */
typedef struct {
    uint32_t magic;         ///< 매직 식별자 ("SLFS")
    uint32_t size;          ///< 파일 바이트 크기
    uint32_t crc32;         ///< 데이터 무결성 검증용 CRC32
    uint32_t timestamp;     ///< 저장 시각 타임스탬프
    char filename[64];      ///< 저장된 원본 파일명
    char ic_type[32];       ///< 대상 타겟 IC 종류 (예: BQ40Z50, BQ78350)
    char version[32];       ///< 펌웨어 버전 문자열
} flash_meta_t;

/**
 * @brief 플래시 저장소 초기화 (저장된 메타데이터 검증 및 로드)
 */
void flash_store_init(void);

/**
 * @brief SLFS 업로드 세션 시작 (요청된 크기만큼 플래시 섹터 4KB 소거)
 * @param size 업로드할 파일의 총 바이트 수
 * @return 0: 성공, 음수: 실패 에러 코드
 */
int flash_store_upload_start(uint32_t size);

/**
 * @brief SLFS 청크 데이터 플래시 작성 (256바이트 플래시 페이지 버퍼링 적용)
 * @param offset 업로드 오프셋
 * @param data 데이터 바이트 배열
 * @param len 데이터 길이
 * @return 0: 성공, 음수: 실패 에러 코드
 */
int flash_store_upload_chunk(uint32_t offset, const uint8_t *data, uint16_t len);

/**
 * @brief SLFS 업로드 마감 (남은 버퍼 작성, CRC32 검증, 메타데이터 영구 기록)
 */
int flash_store_upload_end(uint32_t expected_crc32, uint32_t timestamp, const char *filename, const char *ic_type, const char *version);

/**
 * @brief 현재 저장된 SLFS 메타데이터 정보 읽기
 * @param out_meta 메타데이터가 저장될 포인터
 * @return true: 유효한 메타데이터 존재, false: 없음
 */
bool flash_store_get_meta(flash_meta_t *out_meta);

/**
 * @brief 현재 저장된 SLFS 파일 바이트 크기 읽기
 */
uint32_t flash_store_get_size(void);

/**
 * @brief 플래시 메모리에서 SLFS 파일 데이터 읽기
 */
uint32_t flash_store_read_data(uint32_t offset, uint8_t *buf, uint32_t len);

/**
 * @brief CRC32 계산 헬퍼 함수
 */
uint32_t flash_store_crc32(const uint8_t *data, size_t len, uint32_t seed);

#endif // FLASH_STORE_H
