#ifndef FLASH_STORE_H
#define FLASH_STORE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define FLASH_SLFS_META_OFFSET  (1024 * 1024)       // 1MB
#define FLASH_SLFS_DATA_OFFSET  (FLASH_SLFS_META_OFFSET + 4096) // 1MB + 4KB

#define SLFS_MAGIC 0x534C4653 // "SLFS"

typedef struct {
    uint32_t magic;
    uint32_t size;
    uint32_t crc32;
    uint32_t timestamp;
    char filename[64];
    char ic_type[32];
    char version[32];
} flash_meta_t;

// Initialize flash store (read metadata)
void flash_store_init(void);

// Start an upload session: erases the needed sectors
int flash_store_upload_start(uint32_t size);

// Write chunk of data (buffers internally to align with 256-byte flash page size)
int flash_store_upload_chunk(uint32_t offset, const uint8_t *data, uint16_t len);

// Finish upload session: flushes remaining buffer, computes CRC32, and writes metadata
int flash_store_upload_end(uint32_t expected_crc32, uint32_t timestamp, const char *filename, const char *ic_type, const char *version);

// Get current metadata
bool flash_store_get_meta(flash_meta_t *out_meta);

// Get current saved SLFS file size
uint32_t flash_store_get_size(void);

// Read SLFS file data
uint32_t flash_store_read_data(uint32_t offset, uint8_t *buf, uint32_t len);

// Helper CRC32 function
uint32_t flash_store_crc32(const uint8_t *data, size_t len, uint32_t seed);

#endif // FLASH_STORE_H
