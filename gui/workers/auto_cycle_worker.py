"""Background worker thread for RP2040 SMBus telemetry polling and Auto Cycle state machine."""

import time
import struct
import serial
from PySide6.QtCore import QThread, Signal

from gui.protocol import (
    CMD_RELAY_SET, CMD_SMBUS_CMD, RESP_OK, PROTOCOL_STX,
    make_packet, parse_response
)
from gui.tabs.auto_cycle_mixins.constants import (
    SBS_COMMANDS, STEP_CHARGING, STEP_CHARGED,
    STEP_DISCHARGING, STEP_DISCHARGED
)


class AutoCycleWorker(QThread):
    """Worker thread that polls BQ SMBus data and drives the 4-step Auto Cycle state machine."""

    data_updated = Signal(dict)
    step_changed = Signal(str, int, int)      # step_name, cycle_count, elapsed_sec
    relay_state_changed = Signal(bool, bool)  # power_on, load_on
    log_message = Signal(str)
    finished_cycle = Signal(str)

    def __init__(self, port_name: str, poll_interval: float = 1.0,
                 auto_cycle: bool = False, target_cycles: int = 1, parent=None):
        super().__init__(parent)
        self.port_name = port_name
        self.poll_interval = max(0.5, poll_interval)
        self.auto_cycle = auto_cycle
        self.target_cycles = target_cycles
        self.running = False
        
        self.ser = None
        self.ch = 1           # RP2040 Channel 1
        self.bq_addr = 0x0B   # Default BQ40Z50 7-bit I2C Address

        # State Machine Variables
        self.current_step = STEP_CHARGING
        self.cycle_count = 0
        self.step_start_time = time.time()
        self.power_on = False
        self.load_on = False
        self.in_step_init = False
        self.delay_trigger_time = None

    def run(self):
        """Main worker polling and control loop."""
        self.running = True
        try:
            self.ser = serial.Serial(self.port_name, 115200, timeout=0.1)
        except Exception as e:
            self.finished_cycle.emit(f"Failed to open port {self.port_name}: {e}")
            return

        self.log_message.emit(f"Connected to RP2040 on {self.port_name}")
        
        if self.auto_cycle:
            self.current_step = STEP_CHARGING
            self.cycle_count = 0
            self.step_start_time = time.time()
            self.in_step_init = False
            self.delay_trigger_time = None
            self.log_message.emit("Auto Cycle Started.")
        else:
            self.log_message.emit("Continuous Logging Started.")

        try:
            while self.running:
                loop_start = time.time()

                # 1. Read SMBus Data
                telemetry = self._read_all_telemetry()
                if telemetry:
                    self.data_updated.emit(telemetry)

                    # 2. Advance Auto Cycle State Machine if enabled
                    if self.auto_cycle:
                        self._process_state_machine(telemetry)

                # Sleep to match polling interval
                elapsed = time.time() - loop_start
                sleep_dur = max(0.05, self.poll_interval - elapsed)
                self.msleep(int(sleep_dur * 1000))

        except Exception as e:
            self.log_message.emit(f"Worker Exception: {e}")
        finally:
            self._set_relay(False, False)
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.finished_cycle.emit("Cycle or Logging Stopped.")

    def stop(self):
        """Requests graceful thread stop."""
        self.running = False

    def set_relay_manual(self, power_on: bool, load_on: bool):
        """Sets relay states directly from UI."""
        self._set_relay(power_on, load_on)

    def _set_relay(self, power_on: bool, load_on: bool):
        """Sends CMD_RELAY_SET to RP2040. CH1=Power (Bit 0), CH2=Load (Bit 1)."""
        if not self.ser or not self.ser.is_open:
            return
        mask = (1 if power_on else 0) | (2 if load_on else 0)
        pkt = make_packet(CMD_RELAY_SET, bytes([mask]))
        self.ser.write(pkt)
        time.sleep(0.02)
        resp = self.ser.read(64)
        self.power_on = power_on
        self.load_on = load_on
        self.relay_state_changed.emit(power_on, load_on)

    def _smbus_read_word(self, cmd_reg: int):
        """Reads 16-bit word from BQ IC."""
        if not self.ser or not self.ser.is_open:
            return None
        payload = bytes([self.ch, self.bq_addr, cmd_reg, 1, 2, 0, 0])
        self.ser.write(make_packet(CMD_SMBUS_CMD, payload))
        time.sleep(0.015)
        rx = self.ser.read(64)
        cmd, data = parse_response(rx)
        if cmd is not None and isinstance(data, (bytes, bytearray)) and len(data) >= 3 and data[0] == RESP_OK:
            return data[2:4]
        return None

    def _read_mac_block(self, sub_cmd_bytes: bytes):
        """Writes 2-byte sub-command to 0x44, then reads block from 0x44."""
        if not self.ser or not self.ser.is_open:
            return None
        # Write sub-command
        tx_payload = bytes([self.ch, self.bq_addr, 0x44, 0, len(sub_cmd_bytes), 0, 0]) + sub_cmd_bytes
        self.ser.write(make_packet(CMD_SMBUS_CMD, tx_payload))
        time.sleep(0.02)
        self.ser.read(64)

        # Read response block
        rx_payload = bytes([self.ch, self.bq_addr, 0x44, 1, 32, 0, 0])
        self.ser.write(make_packet(CMD_SMBUS_CMD, rx_payload))
        time.sleep(0.02)
        rx = self.ser.read(64)
        cmd, data = parse_response(rx)
        if cmd is not None and isinstance(data, (bytes, bytearray)) and len(data) >= 3 and data[0] == RESP_OK:
            length = data[1]
            return data[2:2+length]
        return None

    def _read_all_telemetry(self) -> dict:
        """Reads SBS standard telemetry and 14 status registers."""
        res = {"timestamp": time.time()}

        # 1. SBS Commands
        for name, (cmd, unit, is_signed) in SBS_COMMANDS.items():
            raw = self._smbus_read_word(cmd)
            if raw and len(raw) == 2:
                val = int.from_bytes(raw, byteorder='little', signed=is_signed)
                if unit == "degC":
                    val = round((val / 10.0) - 273.15, 1)
                elif unit == "hex":
                    val = f"0x{val:04X}"
                res[name] = val

        # 2. MFA Blocks for Cell Voltages and 14 Registers
        # OperationStatus (0x0054)
        op = self._read_mac_block(bytes([0x54, 0x00]))
        res["Operation_A_HIGH"] = op[3] if op and len(op) > 3 else 0
        res["Operation_A_LOW"]  = op[2] if op and len(op) > 2 else 0
        res["Operation_B_HIGH"] = op[5] if op and len(op) > 5 else 0
        res["Operation_B_LOW"]  = op[4] if op and len(op) > 4 else 0

        # ChargingStatus (0x0055)
        chg = self._read_mac_block(bytes([0x55, 0x00]))
        res["Charging_HIGH"] = chg[4] if chg and len(chg) > 4 else 0
        res["Charging_LOW"]  = chg[3] if chg and len(chg) > 3 else 0

        # GaugingStatus & ITStatus (0x0056)
        gauge = self._read_mac_block(bytes([0x56, 0x00]))
        res["Gauging"] = gauge[2] if gauge and len(gauge) > 2 else 0
        res["IT_HIGH"] = gauge[4] if gauge and len(gauge) > 4 else 0
        res["IT_LOW"]  = gauge[3] if gauge and len(gauge) > 3 else 0

        # SafetyStatus (0x0051)
        safe = self._read_mac_block(bytes([0x51, 0x00]))
        res["Safety_AB_HIGH"] = safe[3] if safe and len(safe) > 3 else 0
        res["Safety_AB_LOW"]  = safe[2] if safe and len(safe) > 2 else 0
        res["Safety_CD_HIGH"] = safe[5] if safe and len(safe) > 5 else 0
        res["Safety_CD_LOW"]  = safe[4] if safe and len(safe) > 4 else 0

        # Lstatus (ITStatus bit 4 or Mfg info)
        res["Lstatus"] = gauge[3] & 0x0F if gauge and len(gauge) > 3 else 0

        # DAStatus1 (0x0071): Cell Voltages 1~4
        da1 = self._read_mac_block(bytes([0x71, 0x00]))
        if da1 and len(da1) >= 10:
            res["Cell1"] = int.from_bytes(da1[2:4], 'little')
            res["Cell2"] = int.from_bytes(da1[4:6], 'little')
            res["Cell3"] = int.from_bytes(da1[6:8], 'little')
            res["Cell4"] = int.from_bytes(da1[8:10], 'little')

        # Key Flags for State Machine
        res["VCT"]  = bool(res["Charging_LOW"] & 0x80)
        res["REST"] = bool(res["IT_LOW"] & 0x01)
        res["FD"]   = bool(res["Gauging"] & 0x01)
        res["FC"]   = bool(res["Gauging"] & 0x02)
        res["CUV"]  = bool(res["Safety_AB_LOW"] & 0x01)
        return res

    def _process_state_machine(self, data: dict):
        """Executes the 4-step Auto Cycle state machine."""
        now = time.time()
        elapsed_sec = int(now - self.step_start_time)
        self.step_changed.emit(self.current_step, self.cycle_count, elapsed_sec)

        # Step 1: CHARGING
        if self.current_step == STEP_CHARGING:
            if not self.in_step_init:
                self._set_relay(True, False)
                self.in_step_init = True
                self.delay_trigger_time = None
                self.log_message.emit("[Step] CHARGING: Power ON, Load OFF")

            if data.get("VCT", False):
                if self.delay_trigger_time is None:
                    self._set_relay(False, False)
                    self.delay_trigger_time = now
                    self.log_message.emit("[Step] VCT detected! Power OFF. Waiting 10s cooldown...")
                elif now - self.delay_trigger_time >= 10.0:
                    self._transition_to(STEP_CHARGED)

        # Step 2: CHARGED (Resting)
        elif self.current_step == STEP_CHARGED:
            if not self.in_step_init:
                self._set_relay(False, False)
                self.in_step_init = True
                self.delay_trigger_time = None
                self.log_message.emit("[Step] CHARGED: Resting. Waiting for REST bit...")

            if data.get("REST", False):
                if self.delay_trigger_time is None:
                    self.delay_trigger_time = now
                    self.log_message.emit("[Step] REST bit detected! Resting 30s before discharge...")
                elif now - self.delay_trigger_time >= 30.0:
                    self._transition_to(STEP_DISCHARGING)

        # Step 3: DISCHARGING
        elif self.current_step == STEP_DISCHARGING:
            if not self.in_step_init:
                self._set_relay(False, True)
                self.in_step_init = True
                self.delay_trigger_time = None
                self.log_message.emit("[Step] DISCHARGING: Power OFF, Load ON")

            if data.get("FD", False) and data.get("CUV", False):
                if self.delay_trigger_time is None:
                    self._set_relay(False, False)
                    self.delay_trigger_time = now
                    self.log_message.emit("[Step] FD + CUV detected! Load OFF. Waiting 30s cooldown...")
                elif now - self.delay_trigger_time >= 30.0:
                    self._transition_to(STEP_DISCHARGED)

        # Step 4: DISCHARGED (Resting)
        elif self.current_step == STEP_DISCHARGED:
            if not self.in_step_init:
                self._set_relay(False, False)
                self.in_step_init = True
                self.delay_trigger_time = None
                self.log_message.emit("[Step] DISCHARGED: Resting. Waiting for REST bit...")

            if data.get("REST", False):
                if self.delay_trigger_time is None:
                    self.delay_trigger_time = now
                    self.log_message.emit("[Step] REST bit detected! Resting 30s before next cycle...")
                elif now - self.delay_trigger_time >= 30.0:
                    self.cycle_count += 1
                    self.log_message.emit(f"Completed Cycle {self.cycle_count}/{self.target_cycles}")
                    if self.cycle_count >= self.target_cycles:
                        self.log_message.emit("Target cycles reached. Auto Cycle Completed!")
                        self.running = False
                    else:
                        self._transition_to(STEP_CHARGING)

    def _transition_to(self, next_step: str):
        """Transitions state machine to the next step."""
        self.current_step = next_step
        self.step_start_time = time.time()
        self.in_step_init = False
        self.delay_trigger_time = None
