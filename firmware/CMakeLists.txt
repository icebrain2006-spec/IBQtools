cmake_minimum_required(VERSION 3.13)

# Pico SDK Import
include(pico_sdk_import.cmake)

project(IBQtools_Firmware C CXX ASM)

# Bypass host tools compilation by pre-defining their build targets before SDK init
add_custom_target(PioasmBuild)
add_custom_target(ELF2UF2Build)

# Initialize Pico SDK
pico_sdk_init()

# Define executable and source files
add_executable(firmware
    src/main.c
    src/smbus_pio/smbus.c
    src/relay/relay.c
    src/flash/flash_store.c
    src/protocol/protocol.c
    src/bq_updater/bq_updater.c
    src/led/ws2812_control.c
)

# Pull in PIO header generation (Bypassed: using precompiled smbus.pio.h)
# pico_generate_pio_header(firmware ${CMAKE_CURRENT_SOURCE_DIR}/src/smbus_pio/smbus.pio)

# Include directories
target_include_directories(firmware PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/smbus_pio
    ${CMAKE_CURRENT_SOURCE_DIR}/src/relay
    ${CMAKE_CURRENT_SOURCE_DIR}/src/flash
    ${CMAKE_CURRENT_SOURCE_DIR}/src/protocol
    ${CMAKE_CURRENT_SOURCE_DIR}/src/bq_updater
    ${CMAKE_CURRENT_SOURCE_DIR}/src/led
)

# Link hardware libraries
target_link_libraries(firmware PRIVATE
    pico_stdlib
    hardware_pio
    hardware_flash
    hardware_sync
    pico_multicore
)

# Enable USB CDC Serial (tud_cdc), disable hardware UART
pico_enable_stdio_usb(firmware 1)
pico_enable_stdio_uart(firmware 0)

# Add post-install steps (e.g. generate uf2) (Bypassed: will convert elf manually)
# pico_add_extra_outputs(firmware)
