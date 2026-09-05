# PC ↔ RP2040 Serial Communication Protocol Specification

## 1. 개요 (Overview)
본 문서는 PC(Python GUI)와 RP2040 펌웨어(C/C++ SDK) 간의 USB CDC 시리얼 이진 통신 프로토콜 규격을 정의합니다.

* **물리/논리 계층**: USB CDC (Virtual COM Port)
* **데이터 포맷**: 바이너리 패킷 (CRLF 변환 비활성화: `stdio_set_translate_crlf(..., false)`)
* **CRC 방식**: CRC16 (MODBUS 방식, 다항식 `0xA001`, Init `0xFFFF`)
* **엔디안 (Endianness)**:
  * **프레임 헤더 / 길이 / CRC**: Big-Endian (MSB First)
  * **일반 페이로드 구조체**: Big-Endian
  * **SMBus/I2C 레지스터 데이터**: Little-Endian (TI BQ 칩셋 사양)

---

## 2. 패킷 구조 (Packet Framing)

요청(Request) 및 응답(Response) 패킷은 동일한 프레임 구조를 사용합니다.

```
+-------+-------------------+----------+-------------------+-----------------+-------+
|  STX  |   Length (2B)     | Cmd (1B) |   Payload (NB)    |   CRC16 (2B)    |  ETX  |
| 0x02  | Cmd + Payload Len |  Cmd ID  |  Data Buffer      | MODBUS 0xA001   | 0x03  |
+-------+-------------------+----------+-------------------+-----------------+-------+
```

| 필드 | 바이트 크기 | 값 / 범위 | 설명 |
| :--- | :---: | :--- | :--- |
| **STX** | 1 Byte | `0x02` | 패킷 시작 마커 (Start of Text) |
| **Length** | 2 Bytes | `0x0001` ~ `0x0201` | **Cmd (1b) + Payload (Nb)** 의 바이트 길이 (Big-Endian) |
| **Cmd** | 1 Byte | `0x01` ~ `0x62` | 명령어 코드 (Command ID) |
| **Payload** | N Bytes | Data | 명령어별 가변 페이로드 (최대 512 바이트) |
| **CRC16** | 2 Bytes | `0x0000` ~ `0xFFFF` | **Cmd + Payload** 데이터 영역의 CRC16 (Big-Endian) |
| **ETX** | 1 Byte | `0x03` | 패킷 종료 마커 (End of Text) |

> **전체 패킷 길이** = `Length + 5` Bytes (STX 1b + Length 2b + CRC 2b + ETX 1b)

---

## 3. 응답 상태 코드 (Response Status Codes)

응답 패킷의 페이로드 첫 번째 바이트(`payload[0]`)는 실행 결과 상태 코드를 반환합니다.

| 코드 | 이름 | 설명 |
| :---: | :--- | :--- |
| `0x00` | **RESP_OK** | 정상 완료 |
| `0x01` | **RESP_ERR_CRC** | 수신 패킷 CRC 오류 |
| `0x02` | **RESP_ERR_UNKNOWN_CMD** | 미지원 명령어 코드 |
| `0x03` | **RESP_ERR_PARAM** | 유효하지 않은 매개변수 / 패킷 길이 오류 |
| `0x04` | **RESP_ERR_HW** | 하드웨어 / SMBus 통신 / Flash 오류 |
| `0x05` | **RESP_ERR_BUSY** | 작업 진행 중 (Core 1 Engine 동작 중) |

---

## 4. 명령어 상세 사양 (Command Reference)

### 4.1 시스템 및 릴레이 제어 (System & Relay)

#### `CMD_GET_VERSION` (0x01) - 펌웨어 버전 조회
* **요청 페이로드**: 없음 (`Length = 1`)
* **응답 페이로드**: `[Status(1b)]` + `Version String (ASCII)`
  * 예: `[0x00, 'v', '1', '.', '0', '.', '1', '5', '5', '\0']`

#### `CMD_REBOOT_BOOTSEL` (0x02) - BOOTSEL 다운로드 모드 리셋
* **요청 페이로드**: 없음 (`Length = 1`)
* **응답 페이로드**: `[Status(1b)]`
* **설명**: 응답 전송 후 100ms 뒤 RP2040을 USB BOOTSEL ROM 모드로 리셋합니다.

#### `CMD_RELAY_SET` (0x10) - 릴레이 채널 설정
* **요청 페이로드**: `[Ch_Mask(1b)]` (Bit 0~5 = CH1~CH6 ON/OFF)
* **응답 페이로드**: `[Status(1b)]` + `[Current_Mask(1b)]`

#### `CMD_RELAY_GET` (0x11) - 릴레이 상태 읽기
* **요청 페이로드**: 없음 (`Length = 1`)
* **응답 페이로드**: `[Status(1b)]` + `[Current_Mask(1b)]`

#### `CMD_SET_LED_STATE` (0x50) - WS2812 RGB LED 제어
* **요청 페이로드**: `[RGB_Color(4b, U32 BE)]` + `[Mode(1b)]` + `[Duration_Sec(1b)]`
* **응답 페이로드**: `[Status(1b)]`

---

### 4.2 SMBus / I2C 직접 제어 (Direct Pass-through)

#### `CMD_SMBUS_CMD` (0x20) - SMBus 트랜잭션 실행
* **요청 페이로드**:
  * `[Channel(1b)]`: Target Channel (1~6)
  * `[Addr(1b)]`: 7-bit I2C Address (예: `0x0B`)
  * `[Cmd_Reg(1b)]`: SMBus Command Code
  * `[RW(1b)]`: `0` = Write, `1` = Read
  * `[Len(1b)]`: 바이트 길이 (1=Byte, 2=Word, >2=Block)
  * `[Use_PEC(1b)]`: `0` = PEC 미사용, `1` = PEC 사용
  * `[Data(Nb)]`: Write 시 전송 데이터
* **응답 페이로드**:
  * **Write**: `[Status(1b)]` + `[Err_Detail(1b)]`
  * **Read**: `[Status(1b)]` + `[Rx_Len(1b)]` + `[Read_Data(Nb)]`

#### `CMD_I2C_RAW` (0x21) - Raw I2C 트랜잭션
* **요청 페이로드**: `[Ch(1b)]` + `[Addr(1b)]` + `[Tx_Len(1b)]` + `[Rx_Len(1b)]` + `[Tx_Data(Nb)]`
* **응답 페이로드**: `[Status(1b)]` + `[Err_Detail(1b)]` + `[Rx_Data(Nb)]` (Rx_Len > 0)

#### `CMD_SMBUS_POLL_BLOCK` (0x23) - 연속 블록 읽기 (Polling)
* **요청 페이로드**: `[Ch(1b)]` + `[Addr(1b)]` + `[Cmd_Reg(1b)]` + `[Interval_ms(1b)]` + `[Count(1b)]`
* **응답 페이로드**: `[Status(1b)]` + `[Block1_Len(1b)]` + `[Block1_Data]` + `[Block2_Len(1b)]` + ...

---

### 4.3 BQ 펌웨어 업로드 및 플래싱 (Firmware Flashing Engine)

#### `CMD_FW_UPLOAD_START` (0x30) - SLFS 펌웨어 수신 시작
* **요청 페이로드**: `[Total_File_Size(4b, U32 BE)]`
* **응답 페이로드**: `[Status(1b)]`

#### `CMD_FW_UPLOAD_DATA` (0x31) - SLFS 청크 데이터 전송
* **요청 페이로드**: `[Offset(4b, U32 BE)]` + `[Chunk_Len(2b, U16 BE)]` + `[Chunk_Data(Nb)]`
* **응답 페이로드**: `[Status(1b)]`

#### `CMD_FW_UPLOAD_END` (0x32) - 업로드 완료 및 메타데이터 기록
* **요청 페이로드**: `[Expected_CRC32(4b)]` + `[Timestamp(4b)]` + `[Filename(64b)]` + `[IC_Type(32b)]` + `[Version(32b)]`
* **응답 페이로드**: `[Status(1b)]`

#### `CMD_FW_GET_FILE_INFO` (0x35) - 플래시에 저장된 SLFS 정보 조회
* **요청 페이로드**: 없음 (`Length = 1`)
* **응답 페이로드**: `[Status(1b)]` + `[Magic(4b)]` + `[Size(4b)]` + `[CRC32(4b)]` + `[Timestamp(4b)]` + `[Filename(64b)]` + `[IC_Type(32b)]` + `[Version(32b)]`

#### `CMD_FW_UPDATE_RUN` (0x40) - 6채널 동시 BQ 펌웨어 갱신 시작 (Core 1)
* **요청 페이로드**: `[Ch_Mask(1b)]`
* **응답 페이로드**: `[Status(1b)]` (`RESP_OK` 또는 `RESP_ERR_BUSY`)

#### `CMD_FW_UPDATE_STATUS` (0x41) - 펌웨어 갱신 진행률 조회
* **요청 페이로드**: 없음 (`Length = 1`)
* **응답 페이로드**: `[Status(1b)]` + `[State(1b)]` + `[Curr_Line(4b)]` + `[Total_Line(4b)]` + `[Active_Mask(1b)]` + `[Error_Mask(1b)]` + `[Err_Code(4b)]`

#### `CMD_FW_UPDATE_STOP` (0x42) - 펌웨어 갱신 중단
* **요청 페이로드**: 없음 (`Length = 1`)
* **응답 페이로드**: `[Status(1b)]`

---

### 4.4 자동 캘리브레이션 엔진 (Calibration Engine - Core 1)

#### `CMD_CALIB_RUN` (0x60) - 자동 캘리브레이션 시작
* **요청 페이로드 (개별 채널 타겟 설정 - 38 Bytes)**:
  * `[Ch_Mask(1b)]`: 대상 채널 마스크 (Bit 0~5 = CH1~CH6)
  * `[Mode(1b)]`: `0` = Voltage, `1` = Current, `2` = Temp
  * `[CH1~CH6 Target Data (36b)]`: 채널당 6바이트 (U16 Cell1, U16 Pack, U16 Bat) $\times$ 6개 채널
* **응답 페이로드**: `[Status(1b)]` (`RESP_OK` 또는 `RESP_ERR_BUSY`)

#### `CMD_CALIB_STATUS` (0x61) - 캘리브레이션 진행 및 결과 조회
* **요청 페이로드**: 없음 (`Length = 1`)
* **응답 페이로드 (총 178 Bytes)**:
  * `[Status(1b)]` + `[State(1b)]` + `[Active_Mask(1b)]` + `[Error_Mask(1b)]`
  * `[CH1 ~ CH6 Result Data (채널당 29 Bytes $\times$ 6 = 174 Bytes)]`:
    * `Cell1 Gain (2b, U16 LE)`
    * `Pack Gain (2b, U16 LE)`
    * `Bat Gain (2b, U16 LE)`
    * `Success Flag (1b)`: `1` = 성공, `0` = 실패
    * `Raw Cell1 ADC (2b, U16 LE)`
    * `Raw Pack ADC (2b, U16 LE)`
    * `Raw Bat ADC (2b, U16 LE)`
    * `Raw Flash Bytes (18b)`: DataFlash 읽기 원본 덤프

#### `CMD_CAL_EN_SET` (0x62) - 캘리브레이션 모드 (CAL_EN) 토글
* **요청 페이로드**: `[Ch_Mask(1b)]` + `[Enable(1b)]` (`1` = ON, `0` = OFF)
* **응답 페이로드**: `[Status(1b)]` (`RESP_OK` 또는 `RESP_ERR_HW`)
