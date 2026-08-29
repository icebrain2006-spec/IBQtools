# RP2040-Zero IBQtools C/C++ SDK 기반 펌웨어 CMake 빌드 파일
cmake_minimum_required(VERSION 3.13)

# Raspberry Pi Pico SDK 임포트
include(pico_sdk_import.cmake)

project(IBQtools_Firmware C CXX ASM)

# 호스트 도구(Pioasm, ELF2UF2) 빌드를 건너뛰어 크로스 컴파일 호환성 확보
add_custom_target(PioasmBuild)
add_custom_target(ELF2UF2Build)

# Pico SDK 초기화
pico_sdk_init()

# 펌웨어 실행 타겟 및 소스코드 파일 정의
add_executable(firmware
    src/main.c
    src/smbus_pio/smbus.c
    src/relay/relay.c
    src/flash/flash_store.c
    src/protocol/protocol.c
    src/bq_updater/bq_updater.c
    src/calib_engine/calib_engine.c
    src/calib_engine/bq40z50/bq40z50_calib.c
    src/calib_engine/bq78350/bq78350_calib.c
    src/calib_engine/bq40z80/bq40z80_calib.c
    src/led/ws2812_control.c
)

# 헤더 파일 인클루드 경로 지정
target_include_directories(firmware PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/smbus_pio
    ${CMAKE_CURRENT_SOURCE_DIR}/src/relay
    ${CMAKE_CURRENT_SOURCE_DIR}/src/flash
    ${CMAKE_CURRENT_SOURCE_DIR}/src/protocol
    ${CMAKE_CURRENT_SOURCE_DIR}/src/bq_updater
    ${CMAKE_CURRENT_SOURCE_DIR}/src/calib_engine
    ${CMAKE_CURRENT_SOURCE_DIR}/src/calib_engine/bq40z50
    ${CMAKE_CURRENT_SOURCE_DIR}/src/calib_engine/bq78350
    ${CMAKE_CURRENT_SOURCE_DIR}/src/calib_engine/bq40z80
    ${CMAKE_CURRENT_SOURCE_DIR}/src/led
)

# 하드웨어 드라이버 라이브러리 링크 (PIO, Flash, Sync, Multicore)
target_link_libraries(firmware PRIVATE
    pico_stdlib
    hardware_pio
    hardware_flash
    hardware_sync
    pico_multicore
)

# USB CDC 시리얼 포트 사용 설정 (UART 하드웨어 핀 미사용)
pico_enable_stdio_usb(firmware 1)
pico_enable_stdio_uart(firmware 0)
