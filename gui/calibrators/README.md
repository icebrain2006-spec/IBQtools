# IBQTools Calibration Architecture (v2.0)

This directory contains the core logic for running automated hardware-assisted calibration sequences on Texas Instruments (TI) Battery Management System (BMS) ICs (e.g., BQ40Z50, BQ78350, BQ4050, BQ34Z100, BQ40Z80).

---

## 1. Modular System Architecture

The calibration engine adopts a modular Mixin-based design architecture to maintain single responsibility and prevent monolithic code bloat.

### Directory Structure & Component Roles
- **`calib_runner.py`**: Main `CalibrationThread` orchestration entry point (inherits all Mixin classes). Manages the execution lifecycle, channel selection (CH1~CH6), and post-verification monitoring loop.
- **`hw_calib.py` (`HWCalibratorMixin`)**: Handles high-speed hardware calibration commands sent to the RP2040 Pico firmware C-engine (`CMD_HW_CALIB_START`, `CMD_HW_CALIB_POLL`).
- **`fw_detector.py` (`FWDetectorMixin`)**: Detects target IC firmware version via SMBus, automatically mapping DataFlash addresses and offsets using CSV definitions.
- **`smbus_comm.py` (`SMBusCommunicatorMixin`)**: Low-level SMBus packet framing, serial communication with RP2040, and relay control handling.
- **`utils.py`**: Shared utility functions for DataFlash 0x4000 block breakdown formatting, SMBus PEC (CRC-8) calculations, and CSV calibration log generation.
- **`dataflashs/`**: Parameter offset mapping tables (`df_bq*.csv`) per IC family and firmware version.
- **`verifiers/`**: Post-calibration verification rules and live status measurement modules.

---

## 2. Hardware-Accelerated Execution Flow

When the user triggers "Start Calibration" in the GUI:

1. **Initialization & COM Channel Setup**:
   - `CalibrationTab` collects user-defined target values (e.g., Cell voltages, Pack voltage, Current, Temperatures) and channel masks (CH1~CH6).
   - Launches `CalibrationThread` in a separate background thread (`QThread`).

2. **Firmware Detection & Offset Mapping**:
   - `FWDetectorMixin` queries device firmware version (e.g., `0x0402` -> `V4_02`).
   - Dynamically searches `dataflashs/df_<ic>_<version>.csv` to locate exact DataFlash subclass addresses (e.g., DA Configuration Offset).

3. **RP2040 Hardware Calibration Phase**:
   - Sends `CMD_HW_CALIB_START` packet over USB Serial to the RP2040 Pico.
   - The RP2040 C firmware engine handles hardware switching (Relay matrix), high-speed raw ADC sampling, Gain/Offset calculations, and DataFlash PEC-protected write-backs directly on the device.
   - `CalibrationThread` polls `CMD_HW_CALIB_POLL` until the hardware phase completes.

4. **Post-Verification & CSV Logging**:
   - Performs post-calibration measurement reads (`run_post_verify`).
   - Compares measured values against user-configured limits.
   - Writes pass/fail results and raw DataFlash breakdown logs to CSV files.

5. **Continuous Monitoring Mode**:
   - Enters background monitoring loop to continuously track channel voltages and communication stability.

---

## 3. How to Add Support for a New BQ IC

To support a new TI BMS IC:

1. **Add DataFlash CSV Mapping**:
   - Place the DataFlash parameter map CSV file under `dataflashs/` (e.g., `df_bq20z90_V1_00.csv`).
2. **Register IC Configuration in GUI**:
   - Add parameter defaults to `IC_CONFIGS` in `gui/tabs/calibration_tab.py`.
3. **Extend RP2040 Firmware Engine (If needed)**:
   - Add specific MAC commands and raw ADC offset parsers under `firmware_rp2040/src/calib_engine/`.
