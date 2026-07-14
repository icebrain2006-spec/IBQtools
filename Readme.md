# IBQtools

## 1. 스펙
본 문서는 RP2040-Zero를 이용한 IBQ Tool 개발 문서를 작성하는 곳입니다.

## 2. 하드웨어
1. IBT-014 모듈을 사용 ([schematic.pdf](file:///d:/WinApp/python/IBQtools/Reference_Data/schematic.pdf))
2. RP2040-Zero를 사용 ([RP2040_Zero.pdf](file:///d:/WinApp/python/IBQtools/Reference_Data/RP2040_Zero.pdf))

## 3. 프로젝트 구조 (권장)
```
├── Reference_Data/      # 하드웨어 회로도 및 칩 데이터시트
├── firmware/            # RP2040-Zero C/C++ SDK 기반 펌웨어 소스코드
├── gui/                 # PC용 Python GUI 프로그램 소스코드
├── AGENTS.md            # 개발 가이드 및 AI 에이전트 규칙
└── Readme.md            # 프로젝트 개요 문서
```

## 4. RP2040-Zero 펌웨어
### 4.1. C/C++ 펌웨어
### 4.2. 기능
- **4.2.1.** PIO를 이용한 6CH SMBus 통신
- **4.2.2.** Serial 통신을 통한 PC와의 통신
- **4.2.3.** Serial 통신을 통한 Firmware Update 기능
- **4.2.4.** Serial 통신을 통한 SMBus Master로서 기능 모두 구현 (read, write, read block, write block, 기타 특수 명령 등)
- **4.2.5.** SMBus 통신의 불량이 발생되면 PC에 즉시 보고 (기본 통신 타임아웃 50ms, 조정 가능)
- **4.2.6.** 6CH Relay 제어 기능
- **4.2.7.** SLFS 파일의 RP2040으로 업로드 및 SLFS 파일을 이용한 6CH 동시 BQ Firmware Update 기능
- **4.2.8.** 위의 기능을 사용하기 편하게 하기 위한 파이썬 브릿지 코드

## 5. PC용 GUI
### 5.1. 파이썬(Python) 기반 개발
### 5.2. PAGE를 이용한 GUI 디자인 (Program, Calibration)
### 5.3. SLFS 파일의 RP2040 업로드 기능
### 5.4. RP2040-Zero 펌웨어 완료 후 자세한 기능 작성 예정

## 6. 테스트 계획
### 6.1. PIO를 이용한 6CH SMBus 개별 통신 테스트 (읽기 반복, 쓰기 반복)
### 6.2. 2CH 동시 통신 테스트 (읽기 반복, 쓰기 반복)
### 6.3. 펌웨어 업로드 테스트 (SLFS 파일 사용)
### 6.4. 6CH 동시 펌웨어 업로드 테스트