class UIStrings:
    """Centralized UI Text Strings and Dictionary-Based i18n for IBQtools."""

    CURRENT_LANG = "en"  # Default language: "en" or "ko"

    _STRINGS = {
        "en": {
            # --- Main Window & Tabs ---
            "BTN_OPEN_RELAY": "🚀 Open Mini\nRelay Controller",
            "TAB_SN_INSPECTION": "BQ FW Programmer",
            "TAB_CALIBRATION": "Calibration",
            "TAB_MANUAL_DEBUG": "Manual I2C Debug",
            "TAB_SLFS_FLASHER": "RP2040 SLFS Upload",
            "TAB_CSV_VIEWER": "CSV to SLFS",
            "TAB_OPTIONS": "Options",
            "TAB_AUTO_CYCLE": "Auto Cycle && Logger",
            "LBL_WIRING_POWER": "⚡ Relay CH1: Power Supply (Charger)",
            "LBL_WIRING_LOAD": "⚡ Relay CH2: Electronic Load (Discharge)",
            "LBL_WIRING_SMBUS": "🔌 SMBus: CH1 (Single)",
            "BTN_START_AUTO": "▶ AUTO START",
            "BTN_START_LOG": "▶ LOG ONLY",
            "BTN_STOP": "■ STOP",
            "STEP_CHARGING": "CHARGING",
            "STEP_CHARGED": "CHARGED (Resting)",
            "STEP_DISCHARGING": "DISCHARGING",
            "STEP_DISCHARGED": "DISCHARGED (Resting)",
            "LBL_CYCLES": "Cycles:",
            "LBL_CURRENT_STEP": "Current Step:",
            "LBL_STEP_TIME": "Step Time:",

            # --- Common Actions & Buttons ---
            "BTN_REFRESH": "Refresh",
            "BTN_BROWSE": "Browse...",
            "BTN_VIEWER": "Viewer",
            "BTN_CLOSE": "Close",
            "BTN_CANCEL": "Cancel",
            "BTN_SAVE_CLOSE": "Save && Close",
            "BTN_SET_LIMITS": "Set Limits",
            "BTN_START_ALL": "START ALL",
            "BTN_STOP_ALL": "STOP ALL",
            "BTN_QUICK_START": "Quick Start",
            "BTN_SERIAL_CHECK": "SERIAL CHECK",

            # --- Common Labels ---
            "LBL_COM_PORT": "COM Port:",
            "LBL_TARGET_IC": "Target IC:",
            "LBL_TARGET_CH": "Target Channel:",
            "LBL_OVERALL_RESULT": "Overall Result",
            "LBL_SEARCH": "Search:",
            "LBL_STATUS": "Status:",
            "LBL_READY": "Ready.",
            "LBL_PARAM": "Parameter",
            "LBL_MIN_OFFSET": "Min (or -Offset)",
            "LBL_MAX_OFFSET": "Max (or +Offset)",

            # --- Options Tab ---
            "GRP_DATA_LOGGING": "Data Logging Settings (CSV)",
            "GRP_ERROR_DEBUG": "Error & Debug Settings",
            "GRP_PRODUCTION": "Production Settings",
            "GRP_FW_UPDATE": "RP2040 Firmware Auto-Update",
            "LBL_WORK_LOG": "Work Log:",
            "LBL_CAL_LOG": "Calibration Log:",
            "LBL_ERROR_LOG": "Error Log (TXT):",
            "LBL_CONSOLE_OUTPUT": "Console Output:",
            "LBL_QUICK_START_HOTKEY": "Quick Start Hotkey:",
            "LBL_GITHUB_REPO": "GitHub Repository:",
            "CB_GLOBAL_DEBUG_LOG": "Show Detailed / Debug Logs in Console (All Tabs)",
            "CB_SAVE_ERROR_LOG": "Save Error Logs to File",
            "LBL_GDRIVE_STORAGE": "Google Drive Storage:",
            "BTN_SET_GDRIVE": "Set Paths to Google Drive",
            "BTN_MIGRATE_LOGS": "Migrate Local Logs to Drive",
            "MSG_GDRIVE_APPLIED": "Log storage paths have been set to Google Drive:",
            "MSG_MIGRATE_SUCCESS": "Local logs migration result:",
            "BTN_SAVE_SETTINGS": "Save Settings",
            "BTN_CHECK_UPDATE": "Check Update",
            "BTN_DOWNLOAD_FLASH": "Download && Flash",
            "BTN_FLASH_LOCAL": "Flash Local .uf2",
            "TOOLTIP_HOTKEY": "Click here and press the desired hotkey combination (e.g., Space)",
            "TOOLTIP_QUICK_START": "Enable this to trigger 'START ALL' using the configured hotkey",
            "PH_GITHUB_REPO": "e.g. username/repository",

            # --- Relay Tab ---
            "GRP_CONNECTION": "Connection",
            "GRP_RELAY_CONTROL": "Relay Control",
            "LBL_COM": "COM:",

            # --- SLFS Flasher Tab ---
            "GRP_SLFS_BATCH": "SLFS Batch Upload (Multi-Board)",
            "LBL_DETECTED_BOARDS": "Detected RP2040 Boards:",
            "BTN_SCAN_BOARDS": "SCAN BOARDS",
            "BTN_STOP_SCAN": "STOP SCAN",
            "BTN_UPLOAD_ALL": "UPLOAD TO ALL",
            "BTN_STOP_UPLOAD": "STOP UPLOAD",
            "PH_SELECT_SLFS": "Select .slfs file...",

            # --- Manual Tab ---
            "GRP_MANUAL_TARGET": "Target Device Settings",
            "GRP_MANUAL_COMMAND": "I2C / SMBus Command Configuration",
            "LBL_CHANNEL": "Channel (1~6):",
            "LBL_I2C_ADDR": "I2C Address (Hex):",
            "LBL_CMD_MODE": "Command Mode:",
            "LBL_REGISTER": "Cmd / Register (Hex):",
            "LBL_WRITE_DATA": "Write Data (Hex):",
            "LBL_EXPECTED_RX": "Expected RX Bytes:",
            "CHK_USE_PEC": "Use PEC",
            "BTN_SEND_COMMAND": "SEND COMMAND",
            "BTN_CLEAR_CONSOLE": "Clear Console",
            "PH_WRITE_DATA": "e.g. 12 34 (space separated hex)",

            # --- CSV to SLFS Converter Tab ---
            "GRP_IC_CONFIG": "IC Configuration",
            "LBL_IC_TYPE": "IC Type:",
            "LBL_VERSION": "Version:",
            "GRP_FILE_PATHS": "File Paths",
            "LBL_INPUT_CSV": "Input CSV:",
            "LBL_OUTPUT_SLFS": "Output SLFS:",
            "BTN_CONVERT_SLFS": "CONVERT TO SLFS",
            "BTN_CONVERTING": "CONVERTING...",

            # --- Master / SN Checker Panel ---
            "GRP_MASTER_CONFIG": "Master Configuration",
            "GRP_VERIFY_TARGETS": "Verification Targets",
            "LBL_NUM_BOARDS": "Number of Boards (1-4):",
            "LBL_LOOP_COUNT": "Loop Count:",

            # --- Calibration Tab ---
            "GRP_VOLTAGE_CALIB": "Voltage Calibration",
            "GRP_TEMP_CALIB": "Temperature Calibration",
            "GRP_CURRENT_CALIB": "Current Calibration",
            "LBL_RELAY_DELAY": "Relay Delay (ms):",
            "BTN_START_VOLTAGE": "Start Voltage",
            "BTN_START_TEMP": "Start Temp",
            "BTN_START_CURRENT": "Start Current",
            "NOTE_CHANNEL_TOGGLE": "Note: Click on a table header (CH1~CH6) to activate/deactivate channels.",
        },
        "ko": {
            # --- Main Window & Tabs ---
            "BTN_OPEN_RELAY": "🚀 미니 릴레이\n컨트롤러 열기",
            "TAB_SN_INSPECTION": "BQ 펌웨어 프로그래머",
            "TAB_CALIBRATION": "캘리브레이션",
            "TAB_MANUAL_DEBUG": "수동 I2C 디버깅",
            "TAB_SLFS_FLASHER": "RP2040 SLFS 업로드",
            "TAB_CSV_VIEWER": "CSV 로그 뷰어",
            "TAB_OPTIONS": "옵션 및 설정",
            "TAB_AUTO_CYCLE": "자동 사이클 및 로거",
            "LBL_WIRING_POWER": "⚡ 릴레이 CH1: 충전 전원 (파워서플라이)",
            "LBL_WIRING_LOAD": "⚡ 릴레이 CH2: 전자 부하 (방전기)",
            "LBL_WIRING_SMBUS": "🔌 SMBus: CH1 (단일 채널)",
            "BTN_START_AUTO": "▶ 자동 사이클 시작",
            "BTN_START_LOG": "▶ 로깅만 시작",
            "BTN_STOP": "■ 정지",
            "STEP_CHARGING": "충전 중",
            "STEP_CHARGED": "충전 완료 (휴지)",
            "STEP_DISCHARGING": "방전 중",
            "STEP_DISCHARGED": "방전 완료 (휴지)",
            "LBL_CYCLES": "사이클:",
            "LBL_CURRENT_STEP": "현재 단계:",
            "LBL_STEP_TIME": "단계 경과 시간:",

            # --- Common Actions & Buttons ---
            "BTN_REFRESH": "새로고침",
            "BTN_BROWSE": "찾아보기...",
            "BTN_VIEWER": "뷰어",
            "BTN_CLOSE": "닫기",
            "BTN_CANCEL": "취소",
            "BTN_SAVE_CLOSE": "저장 및 닫기",
            "BTN_SET_LIMITS": "임계값 설정",
            "BTN_START_ALL": "전체 시작",
            "BTN_STOP_ALL": "전체 정지",
            "BTN_QUICK_START": "빠른 시작",
            "BTN_SERIAL_CHECK": "시리얼 점검",

            # --- Common Labels ---
            "LBL_COM_PORT": "COM 포트:",
            "LBL_TARGET_IC": "대상 IC:",
            "LBL_TARGET_CH": "대상 채널:",
            "LBL_OVERALL_RESULT": "종합 결과",
            "LBL_SEARCH": "검색:",
            "LBL_STATUS": "상태:",
            "LBL_READY": "준비됨.",
            "LBL_PARAM": "파라미터",
            "LBL_MIN_OFFSET": "최소값 (또는 -오프셋)",
            "LBL_MAX_OFFSET": "최대값 (또는 +오프셋)",

            # --- Options Tab ---
            "GRP_DATA_LOGGING": "데이터 로깅 설정 (CSV)",
            "GRP_ERROR_DEBUG": "오류 및 디버그 설정",
            "GRP_PRODUCTION": "생산 설정",
            "GRP_FW_UPDATE": "RP2040 펌웨어 자동 업데이트",
            "LBL_WORK_LOG": "작업 로그:",
            "LBL_CAL_LOG": "캘리브레이션 로그:",
            "LBL_ERROR_LOG": "오류 로그 (TXT):",
            "LBL_CONSOLE_OUTPUT": "콘솔 출력:",
            "LBL_QUICK_START_HOTKEY": "빠른 시작 단축키:",
            "LBL_GITHUB_REPO": "GitHub 저장소:",
            "CB_GLOBAL_DEBUG_LOG": "콘솔에 상세/디버그 로그 표시 (전체 탭 공통)",
            "CB_SAVE_ERROR_LOG": "오류 로그를 파일에 저장",
            "LBL_GDRIVE_STORAGE": "구글 드라이브 저장소:",
            "BTN_SET_GDRIVE": "구글 드라이브 경로로 일괄 설정",
            "BTN_MIGRATE_LOGS": "로컬 로그 구글 드라이브로 이전",
            "MSG_GDRIVE_APPLIED": "로그 저장 경로가 구글 드라이브로 설정되었습니다:",
            "MSG_MIGRATE_SUCCESS": "로컬 로그 이전 결과:",
            "BTN_SAVE_SETTINGS": "설정 저장",
            "BTN_CHECK_UPDATE": "업데이트 확인",
            "BTN_DOWNLOAD_FLASH": "다운로드 및 플래싱",
            "BTN_FLASH_LOCAL": "로컬 .uf2 플래싱",
            "TOOLTIP_HOTKEY": "여기를 클릭하고 원하시는 단축키 조합을 누르세요 (예: Space)",
            "TOOLTIP_QUICK_START": "설정한 단축키를 눌러 '전체 시작'을 실행하도록 활성화합니다",
            "PH_GITHUB_REPO": "예: 사용자명/저장소명",

            # --- Relay Tab ---
            "GRP_CONNECTION": "연결",
            "GRP_RELAY_CONTROL": "릴레이 제어",
            "LBL_COM": "COM:",

            # --- SLFS Flasher Tab ---
            "GRP_SLFS_BATCH": "SLFS 배치 업로드 (다중 보드)",
            "LBL_DETECTED_BOARDS": "감지된 RP2040 보드:",
            "BTN_SCAN_BOARDS": "보드 스캔",
            "BTN_STOP_SCAN": "스캔 중지",
            "BTN_UPLOAD_ALL": "전체 업로드",
            "BTN_STOP_UPLOAD": "업로드 중지",
            "PH_SELECT_SLFS": ".slfs 파일을 선택하세요...",

            # --- Manual Tab ---
            "GRP_MANUAL_TARGET": "대상 장치 설정",
            "GRP_MANUAL_COMMAND": "I2C / SMBus 명령 구성",
            "LBL_CHANNEL": "채널 (1~6):",
            "LBL_I2C_ADDR": "I2C 주소 (Hex):",
            "LBL_CMD_MODE": "명령 모드:",
            "LBL_REGISTER": "명령어 / 레지스터 (Hex):",
            "LBL_WRITE_DATA": "쓰기 데이터 (Hex):",
            "LBL_EXPECTED_RX": "수신 예상 바이트:",
            "CHK_USE_PEC": "PEC 사용",
            "BTN_SEND_COMMAND": "명령 전송",
            "BTN_CLEAR_CONSOLE": "콘솔 지우기",
            "PH_WRITE_DATA": "예: 12 34 (띄어쓰기 구분 Hex)",

            # --- CSV to SLFS Converter Tab ---
            "TAB_CSV_VIEWER": "CSV to SLFS 변환",
            "GRP_IC_CONFIG": "IC 설정",
            "LBL_IC_TYPE": "IC 종류:",
            "LBL_VERSION": "버전:",
            "GRP_FILE_PATHS": "파일 경로",
            "LBL_INPUT_CSV": "입력 CSV:",
            "LBL_OUTPUT_SLFS": "출력 SLFS:",
            "BTN_CONVERT_SLFS": "SLFS로 변환",
            "BTN_CONVERTING": "변환 중...",

            # --- Master / SN Checker Panel ---
            "GRP_MASTER_CONFIG": "마스터 설정",
            "GRP_VERIFY_TARGETS": "검증 대상",
            "LBL_NUM_BOARDS": "보드 개수 (1-4):",
            "LBL_LOOP_COUNT": "반복 횟수:",

            # --- Calibration Tab ---
            "GRP_VOLTAGE_CALIB": "전압 캘리브레이션",
            "GRP_TEMP_CALIB": "온도 캘리브레이션",
            "GRP_CURRENT_CALIB": "전류 캘리브레이션",
            "LBL_RELAY_DELAY": "릴레이 지연 (ms):",
            "BTN_START_VOLTAGE": "전압 측정 시작",
            "BTN_START_TEMP": "온도 측정 시작",
            "BTN_START_CURRENT": "전류 측정 시작",
            "NOTE_CHANNEL_TOGGLE": "참고: 테이블 헤더(CH1~CH6)를 클릭하여 채널을 활성화/비활성화할 수 있습니다.",
        }
    }

    # Backward Compatibility Attribute Aliases
    BTN_REFRESH = _STRINGS["en"]["BTN_REFRESH"]
    BTN_START_VOLTAGE = _STRINGS["en"]["BTN_START_VOLTAGE"]
    BTN_START_TEMP = _STRINGS["en"]["BTN_START_TEMP"]
    BTN_START_CURRENT = _STRINGS["en"]["BTN_START_CURRENT"]
    BTN_START_ALL = _STRINGS["en"]["BTN_START_ALL"]
    BTN_QUICK_START = _STRINGS["en"]["BTN_QUICK_START"]
    BTN_SET_LIMITS = _STRINGS["en"]["BTN_SET_LIMITS"]
    BTN_SAVE_CLOSE = _STRINGS["en"]["BTN_SAVE_CLOSE"]
    BTN_CANCEL = _STRINGS["en"]["BTN_CANCEL"]
    LBL_COM_PORT = _STRINGS["en"]["LBL_COM_PORT"]
    LBL_TARGET_IC = _STRINGS["en"]["LBL_TARGET_IC"]
    LBL_TARGET_CH = _STRINGS["en"]["LBL_TARGET_CH"]
    LBL_OVERALL_RESULT = _STRINGS["en"]["LBL_OVERALL_RESULT"]
    LBL_RELAY_DELAY = _STRINGS["en"]["LBL_RELAY_DELAY"]
    NOTE_CHANNEL_TOGGLE = _STRINGS["en"]["NOTE_CHANNEL_TOGGLE"]
    TOOLTIP_QUICK_START = _STRINGS["en"]["TOOLTIP_QUICK_START"]
    GRP_VOLTAGE_CALIB = _STRINGS["en"]["GRP_VOLTAGE_CALIB"]
    GRP_TEMP_CALIB = _STRINGS["en"]["GRP_TEMP_CALIB"]
    GRP_CURRENT_CALIB = _STRINGS["en"]["GRP_CURRENT_CALIB"]

    @classmethod
    def set_language(cls, lang: str):
        """Set application active language ('en' or 'ko')."""
        if lang in cls._STRINGS:
            cls.CURRENT_LANG = lang

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        """Get translated UI string for the current language."""
        lang_dict = cls._STRINGS.get(cls.CURRENT_LANG, cls._STRINGS["en"])
        return lang_dict.get(key, default or cls._STRINGS["en"].get(key, key))
