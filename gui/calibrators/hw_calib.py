import time
import struct

ERR_STAGE_MAP = {
    0xE102: "Stage 2 (CAL_EN check FAIL)",
    0xE104: "Stage 4 (Raw ADC Sampling FAIL - 0 samples)",
    0xE105: "Stage 5 (ADC Average is 0)",
    0xE106: "Stage 6 (0x4000 Block Write/Cache FAIL)",
}

BQ_DF_TO_STUDIO_CONV = 3.714528
CMD_CALIB_RUN = 0x60
CMD_CALIB_STATUS = 0x61
RESP_OK = 0x00

class HWCalibratorMixin:
    """Mixin class providing RP2040 hardware calibration sequence execution and status parsing."""

    def _build_calib_payload(self, mode_name, ch_mask) -> bytes:
        """Builds CMD_CALIB_RUN payload bytes containing channel mask, mode code, and target values."""
        mode_code = 0 if mode_name == "voltage" else (1 if mode_name == "current" else 2)
        payload_bytes = bytearray([ch_mask, mode_code])
        for ch in range(1, 7):
            ch_t = self.targets_per_ch.get(ch, self.targets)
            if mode_name == "current":
                tc1 = int(abs(ch_t.get('currentma', -2000)))
                tpk = 0
                tbt = 0
            else:
                tc1 = int(ch_t.get('cell1mv', 3200))
                tpk = int(ch_t.get('packmv', 12780))
                tbt = int(ch_t.get('batmv', 12780))
            payload_bytes.extend(struct.pack(">HHH", tc1, tpk, tbt))
            if ch in self.channels:
                if mode_name == "current":
                    self._log(f"    [DEBUG Target CH{ch}] Current={tc1}mA")
                else:
                    self._log(f"    [DEBUG Target CH{ch}] Cell1={tc1}mV, Pack={tpk}mV, Bat={tbt}mV")
        return bytes(payload_bytes)

    def _unpack_ch_status_payload(self, st_resp, idx):
        """Unpacks 25-byte per-channel status block from CMD_CALIB_STATUS response."""
        cell1_g = struct.unpack('<H', st_resp[idx:idx+2])[0]; idx += 2
        pack_g = struct.unpack('<H', st_resp[idx:idx+2])[0]; idx += 2
        bat_g = struct.unpack('<H', st_resp[idx:idx+2])[0]; idx += 2
        ch_succ_val = st_resp[idx]; idx += 1
        
        raw_c1_adc = struct.unpack('<H', st_resp[idx:idx+2])[0] if idx + 2 <= len(st_resp) else 0; idx += 2
        raw_pack_adc = struct.unpack('<H', st_resp[idx:idx+2])[0] if idx + 2 <= len(st_resp) else 0; idx += 2
        raw_bat_adc = struct.unpack('<H', st_resp[idx:idx+2])[0] if idx + 2 <= len(st_resp) else 0; idx += 2
        raw_bytes = st_resp[idx:idx+18] if idx + 18 <= len(st_resp) else b""; idx += 18
        
        return (cell1_g, pack_g, bat_g, ch_succ_val, raw_c1_adc, raw_pack_adc, raw_bat_adc, raw_bytes), idx

    def _handle_current_calib_results(self, ch_status_map, cc_adc_map, cc_calc_map):
        """Reads back DataFlash 0x4000 block for active channels after current calibration and emits results."""
        for ch in self.channels:
            if ch_status_map.get(ch, False):
                self.ch = ch
                df_b = self.read_mac_block([0x00, 0x40])
                if df_b and len(df_b) >= 16:
                    self._log(f"    [CH{ch} 0x4000 RAW READ BACK ({len(df_b)}b)] {bytes(df_b).hex(' ')}")
                    base = 2 if (len(df_b) >= 18 and df_b[0] == 0x00 and df_b[1] == 0x40) else 0
                    cc_gain_read = struct.unpack_from('<f', df_b, base + 6)[0]
                    cap_gain_read = struct.unpack_from('<f', df_b, base + 10)[0]
                    mohm_read = BQ_DF_TO_STUDIO_CONV / cc_gain_read if (cc_gain_read > 0.1 and cc_gain_read < 20.0) else 0.959
                    
                    calc_gain = cc_calc_map.get(ch, 0.0)
                    calc_mohm = BQ_DF_TO_STUDIO_CONV / calc_gain if calc_gain != 0 else 0
                    avg_cc = cc_adc_map.get(ch, 0)
                    
                    self._log(f"    [CH{ch} RP2040 HW Result] PASS -> Avg CC ADC: {avg_cc}, CC Gain: {cc_gain_read:.6f}, Shunt Resistor: {mohm_read:.3f} mOhm")
                    self._log(self.format_df4000_breakdown(df_b, f"CH{ch} 4. AFTER CURRENT CALIBRATION 0x4000 DF BLOCK"))
                    
                    self.emit_result("CC Gain", "CC Gain (mOhm)", f"{mohm_read:.3f}", mohm_read, is_gain=True)
                    self.emit_result("Capacity Gain", "Capacity Gain (mOhm)", f"{mohm_read:.3f}", mohm_read, is_gain=True)

    def _parse_calib_status_response(self, st_resp, mode_name, ch_status_map, run_mode):
        """Parses CMD_CALIB_STATUS (state==2 DONE) response payload and emits results to UI."""
        active_channels = st_resp[2]
        err_channels = st_resp[3]
        self._log(f"    [DEBUG RAW RESP] len={len(st_resp)}, hex={bytes(st_resp).hex(' ')}")
        idx = 4
        cc_adc_map = {}
        cc_calc_map = {}

        for ch in range(1, 7):
            unpacked, idx = self._unpack_ch_status_payload(st_resp, idx)
            cell1_g, pack_g, bat_g, ch_succ_val, raw_c1_adc, raw_pack_adc, raw_bat_adc, raw_bytes = unpacked

            ch_succ = (ch_succ_val == 1)
            if ch in self.channels:
                is_err = (err_channels & (1 << (ch - 1))) != 0
                ch_status_map[ch] = ch_status_map.get(ch, True) and ch_succ and not is_err
                cc_adc_map[ch] = struct.unpack('<h', struct.pack('<H', cell1_g))[0]
                cc_calc_map[ch] = pack_g / 1000.0
                self._log(f"    [DEBUG CH{ch}] cell1_g={cell1_g}, pack_g={pack_g}, bat_g={bat_g}, ch_succ_val={ch_succ_val}, is_err={is_err}")

                if len(raw_bytes) > 0 and mode_name == "voltage":
                    self._log(f"    [CH{ch} RAW 0xF081 BLOCK] Hex={bytes(raw_bytes).hex(' ')}")
                    self._log(f"    [CH{ch} RAW ADC AVG] Cell1_ADC={raw_c1_adc}, Pack_ADC={raw_pack_adc}, Bat_ADC={raw_bat_adc}")

                if ch_status_map[ch] and mode_name != "current":
                    self.ch = ch
                    self._log(f"    [CH{ch} RP2040 HW Result] PASS -> Cell1 Gain: {cell1_g}, Pack Gain: {pack_g}, Bat Gain: {bat_g}")
                    df_b = self.read_mac_block([0x00, 0x40])
                    if df_b:
                        self._log(self.format_df4000_breakdown(df_b, f"CH{ch} 2. AFTER VOLTAGE CALIBRATION 0x4000 DF BLOCK"))
                    self.emit_result("Cell 1 Gain", "Cell 1 Gain", str(cell1_g), cell1_g, is_gain=True)
                    self.emit_result("Pack Gain", "Pack Gain", str(pack_g), pack_g, is_gain=True)
                    self.emit_result("Bat Gain", "Bat Gain", str(bat_g), bat_g, is_gain=True)
                    if run_mode != "all":
                        self.post_verify()
                elif not ch_status_map[ch]:
                    stage_desc = ERR_STAGE_MAP.get(cell1_g, f"Unknown Stage Error 0x{cell1_g:04X}")
                    if cell1_g == 0xE102:
                        rx_len = pack_g & 0xFF
                        b0 = (pack_g >> 8) & 0xFF
                        b1 = bat_g & 0xFF
                        b2 = (bat_g >> 8) & 0xFF
                        self._log(f"    [CH{ch} RP2040 HW Result] FAIL -> Reason: {stage_desc} | SMBus Resp Len={rx_len}, Bytes=[{b0:02X} {b1:02X} {b2:02X}]")
                    else:
                        self._log(f"    [CH{ch} RP2040 HW Result] FAIL -> Reason: {stage_desc} (err_mask={bin(err_channels)})")
        
        if mode_name == "current":
            self._handle_current_calib_results(ch_status_map, cc_adc_map, cc_calc_map)

    def _run_hw_calibration_phase(self, modes_to_run, ch_mask, ch_status_map, run_mode) -> bool:
        """Executes RP2040 hardware calibration sequence across requested modes."""
        calib_done = False
        for mode_name in modes_to_run:
            self._log(f"\n--- Executing Hardware Calibration Mode: {mode_name.upper()} ---")

            # Pre-calibration 0x4000 DF Dump Checkpoint
            for ch in self.channels:
                old_c = self.ch
                self.ch = ch
                df_pre = self.read_mac_block([0x00, 0x40])
                if df_pre:
                    stage_tag = "1. BEFORE VOLTAGE" if mode_name == "voltage" else "3. BEFORE CURRENT"
                    self._log(self.format_df4000_breakdown(df_pre, f"CH{ch} {stage_tag} CALIBRATION 0x4000 DF BLOCK"))
                self.ch = old_c

            # Set Relay state: OFF for Voltage mode, ON for Current mode
            relay_mask = ch_mask if mode_name == "current" else 0
            self._set_relay(mode_name == "current", mask=relay_mask)
            time.sleep(0.3)

            # Pre-calibration load current safety check for Current mode
            if mode_name == "current":
                valid_ch_mask = 0
                for ch in self.channels:
                    ch_in_b = ((ch - 1) % 6) + 1
                    if not (ch_mask & (1 << (ch_in_b - 1))):
                        continue
                    
                    old_ch = getattr(self, 'ch', ch)
                    self.ch = ch
                    if hasattr(self, 'ser_map'):
                        board_idx = ((ch - 1) // 6) + 1
                        if board_idx in self.ser_map:
                            self.ser = self.ser_map[board_idx]
                    
                    ch_t = self.targets_per_ch.get(ch, self.targets) if hasattr(self, 'targets_per_ch') and self.targets_per_ch else self.targets
                    target_ma = int(ch_t.get('currentma', -2000))
                    
                    # Read Present Current via SBS Command 0x0A (int16 signed mA) with fast retry polling
                    actual_current = 0
                    for retry in range(4):
                        cur_bytes = self.smbus_read_word(0x0A)
                        if cur_bytes and len(cur_bytes) >= 2:
                            actual_current = struct.unpack('<h', bytes(cur_bytes))[0]
                        else:
                            actual_current = 0
                        
                        if target_ma > -500 or actual_current <= -200:
                            break
                        time.sleep(0.15)
                    
                    self._log(f"    [CH{ch} Pre-Check] Target: {target_ma}mA, Measured Current: {actual_current}mA")
                    
                    # If target is load current (e.g. <= -500mA) and actual measured current > -200mA (no load current flowing)
                    if target_ma <= -500 and actual_current > -200:
                        self._log(f"    [CH{ch} ERROR] Current Cal ABORTED! Measured current ({actual_current}mA) is > -200mA. Equipment disconnected or load OFF!")
                        ch_status_map[ch] = False
                        if hasattr(self, 'emit_result'):
                            self.emit_result("CC Gain", "CC Gain (mOhm)", "0", 0, is_gain=True, force_fail=True)
                            self.emit_result("Capacity Gain", "Capacity Gain (mOhm)", "0", 0, is_gain=True, force_fail=True)
                    else:
                        valid_ch_mask |= (1 << (ch_in_b - 1))
                        
                    self.ch = old_ch

                ch_mask = valid_ch_mask
                if ch_mask == 0:
                    self._log("    [ERROR] No active channels with valid load current (all > -200mA). Aborting current calibration.")
                    self._set_relay(False, mask=0)
                    return False

            payload_bytes = self._build_calib_payload(mode_name, ch_mask)
            self._log(f"--- Sending Hardware Calibration Command to RP2040 ({mode_name.upper()} mode, Channels: {self.channels}) ---")
            
            # Send CMD_CALIB_RUN (0x60) packet
            cmd, resp = self._send_cmd(CMD_CALIB_RUN, payload_bytes)
            if not isinstance(resp, (bytes, bytearray)) or len(resp) == 0 or resp[0] != RESP_OK:
                err_code = resp[0] if isinstance(resp, (bytes, bytearray)) and len(resp) > 0 else resp
                self._log(f"Error: RP2040 rejected hardware calibration start command for {mode_name}. (Resp Code: {err_code}, Cmd: {cmd})")
                return False

            # Poll CMD_CALIB_STATUS (0x61) until state becomes 2 (DONE) or 3 (ERROR)
            for _ in range(60): # Max 6 seconds poll timeout
                if not self._running: break
                time.sleep(0.1)
                
                st_cmd, st_resp = self._send_cmd(CMD_CALIB_STATUS, b"")
                if isinstance(st_resp, (bytes, bytearray)) and st_resp[0] == RESP_OK:
                    state = st_resp[1]
                    if state == 2: # DONE
                        calib_done = True
                        self._parse_calib_status_response(st_resp, mode_name, ch_status_map, run_mode)
                        break
                    elif state == 3: # ERROR state from RP2040
                        err_channels = st_resp[3]
                        self._log(f"    [RP2040 HW Result] RP2040 returned ERROR state (err_mask={bin(err_channels)})")
                        break
                else:
                    self._log(f"    [DEBUG] Poll status response: cmd={st_cmd}, resp={st_resp}")

            # Ensure Relays are turned OFF after Current mode
            if mode_name == "current":
                self._set_relay(False, mask=0)

        return calib_done
