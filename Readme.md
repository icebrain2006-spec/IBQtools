# IBQtools (v2.0)

RP2040-Zero 메인 컨트롤러 및 PySide6 기반의 multi-board BQ40Z50/BQ78350 펌웨어 프로그래머 및 캘리브레이션 통합 솔루션입니다.

---

## 1. 실행 및 셋업 (Build & Run)
- **Primary Run**: `uv run python main.py` (또는 `gui/main.py`)
- **Setup**: `uv sync`
- **Install Package**: `uv add <package>`
- **RP2040 Firmware Build**: Pico SDK 기반 C/C++ CMake 빌드 (`mkdir build && cd build && cmake .. && make`)

---

## 2. 하드웨어 스펙 및 리퍼런스
1. **IBT-014 모듈**: 하드웨어 회로도 ([schematic.pdf](file:///d:/WinApp/python/IBQtools/reference/schematic.pdf))
2. **RP2040-Zero**: MCU 핀맵 및 규격 ([RP2040_Zero.pdf](file:///d:/WinApp/python/IBQtools/reference/RP2040_Zero.pdf))

---

## 3. 프로젝트 구조 (v2.0 모듈화)
```text
├── reference/           # 하드웨어 회로도 및 칩 데이터시트
├── firmware_rp2040/     # RP2040-Zero C/C++ SDK 기반 PIO SMBus & Relay 제어 소스코드
├── gui/                 # PC용 Python GUI 프로그램 소스코드 (PySide6 / Qt6)
│   ├── dialogs/         # 다이얼로그 모듈 (CSV 뷰어, Limit 설정)
│   ├── widgets/         # RP2040 위젯 및 서브 Mixins (board_mixins/)
│   ├── workers/         # 비동기 QThread 워커 (플래싱, 스캔, 모니터링, FW 업데이트)
│   ├── tabs/            # 6개 주요 기능 탭 모듈 및 Mixins
│   ├── protocol.py      # 패킷 생성, CRC16 및 파싱 프로토콜 유틸
│   ├── strings.py       # 딕셔너리 기반 다국어 (i18n, 영어/한글) 중앙 맵
│   ├── styles.py        # 중앙 디자인 토큰 (Colors) 및 QSS 템플릿 (Styles)
│   ├── config.py        # QSettings 앱 설정 관리
│   ├── utils.py         # 로그 파일 I/O 및 포트 검사 유틸
│   └── main.py          # GUI 메인 엔트리포인트 윈도우
├── AGENTS.md            # 개발 가이드 및 AI 에이전트 개발 규칙
└── Readme.md            # 프로젝트 개요 및 구조 문서
```

---

## 4. RP2040-Zero 펌웨어 주요 기능
- **PIO 기반 6CH SMBus 통신**: 50ms 타임아웃 지원 및 개별 채널 동시 통신
- **Serial 명령 인터페이스**: PC 패킷 전송(STX/ETX/CRC16) 및 응답 파싱
- **Direct Master Command**: SMBus Read/Write, Block Read/Write, ROM Mode 탈출
- **SLFS 오프로드 플래싱**: `.slfs` 파일 수신 후 RP2040 내부에서 6CH BQ IC 동시 펌웨어 업로드
- **6CH Relay 제어**: 보드별 6채널 스위칭 릴레이 제어
- **LED & 착탈 모니터링**: 상태 알림 LED 및 칩 이탈 감지 시그널링

---

## 5. PC GUI (PySide6 Qt6) 주요 기능

### 5.1. SN & Inspection Tab (다중 보드 시리얼 검사)
- 최대 4개 보드 x 6채널 = **총 24개 채널 동시 펌웨어 프로그래밍 및 검증**
- BQ40Z50 시리얼 번호 및 생산일자 자동 생성/기입 및 검증
- 실시간 프로그레스 바, 상태 표시 및 CSV 작업 로그 저장 (`work_log.csv`)

### 5.2. Calibration Tab (전압/온도/전류 캘리브레이션)
- BQ78350 및 BQ40Z50 칩셋 정밀 오프셋/게인 측정 및 캘리브레이션
- `LimitsDialog` 기반 항목별 Pass/Fail 임계값(Min/Max) 관리 및 레지스트리 동기화

### 5.3. SLFS Flasher Tab (배치 펌웨어 업로드)
- 자동 RP2040 보드 스캔 및 배치 `.slfs` 펌웨어 전송
- 비동기 콘솔 로깅 및 진행률 트래킹

### 5.4. Manual I2C Debug Tab (수동 명령 제어)
- 임의의 HEX 명령 바이너리 프레임 구성 및 비동기 수신 콘솔 분석

### 5.5. CSV to SLFS Log Exporter Tab
- 캡처된 CSV 로그 뷰어, 날짜/SN/결과 실시간 필터링 및 로그 내보내기

### 5.6. Options Tab (자동 업데이트 및 설정)
- GitHub 연동 RP2040 최신 release 스캔 및 BOOTSEL 오토 플래싱
- 퀵 스타트 단축키 (Space 등) 설정 및 로그 경로 지정

### 5.7. Mini Relay Controller Window
- 독립 툴 윈도우 기반 6채널 릴레이 토글 비동기 제어

---

## 6. 테스트 및 검증
- 구문 및 교차 참조 검증: `uv run python -m py_compile <files...>`
- 비동기 Concurrency: 메인 UI 스레드 블로킹 방지를 위해 모든 시리얼 입출력은 `QThread` 워커로 이전되어 관리됩니다.