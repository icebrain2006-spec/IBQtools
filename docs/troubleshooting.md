# BQ40Z50 Multi-Board Updater - Troubleshooting & Decision History

이 문서는 프로젝트 개발 및 유지보수 과정에서 발생한 하드웨어/펌웨어/소프트웨어 문제와 그 근본 원인, 해결 방법, 그리고 해당 해결책을 채택한 의사결정 배경을 기록하는 히스토리 문서입니다.
**새로운 문제 발생 시 코드를 수정하기 전, 반드시 이 문서의 과거 해결 내역과 설계 의도를 먼저 검토해야 합니다.**

---

## [Issue #01] BQ40Z50 펌웨어 업데이트 시작 시 Line 8에서 즉시 에러 중단 (`err_code = -11`)

* **발생 일자**: 2026-10-15
* **영향 컴포넌트**: `firmware_rp2040/src/bq_updater/bq_updater.c`, `gui/updater_thread.py`
* **에러 로그**:
  ```text
  [STATUS OK] state=3, line=8/2100, active=0x01, err_mask=0x01, err_code=-11
  [CRITICAL] Updater Error Code: -11
  ```

### 1. 현상 및 근본 원인
* **Line 8 명령어**: `W: 16 44 02 00 0F 41` (ManufacturerBlockAccess를 통한 롬(BootROM) 모드 진입 명령)
* **원인**:
  1. 이전 테스트 중단 등으로 인해 배터리 칩이 **이미 롬 모드(ROM Mode)에 진입해 있는 상태**였음.
  2. 칩이 이미 롬 모드에 있을 때는 일반 모드 전용 명령어인 `0x44`(`ManufacturerBlockAccess`)가 지원되지 않아 칩이 `NACK (0x0402)`를 반환함.
  3. RP2040의 SLFS 실행기(`bq_updater.c`)는 `W:` 쓰기 명령에서 NACK가 오면 즉시 해당 채널을 에러(`error_channels |= ch_mask`)로 처리하고 -11로 중단함.

### 2. 해결 방법 및 검증
* **조치**:
  1. 플래싱 시작 전 칩이 이미 롬 모드인지(`0x0D` 레지스터 응답 여부) 점검.
  2. 만약 롬 모드에 갇혀 있다면 탈출 명령(`W: 16 08 11`)을 보내 일반 Application 모드로 복귀시킨 후 플래싱을 시작하도록 처리.
  3. 일반 모드 상태에서는 `Line 4, 6(Unseal) -> Line 8(ROM 진입) -> Line 10(ROM ID 확인)`이 100% 정상 작동함을 하드웨어 검증 완료.

### 3. 의사결정 배경 및 주의사항 (Decision Context)
* SLFS 파일의 첫 부분에는 반드시 Unseal 키와 롬 진입 명령(`0x44`)이 필요하지만, 칩이 이미 롬 모드인 상태에서 재실행될 가능성을 항상 고려해야 함.
* 칩이 롬 모드일 때는 SBS 명령(0x1B Date, 0x1C SN)도 읽히지 않고 더미 값(`0x17 0x17`)을 반환하므로, 사전 진단 시 0x0D 레지스터 확인이 필수적임.

---

## [Issue #02] SLFS 플래싱 완료 후 날짜/시리얼이 2026-10-15가 아닌 `1991-08-23, SN 5911`로 표시되는 현상

* **발생 일자**: 2026-10-15
* **영향 컴포넌트**: `gui/utils.py` (`convert_csv_to_slfs`), `reference/TEMPP/`

### 1. 현상 및 근본 원인
* **현상**: `09.slfs`로 플래싱 성공 후 칩의 SBS 데이터를 읽었을 때 제조일자가 `2026-10-15`가 아닌 `1991-08-23 (0x1717)`로 출력됨.
* **원인**:
  1. BQ40Z50 펌웨어 플래싱은 **[1] Instruction Flash(프로그램 코드)**와 **[2] DataFlash(설정/날짜/시리얼/캘리브레이션)**의 2단계로 구성됨.
  2. 정상 풀 데이터인 `07.csv`(1,960블록, 6.8만 라인)에는 블록 31에 DataFlash 주소 `0x4060` (제조사 `ENERTECH`, 날짜 `0x4F 0x5D`, 시리얼 `0x12 0x00`)이 온전히 존재함.
  3. 반면 `09.csv`(1,047블록, 3.9만 라인)는 BQ Studio에서 다운로드 캡처 시 DataFlash 영역 쓰기가 시작되기 전 조기 종료된 **반쪽짜리 불완전 캡처 파일**이었음.
  4. DataFlash가 쓰여지지 않고 초기화(Erase) 상태로 남아 기본값인 `0x17 0x17` (5911 -> 계산 시 1991-08-23)이 읽혔던 것임.

### 2. 해결 방법 및 검증
* **조치**:
  1. CSV 변환 시 불완전한 파일(DataFlash 누락)과 정상 풀 데이터(3,500라인 이상)의 구분 기준 정립.
  2. 로직 분석기 노이즈로 섞인 가짜 주소(`0x08`, `0x18` 등) 필터링 로직 추가.
  3. 첫 `0x44` 명령이 단독으로 캡처된 경우 풀 롬 진입 패킷(`02 00 0F 41`)으로 자동 정규화.
  4. 최소 딜레이 `X: 2` 보장 및 10ms 단위 올림으로 플래시 안정 기록 시간 확보.

### 3. 의사결정 배경 및 주의사항 (Decision Context)
* 차후 새로운 배터리 모델의 로직 캡처 CSV를 생성할 때, 반드시 BQ Studio에서 펌웨어 다운로드 게이지가 100% 완료되고 DataFlash 쓰기까지 끝난 후 캡처를 저장해야 함.
* 변환 결과 라인 수가 3,000줄 이하인 경우 DataFlash 누락 여부를 의심하고 사전 점검해야 함.

---

## [Issue #03] 다채널 연속 플래싱 시 `line=최대라인/최대라인, state=1` 상태로 멈추는 현상

* **발생 일자**: 2026-10-16
* **영향 컴포넌트**: `firmware_rp2040/src/bq_updater/bq_updater.c`, `gui/workers/updater_worker.py`

### 1. 현상 및 근본 원인
* **현상**: 1~2회는 정상 동작하다가 다시 Start 시 1번 줄부터 올라가지 않고 즉시 `line=3520/3520, state=1`에 머무르며 진행되지 않음.
* **원인**:
  1. 3개 채널 동시 플래싱 종료 시(마지막 `W: 16 08 11` 리부팅 단계), 칩들이 동시 리셋되면서 I2C 버스 락업(SCL/SDA Low) 또는 Core 1이 정상 대기 루프로 복귀하지 못하고 Hang 발생.
  2. PC에서 Start 명령 송신 시 Core 0은 `state=1`로 세팅하고 Core 1에 FIFO를 쐈으나, Core 1이 깨어나지 못해 `current_line`이 0으로 리셋되지 않고 이전 최대 라인에 갇힘.

### 2. 해결 방법 및 주의사항
* **조치**:
  1. 하드웨어적 리셋: RP2040 USB 케이블 탈착으로 버스 락업 해제.
  2. 소프트웨어적 방어: Start 호출 전 명시적 `STOP` 전송 및 이전 상태 클리어 안전장치 적용.
---

## [Issue #04] 프로젝트 폴더 삭제/업데이트 시 캘리브레이션 및 작업 로그(work_log, cal_log) 유실 문제

* **발생 일자**: 2026-11-02
* **영향 컴포넌트**: `gui/config.py`, `gui/gdrive_utils.py`, `gui/tabs/options_tab.py`, `gui/utils.py`, `gui/calibrators/utils.py`

### 1. 현상 및 근본 원인
* **현상**: 버전 업데이트 과정에서 기존 프로젝트 폴더(`IBQtools`)를 통째로 삭제하고 재설치할 때마다 `work_log.csv` 및 `cal_log.csv`가 함께 삭제되어 작업 이력 관리가 불가능했던 문제.
* **원인**:
  1. 기존 설정 기본값이 상대 경로(`"work_log.csv"`, `"cal_log.csv"`)로 하드코딩되어 있어 프로그램 실행 디렉토리(프로젝트 루트)에 파일이 생성됨.
  2. Google Drive Desktop(DriveFS) 환경이 설치되어 있음에도 프로젝트 외부의 안전한 영구 저장소 경로로 자동 연동되는 로직이 부재함.

### 2. 해결 방법 및 검증
* **조치**:
  1. **Google Sheets 클라우드 웹훅 실시간 업로드 (`gui/gsheet_logger.py`)**:
     - Google Apps Script Web App 연동을 통해 PC의 특정 드라이브 마운트 여부와 무관하게 모든 PC에서 구글 시트 웹 링크(URL)로 직접 행(row)을 실시간 추가(append)하는 비동기 전송 파이프라인 구축.
     - Work_log 및 Cal_log 링크로 자동 분기 전송되어 클라우드 스프레드시트에 영구 보존.
  2. **Google Drive 감지 유틸리티 (`gui/gdrive_utils.py`) 구축**:
     - Windows 레지스트리(`DriveFS/Share/SyncTargets`) 및 드라이브 경로를 자동 스캔하여 사내 공용 디렉토리(`D:\icebrain2006\내 드라이브\IB_Product_Log\IBQtools`)를 최우선 감지하도록 구현.
     - 미설치 환경 대비 `~/Documents/IBQtools_Log` 자동 Fallback 지원.
     - 기존 프로젝트 루트의 로그를 원클릭으로 구글 드라이브 대상 파일과 중복 없이 병합/복사하는 `migrate_all_local_logs()` 기능 구현.
  2. **기본 경로 스마트화 (`gui/config.py`)**:
     - 상대 경로이거나 초기 설정 시 자동으로 Google Drive 절대 경로를 반환하여 프로젝트 폴더 삭제와 무관하게 보존.
  3. **디렉토리 자동 생성 방어 코드 (`gui/utils.py`, `gui/calibrators/utils.py`)**:
     - 파일 쓰기 전 `os.makedirs(os.path.dirname(path), exist_ok=True)` 방어 처리로 대상 폴더가 없더라도 즉시 자동 생성.
  4. **Options 탭 UI 편의성 및 모듈화**:
     - Google Drive 감지 상태 표시, [구글 드라이브로 설정], [로컬 로그 이전] 버튼 추가.
     - `OptionsFwUpdateMixin`, `OptionsGDriveSyncMixin`으로 믹스인 분리하여 300줄 한도 엄격 준수.

### 3. 의사결정 배경 및 주의사항 (Decision Context)
* 사용자 PC에 여러 개의 구글 드라이브 계정(`icebrain2006`, `Supplysn81` 등)이 존재하므로, 타 프로젝트(`HDQ_Reader` 등)와 통일성을 위해 `IB_Product_Log` 폴더가 존재하는 계정(`icebrain2006`)을 1순위로 자동 매칭하도록 설계함.
* 사용자가 직접 Browse로 다른 경로를 설정한 경우 그 설정을 존중하며, 상대 경로로 설정되어 프로젝트 폴더 내부에 격리되는 것만 방지함.
