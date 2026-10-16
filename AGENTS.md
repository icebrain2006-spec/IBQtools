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
- **Centralized Styling & Design Tokens (스타일/디자인 토큰 중앙 관리)**: UI 하드코딩 색상(`QColor("#1e1e1e")` 등) 및 디자인 토큰은 코드 곳곳에 직접 작성하지 않고 `gui/styles.py` (`Colors` 클래스)에서 중앙 집중 관리하여 디자인 일관성과 유지보수성을 보장합니다.
- **Centralized UI Strings & Label Management (UI 문자열 중앙 관리)**: UI에 표시되는 버튼 텍스트, 필드 라벨, 툴팁 등 하드코딩 문자열은 `gui/strings.py` (`UIStrings` 클래스)에서 중앙 관리하여 문구 일관성 및 추후 다국어(i18n) 확장을 보장합니다.
- **Compilation Verification**: 모듈 분리 및 수정 후에는 반드시 `uv run python -m py_compile <files...>` 명령으로 구문 및 교차 참조 오류를 검증합니다.


## Error Prevention (BQ & RP2040 Specific)
- **SMBus Timeout**: RP2040 PIO SMBus 통신 타임아웃은 기본 `50ms`로 제한하며, 에러 발생 시 즉시 PC에 Serial을 통해 리포트해야 합니다.
- **Endianness**: Gain values for BQ40Z50 are typically Little-Endian uint16 (unless float32 in specific CC gain sections).
- **Header Matching**: Always use `_find_header()` to locate command echoes in SMBus responses to avoid byte-shift errors.
- **Timing**: Respect `_DELAY` constants from `calibrators/bq40z50.py`.

## Restricted Actions (v2.0 Development)
- **No Git Deploy**: 2.0 버전은 대규모 수정이 진행되므로, 다시 요청하기 전까지 `deploy_github.py`를 통한 git 배포/푸시 작업을 절대 진행하지 않는다.
- **No Windows Build**: 다시 요청하기 전까지 `build_windows.py`를 통한 빌드/패키징 작업을 실행하지 않는다.

## Autonomous Execution & Rollback Guarantee (자율 실행 및 원상 복구 규정)
- **자율 검증 및 선실행 원칙 (Autonomous Verification)**: 사소한 분기점(실행 방법, 단순 진단 스크립트 작성 등)마다 매번 사용자에게 허락을 구하지 마세요. 가장 안전하고 합리적인 방식을 자율적으로 선택하여 먼저 실행·검증한 뒤 결과 중심으로 보고합니다.
- **실패 시 즉각 롤백 보장 (Mandatory Rollback on Failure)**: 
  - 작업을 시작하기 전 반드시 기준 상태(Clean Git 상태)를 파악합니다.
  - 자체적으로 원인 분석, 코드 수정, 테스트를 진행하다가 문제를 완전히 해결하지 못하거나 한계에 부딪힌 경우, **코드를 임의로 방치하지 말고 즉시 `git restore` 등을 통해 작업 착수 전 상태로 100% 원상 복구(Rollback)**한 뒤 그 사유와 분석 결과를 보고합니다.
- **운영 코드 오염 방지 (Scratch Isolation)**: 가설 검증이나 하드웨어 진단은 `scratch/` 디렉토리의 일회성 스크립트를 사용하여 기존 운영 코드가 불필요하게 훼손되지 않도록 격리합니다.
- **문제 해결 시 자동 커밋 (Auto-Commit on Verified Fix)**: 
  - 문제 원인 분석 및 코드 수정 후, 실행/테스트를 통해 문제가 성공적으로 해결되었음이 검증되면 **사용자에게 매번 묻지 말고 즉시 명확한 커밋 메시지와 함께 로컬 Git에 자동으로 커밋**합니다. (단, 푸시/배포는 금지 규정 준수)
- **트러블슈팅 히스토리 문서화 & 사전 필수 조회 (Troubleshooting Lore & Decision Log)**:
  - **기록**: 문제가 해결될 때마다 `docs/troubleshooting.md`에 [발생 현상, 근본 원인, 해결 조치, 이 결정을 내린 이유(의사결정 배경)]를 즉시 추가 기록합니다.
  - **사전 조회**: **새로운 문제가 발생하거나 기존 로직을 수정하기 전, 반드시 `docs/troubleshooting.md`를 먼저 읽고 과거에 왜 이런 결정을 내렸는지 배경을 파악한 후 개선 작업을 진행**해야 합니다. 과거 결정을 모르고 되돌리는 회귀(Regression) 오류를 절대 방지합니다.





