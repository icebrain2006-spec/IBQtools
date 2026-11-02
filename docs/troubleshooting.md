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
---

## [Issue #05] BQ FW Programmer 제조사 데이터(System Data / Manufacturer Info Block A) 2블록 시리얼 쓰기 신규 기능 추가

* **발생/요청 일자**: 2026-11-02
* **영향 컴포넌트**: `gui/tabs/sn_checker_mixins/`, `gui/workers/mfg_block_writer.py`, `gui/workers/updater_worker.py`, `gui/strings.py`

### 1. 현상 및 요구 배경
* **배경**: 기존 SBS Serial(`0x1C`) 외에, BQ40Z50의 DataFlash `System Data / Manufacturer Data` 내 `Manufacturer Info Block A` (A01~A32) 영역에 2개 블록을 합쳐 16-bit 시리얼 번호(예: `0x0001 -> A02=0x00, A03=0x01`)를 쓰는 생산 공정 요구 발생.
* **핵심 요구사항**:
  1. 기존 SBS Serial 및 Date 쓰기 로직은 100% 독립 유지.
  2. 시작 블록(`A01` ~ `A31`) 지정 시, 해당 블록과 다음 블록 2개를 묶어 Big-Endian 16-bit 시리얼 분할 저장.
  3. 자동 증가(+1) 및 동일 번호 유지 기능 제공.
  4. SBS 기능과 완전히 분리된 독립 제어 보장.

### 2. 해결 방법 및 검증
* **조치**:
  1. **독립 UI 그룹박스 구성 (`master_panel_mixin.py`)**:
     - SBS 그룹 아래에 `Manufacturer Data Serial (Block A)` 전용 독립 UI 추가.
     - 시작 블록 드롭다운(`A01`~`A31`), 자동 힌트 라벨(`Used: A02 + A03`), 시작 시리얼 및 DEC/HEX 포맷, 자동 증가 체크박스 배치.
  2. **독립 상태 캐시 및 카운터 분리 (`state_cache_mixin.py`)**:
     - `QSettings` 영구 저장 분리(`ui_write_mfg_sn`, `ui_mfg_start_block`, `ui_mfg_auto_inc`, `ui_mfg_sn_fmt`, `ui_mfg_exp_sn`).
     - 작업 시작 시 SBS와 Mfg 시리얼을 각각 독립 카운터로 계산하여 충돌 방지.
  3. **전용 DataFlash Block A 드라이버 구현 (`gui/workers/mfg_block_writer.py`)**:
     - Subcommand `0x0070` 및 `0x44` ManufacturerBlockAccess 프로토콜 구현.
     - 기존 32바이트 읽기 -> 지정 인덱스(예: 1, 2)에 2바이트 덮어쓰기 -> 체크섬(0x60) 및 길이(0x61) 쓰기 -> 재독출 및 값 일치 검증 파이프라인 완성.
  5. **Work Log 및 구글 시트 연동 확장 (`append_work_log`)**:
     - `work_log.csv` 및 Google Sheets에 `Mfg_Block`(예: `A02+A03`)과 `Mfg_SN`(예: `0x0001` 또는 미사용 시 `N/A`) 컬럼을 신규 추가하여 작업 이력 추적성 확보.
  4. **순환 참조 해소 및 모듈 표준화 (`gui/i18n/`)**:
     - 300줄을 초과하던 `strings.py`를 `gui/i18n/strings_en.py`, `strings_ko.py`로 분리하여 300라인 제한 및 단일 책임 원칙 준수.
     - `board_ui_mixin`과 `fw_update_worker`의 `updater_thread` 의존성을 `gui.protocol`로 직접 연결하여 순환 참조 해결.

### 3. 의사결정 배경 및 주의사항 (Decision Context)
* TI BQ40Z50에서 Manufacturer Info Block A는 32바이트 단위 블록 쓰기 후 0x60 체크섬과 0x61 길이를 기록해야 DataFlash 플래시에 영구 반영되므로, 표준 체크섬 계산식(`0xFF - (sum & 0xFF)`)을 준수하여 작성함.
* SBS 시리얼과 Manufacturer 시리얼을 하나의 데이터 구조로 합치지 않고 튜플 내 독립 딕셔너리로 분리하여, 향후 다른 블록(Block B, Block C) 확장 시에도 기존 SBS 검증 파이프라인에 영향을 주지 않도록 설계함.

---

## [Issue #06] GitHub Push 시 100MB 초과 대용량 파일 거절 에러 (pre-receive hook declined)

* **발생 일자**: 2026-11-02
* **영향 컴포넌트**: Git Repository History (
eference/Log_20231222_BP25_Learning.csv, .gitignore)

### 1. 현상 및 근본 원인
* **현상**: 2.0.29 배포 버전 생성 후 원격 저장소(origin/release/v2.1)로 git push 실행 시 GitHub pre-receive hook에서 다음과 같이 푸시 거부:
  `	ext
  remote: error: File reference/Log_20231222_BP25_Learning.csv is 138.14 MB; this exceeds GitHub's file size limit of 100.00 MB
  ! [remote rejected] release/v2.1 -> release/v2.1 (pre-receive hook declined)
  `
* **원인**: 과거 eat(auto_cycle) 커밋(d56bdb) 시 138MB 용량의 참조 데이터셋 CSV가 저장소 이력에 포함되었고, 해당 파일이 포함된 브랜치를 GitHub로 푸시하면서 100MB 파일 크기 제한 정책에 위배됨.

### 2. 해결 방법 및 검증
* **조치**:
  1. **임시 롤백 브랜치 확보**: 작업 착수 전 ackup/release-v2.1-before-filter 브랜치를 생성하여 100% 원상 복구 경로 확보.
  2. **이력 필터링**: git filter-branch --index-filter를 통해 커밋 이력에서 
eference/Log_20231222_BP25_Learning.csv를 안전하게 제거.
  3. **로컬 파일 보존**: 디스크 상의 원본 CSV 파일은 삭제되지 않도록 유지(100% 보존).
  4. **재유입 방지**: .gitignore에 
eference/Log_*.csv 규칙을 추가하여 향후 대용량 파일이 git에 추적되지 않도록 차단.
  5. **원격 푸시 검증**: git push --dry-run 검증 후 git push -u origin release/v2.1 성공.

### 3. 의사결정 배경 및 주의사항 (Decision Context)
* 원격 저장소에 아직 
elease/v2.1 브랜치가 푸시되지 않은 상태였으므로, 로컬 이력 재작성이 타 작업자의 원격 브랜치에 충돌을 주지 않는 안전한 상태임을 사전 확인 후 진행함.
* 로컬 디스크 상의 참조 파일(Log_20231222_BP25_Learning.csv)은 학습용 레퍼런스로 사용될 수 있으므로 절대 영구 삭제하지 않고 유지함.

---

## [Issue #07] Auto Cycle & Logger SMBus 텔레메트리 누락 및 시리얼 탈조 오류

* **발생 일자**: 2026-11-02
* **영향 컴포넌트**: `gui/workers/auto_cycle_worker.py`

### 1. 현상 및 근본 원인
* **현상**:
  - Auto Start 실행 시 충전 릴레이(CH1 Power)는 정상 ON 되었으나, Live BQ Telemetry(전압, 전류, RSOC, 온도, Cell 1~4)가 전부 0으로 표시되고 CSV 로그 파일에 SBS 데이터가 빈 콤마(`,,,,`)로 기록됨.
  - 상태 레지스터 행렬에 실제 BQ IC 상태 대신 `0x01, 0x87` 등의 패킷 바이트 파편이 반복 채워지며 비트맵이 비정상 표시됨.
* **근본 원인**:
  1. **Word Read 슬라이스 오프셋 버그**: RP2040의 Word Read 응답(`[0x00, Low, High]`, 총 3바이트)에서 `data[1:3]`(2바이트)이 아닌 `data[2:4]`(1바이트)를 반환하도록 작성되어, `len(raw) == 2` 조건문에서 15개 SBS 표준 명령(Voltage, Current, RSOC 등)이 단 하나도 파싱되지 못하고 전부 누락됨.
  2. **MAC 서브커맨드 페이로드 헤더 불일치**: `_read_mac_block` 구성 시 `[ch, addr, reg, rw, len, pec]` 6바이트 뒤에 불필요한 0 바이트가 1개 더 삽입되어 7바이트가 되면서 서브커맨드(0x0054 등)가 0x5400으로 오염 전송되어 BQ IC로부터 NACK 발생.
  3. **ChargingStatus 인덱스 역전/누락**: 2바이트 데이터 블록에서 `Charging_LOW`와 `Charging_HIGH`를 `chg[2], chg[3]`이 아닌 `chg[3], chg[4]`로 슬라이스하여 `Charging_HIGH`는 0이 되고, bit 7 VCT(충전 완료) 판정이 엉뚱한 비트를 참조함.
  4. **시리얼 프레이밍 동기화 부재**: `reset_input_buffer()` 없이 단순 `time.sleep(0.015)` 및 `read(64)`로 패킷을 수신하여 통신 지연 발생 시 이전 응답 패킷 잔여 데이터가 다음 명령으로 유입되는 영구 시리얼 탈조(Desync) 발생.

### 2. 해결 방법 및 검증
* **조치**:
  1. **STX 기반 동기 통신 구현 (`_send_cmd`, `_read_packet`)**: 패킷 송신 전 버퍼를 비우고, `PROTOCOL_STX`부터 `CRC16`, `ETX`까지 완전한 패킷이 도착할 때까지 안전하게 수신하도록 일원화.
  2. **Word Read 슬라이스 수정**: `data[1:3]`으로 2바이트 Little-Endian 데이터를 정상 반환하도록 수정하여 15개 SBS 텔레메트리 복원.
  3. **정규 6바이트 MAC 헤더 및 0x44/0x00 폴백 적용**: 서브커맨드 파라미터 오프셋 교정 및 BQ IC 모드별 자동 대응.
  4. **ChargingStatus 오프셋 교정**: `chg[2]`를 LOW(VCT 비트 포함), `chg[3]`을 HIGH로 정상 매핑.
  5. **Cell 전압 폴백 추가**: `DAStatus1 (0x0071)` 실패 시 SBS `0x3F~0x3C`를 자동으로 조회하는 안전 폴백 추가.
  6. **방전 완료 판정식 정상화**: `FD and CUV`로 되어 있어 보호회로(CUV)가 터져야만 방전이 끝나던 논리적 결함을 `FD or CUV`로 정상화.

### 3. 의사결정 배경 및 주의사항 (Decision Context)
* RP2040과 PC 간의 통신은 요청-응답(Request-Response) 구조이므로 임의의 sleep-read를 사용하면 20여 개 명령이 연속 실행될 때 1개 명령 지연만으로 전체 스트림이 오염됨. 따라서 STX 패킷 프레이밍 기반 동기화가 필수적임.
