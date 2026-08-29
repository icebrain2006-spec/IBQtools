# Codex Harness for BQ Calibration

## Build & Run Commands
- Primary (Python GUI): `uv run python main.py` (또는 GUI 디렉토리 내 진입점)
- Setup: `uv sync`
- Install package: `uv add <package>`
- Firmware Build (C/C++): CMake 기반 Pico SDK 빌드 (`mkdir build && cd build && cmake .. && make`)

## Directory Standards
- **`firmware/`**: RP2040-Zero C/C++ SDK 소스코드. PIO 기반 SMBus 및 Relay 제어 로직 위치.
- **`gui/`**: Python 기반 PC 프로그램 및 GUI 레이아웃 리소스 위치.

## Development Standards
- **300-Line Limit**: Break down files exceeding 300 lines into logical components.
- **Lore Tracking**: Document significant logic changes (especially register offsets) in `.autopus/lore/`.
- **Concurrency**: NEVER block the main UI thread. Use `utils/worker.py` (if exists) or `QRunnable`.
- **Hardware Safety**: Always include PEC (Checksum) for DataFlash writes on BQ40Z50.

## Error Prevention (BQ & RP2040 Specific)
- **SMBus Timeout**: RP2040 PIO SMBus 통신 타임아웃은 기본 `50ms`로 제한하며, 에러 발생 시 즉시 PC에 Serial을 통해 리포트해야 합니다.
- **Endianness**: Gain values for BQ40Z50 are typically Little-Endian uint16 (unless float32 in specific CC gain sections).
- **Header Matching**: Always use `_find_header()` to locate command echoes in SMBus responses to avoid byte-shift errors.
- **Timing**: Respect `_DELAY` constants from `calibrators/bq40z50.py`.

## Restricted Actions (v2.0 Development)
- **No Git Deploy**: 2.0 버전은 대규모 수정이 진행되므로, 다시 요청하기 전까지 `deploy_github.py`를 통한 git 배포/푸시 작업을 절대 진행하지 않는다.
- **No Windows Build**: 다시 요청하기 전까지 `build_windows.py`를 통한 빌드/패키징 작업을 실행하지 않는다.

