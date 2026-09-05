# Lore: PC ↔ RP2040 Serial Protocol Architecture

## Context & History
PC (Python GUI)와 RP2040 (C/C++ Pico SDK) 통신은 USB CDC 시리얼 이진 프로토콜을 사용하며, MODBUS 0xA001 CRC16을 이용하여 데이터 무결성을 검증합니다.

## Key Framing Rules
1. **STX/ETX**: `0x02` / `0x03`
2. **Length Field**: Big-Endian 2바이트 (`Cmd + Payload` 길이)
3. **Status Field**: 모든 응답의 `payload[0]`는 `RESP_OK (0x00)` 또는 에러 코드 (`RESP_ERR_*`)
4. **Calibration Core 1 Protocol (0x60 / 0x61)**:
   - `CMD_CALIB_RUN` (0x60): 채널 마스크, 모드(Voltage=0, Current=1, Temp=2), 채널별 타겟값(Cell1, Pack, Bat) 수신
   - `CMD_CALIB_STATUS` (0x61): State, ActiveMask, ErrorMask 및 채널 1~6의 결과(Gain, Raw ADC, 18B raw DataFlash 덤프) 178바이트 수신

## Documentation Location
프로토콜 상세 명세는 [protocol_spec.md](file:///d:/WinApp/python/IBQtools/docs/protocol_spec.md)에 유지관리됩니다.
