# Codex Harness for BQ Calibration

## Build & Run Commands
- Primary (Python GUI): `uv run python main.py` (또는 GUI 디렉토리 내 진입점)
- Setup: `uv sync`
- Install package: `uv add <package>`
- Firmware Build (C/C++): CMake 기반 Pico SDK 빌드 (`mkdir build && cd build && cmake .. && make`)

## Directory Standards
- **`firmware_rp2040/`**: RP2040-Zero C/C++ SDK 소스코드. PIO 기반 SMBus 및 Relay 제어 로직 위치.
- **`gui/`**: Python 기반 PC 프로그램 및 GUI 레이아웃 리소스 위치.

## Development Standards
- **300-Line Limit**: Break down files exceeding 300 lines into logical components.
- **Lore Tracking**: Document significant logic changes (especially register offsets) in `.autopus/lore/`.
- **Concurrency**: NEVER block the main UI thread. Use `utils/worker.py` (if exists) or `QRunnable`.
- **Hardware Safety**: Always include PEC (Checksum) for DataFlash writes on BQ40Z50.

## Modular Architecture & Refactoring Standards
- **Single Responsibility Principle (단일 책임 원칙)**: 하나의 함수는 단 하나의 기능만 수행하도록 작성합니다. 함수 길이가 길어지면 역할별 헬퍼 함수로 세분화합니다.
- **Module-Level Constant Extraction (상수/맵 모듈 분리)**: 에러 코드 맵(예: `ERR_STAGE_MAP`), 설정 딕셔너리, 매핑 테이블 등 정적 데이터는 함수 내부에 매번 선언하지 않고 모듈 상단 상수로 분리하여 메모리 재할당을 방지하고 가독성을 높입니다.
- **Mixin & Sub-Package Decomposition (모듈화 구조)**:
  - 300줄을 초과하는 거대 클래스는 역할(통신, 감지, HW 캘리브레이션 등)에 따라 Mixin 클래스로 분리합니다.
  - 특정 IC/장치별 분기 조건문은 단일 파일 내 거대 조건문 대신 서브 패키지(예: `verifiers/`)로 모듈화하고 디스패처 패턴을 적용합니다.
- **File I/O Isolation (관심사 분리)**: CSV 로그 파일 생성/저장 등 파일 시스템 I/O 로직은 스레드 클래스 내부에서 직접 작성하지 않고 `utils.py` 등의 독립 유틸리티 함수로 분리합니다.
- **Compilation Verification**: 모듈 분리 및 수정 후에는 반드시 `uv run python -m py_compile <files...>` 명령으로 구문 및 교차 참조 오류를 검증합니다.


## Error Prevention (BQ & RP2040 Specific)
- **SMBus Timeout**: RP2040 PIO SMBus 통신 타임아웃은 기본 `50ms`로 제한하며, 에러 발생 시 즉시 PC에 Serial을 통해 리포트해야 합니다.
- **Endianness**: Gain values for BQ40Z50 are typically Little-Endian uint16 (unless float32 in specific CC gain sections).
- **Header Matching**: Always use `_find_header()` to locate command echoes in SMBus responses to avoid byte-shift errors.
- **Timing**: Respect `_DELAY` constants from `calibrators/bq40z50.py`.

## Restricted Actions (v2.0 Development)
- **No Git Deploy**: 2.0 버전은 대규모 수정이 진행되므로, 다시 요청하기 전까지 `deploy_github.py`를 통한 git 배포/푸시 작업을 절대 진행하지 않는다.
- **No Windows Build**: 다시 요청하기 전까지 `build_windows.py`를 통한 빌드/패키징 작업을 실행하지 않는다.


