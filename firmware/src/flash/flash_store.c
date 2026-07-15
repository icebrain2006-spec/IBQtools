#include "flash_store.h"
#include "pico/stdlib.h"
#include "hardware/flash.h"
#include "hardware/sync.h"
#include <string.h>

static volatile flash_meta_t current_meta;
static volatile bool meta_loaded = false;

// Internal write buffer for 256-byte alignment
static uint8_t write_buffer[256];
static uint16_t write_buf_idx = 0;
static uint32_t flash_write_offset = 0;

// CRC32 implementation (IEEE 802.3 polynomial 0xEDB88320)
uint32_t flash_store_crc32(const uint8_t *data, size_t len, uint32_t seed) {
    uint32_t crc = ~seed;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xEDB88320;
            } else {
                crc >>= 1;
            }
        }
    }
    return ~crc;
}

void flash_store_init(void) {
    // Read current metadata from Flash
    // Note: To access flash directly, use XIP base address + offset
    const flash_meta_t *meta_flash = (const flash_meta_t *)(XIP_BASE + FLASH_SLFS_META_OFFSET);
    
    if (meta_flash->magic == SLFS_MAGIC) {
        current_meta = *meta_flash;
        meta_loaded = true;
    } else {
        current_meta.magic = 0;
        current_meta.size = 0;
        current_meta.crc32 = 0;
        meta_loaded = false;
    }
}

int flash_store_upload_start(uint32_t size) {
    // Stop writing state
    write_buf_idx = 0;
    flash_write_offset = 0;
    
    // 512KB limit check
    if (size > (512 * 1024)) return -1;
    
    // Calculate sectors to erase (each sector is 4096 bytes)
    // 1 sector for metadata + enough sectors for data
    uint32_t data_sectors = (size + 4095) / 4096;
    uint32_t total_erase_size = (1 + data_sectors) * 4096;
    
    // Disable interrupts during flash erase
    uint32_t ints = save_and_disable_interrupts();
    flash_range_erase(FLASH_SLFS_META_OFFSET, total_erase_size);
    restore_interrupts(ints);
    
    current_meta.magic = 0;
    current_meta.size = size;
    current_meta.crc32 = 0;
    meta_loaded = false;
    
    return 0;
}

int flash_store_upload_chunk(uint32_t offset, const uint8_t *data, uint16_t len) {
    // Ensure chronological programming or relative offsets
    for (uint16_t i = 0; i < len; i++) {
        write_buffer[write_buf_idx++] = data[i];
        
        if (write_buf_idx == 256) {
            uint32_t target_flash_addr = FLASH_SLFS_DATA_OFFSET + flash_write_offset;
            
            uint32_t ints = save_and_disable_interrupts();
            flash_range_program(target_flash_addr, write_buffer, 256);
            restore_interrupts(ints);
            
            flash_write_offset += 256;
            write_buf_idx = 0;
        }
    }
    return 0;
}

int flash_store_upload_end(uint32_t expected_crc32) {
    // Flush remaining buffer
    if (write_buf_idx > 0) {
        // Pad the rest of the page with zeros
        memset(write_buffer + write_buf_idx, 0, 256 - write_buf_idx);
        uint32_t target_flash_addr = FLASH_SLFS_DATA_OFFSET + flash_write_offset;
        
        uint32_t ints = save_and_disable_interrupts();
        flash_range_program(target_flash_addr, write_buffer, 256);
        restore_interrupts(ints);
        
        flash_write_offset += 256;
        write_buf_idx = 0;
    }
    
    // Verify CRC32 from Flash content
    uint32_t file_size = current_meta.size;
    uint32_t computed_crc = 0;
    
    // Compute CRC32 in chunks of 256 bytes directly from mapped flash memory
    uint32_t bytes_to_read = file_size;
    const uint8_t *flash_data_ptr = (const uint8_t *)(XIP_BASE + FLASH_SLFS_DATA_OFFSET);
    computed_crc = flash_store_crc32(flash_data_ptr, bytes_to_read, 0);
    
    if (computed_crc != expected_crc32) {
        // Mismatch, discard upload
        return -2;
    }
    
    // Program metadata
    current_meta.magic = SLFS_MAGIC;
    current_meta.crc32 = computed_crc;
    
    // Prepare metadata block (must be 256 bytes aligned for program)
    uint8_t meta_block[256];
    memset(meta_block, 0, sizeof(meta_block));
    memcpy(meta_block, &current_meta, sizeof(flash_meta_t));
    
    uint32_t ints = save_and_disable_interrupts();
    flash_range_program(FLASH_SLFS_META_OFFSET, meta_block, 256);
    restore_interrupts(ints);
    
    meta_loaded = true;
    return 0;
}

uint32_t flash_store_get_size(void) {
    if (!meta_loaded) return 0;
    return current_meta.size;
}

uint32_t flash_store_read_data(uint32_t offset, uint8_t *buf, uint32_t len) {
    if (!meta_loaded) return 0;
    if (offset >= current_meta.size) return 0;
    
    uint32_t available = current_meta.size - offset;
    uint32_t to_read = (len < available) ? len : available;
    
    const uint8_t *flash_data_ptr = (const uint8_t *)(XIP_BASE + FLASH_SLFS_DATA_OFFSET + offset);
    memcpy(buf, flash_data_ptr, to_read);
    
    return to_read;
}
