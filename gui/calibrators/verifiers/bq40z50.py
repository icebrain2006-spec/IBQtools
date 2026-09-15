import struct

def verify_bq40z50(runner, show_voltage: bool, show_temp: bool) -> bool:
    """Post-calibration verification for BQ40Z50/BQ4050 series ICs."""
    v_bat_val = None
    v_pack_val = None
    data_ok = False

    active_cells = getattr(runner, 'active_cells', 4)
    if hasattr(runner, 'active_cells_map') and runner.ch in runner.active_cells_map:
        active_cells = runner.active_cells_map[runner.ch]
    elif hasattr(runner, 'detect_firmware_and_config'):
        try:
            runner.detect_firmware_and_config()
            active_cells = getattr(runner, 'active_cells', 4)
            if not hasattr(runner, 'active_cells_map'):
                runner.active_cells_map = {}
            runner.active_cells_map[runner.ch] = active_cells
        except Exception as e:
            if hasattr(runner, '_log'):
                runner._log(f"DA Config detect error: {e}")

    data1 = runner.read_mac_block([0x71, 0x00])
    if data1 and len(data1) >= 14:
        data_ok = True
        v_c1 = struct.unpack_from('<H', data1, 2)[0]
        v_c2 = struct.unpack_from('<H', data1, 4)[0]
        v_c3 = struct.unpack_from('<H', data1, 6)[0]
        v_c4 = struct.unpack_from('<H', data1, 8)[0]
        
        # Voltage pattern fallback refinement for 2S / 3S packs
        if v_c1 > 1000 and v_c2 > 1000:
            if v_c3 == 0 and v_c4 == 0:
                active_cells = 2
            elif v_c3 > 1000 and v_c4 == 0:
                active_cells = 3
        
        if not hasattr(runner, 'active_cells_map'):
            runner.active_cells_map = {}
        runner.active_cells_map[runner.ch] = active_cells
        runner.active_cells = active_cells

        if show_voltage:
            v_cells = [v_c1, v_c2, v_c3, v_c4]
            for i in range(4):
                if i < active_cells:
                    runner.emit_result(f"V_Cell {i+1}", f"V_Cell {i+1}", "-", v_cells[i], suffix=" mV")
                else:
                    if hasattr(runner, 'row_signal'):
                        runner.row_signal.emit(f"V_Cell {i+1}", runner.ch, "-", "INFO")
                    if hasattr(runner, 'cal_log_buffer') and runner.ch in runner.cal_log_buffer:
                        runner.cal_log_buffer[runner.ch][f"V_Cell {i+1}"] = {'value': 'N/A', 'range': 'Excluded (2S)'}

        v_bat_val = struct.unpack_from('<H', data1, 10)[0]
        v_pack_val = struct.unpack_from('<H', data1, 12)[0]
    else:
        if show_voltage:
            for i in range(4):
                if i < active_cells:
                    cmd = 0x3F - i
                    val = runner.smbus_read_word(cmd)
                    if val:
                        data_ok = True
                        v_cell = struct.unpack('<H', bytes(val))[0]
                        runner.emit_result(f"V_Cell {i+1}", f"V_Cell {i+1}", "-", v_cell, suffix=" mV")
                else:
                    if hasattr(runner, 'row_signal'):
                        runner.row_signal.emit(f"V_Cell {i+1}", runner.ch, "-", "INFO")

        val_pack = runner.smbus_read_word(0x09)
        if val_pack:
            data_ok = True
            v_p = struct.unpack('<H', bytes(val_pack))[0]
            v_bat_val = v_p
            v_pack_val = v_p

    if show_voltage and (v_pack_val is not None and v_bat_val is not None):
        ch_limits = runner.limits_per_ch.get(runner.ch, runner.limits) if hasattr(runner, 'limits_per_ch') else runner.limits
        diff_min, diff_max = ch_limits.get("V_Pack - V_Bat Diff", ch_limits.get("V_Pack / V_Bat Diff", (-20.0, 20.0)))
        v_diff = v_pack_val - v_bat_val
        force_diff_fail = (v_diff < diff_min or v_diff > diff_max)
        if force_diff_fail:
            runner._log(f"FAIL: V_Pack/V_Bat diff={v_diff}mV exceeds limit ({diff_min}, {diff_max})")
        runner.emit_result("V_Pack", "V_Pack", "-", v_pack_val, suffix=" mV", force_fail=force_diff_fail)
        runner.emit_result("V_Bat", "V_Bat", "-", v_bat_val, suffix=" mV", force_fail=force_diff_fail)

    data2 = runner.read_mac_block([0x72, 0x00])
    if data2 and len(data2) >= 16:
        int_temp = round(struct.unpack_from('<H', data2, 2)[0] * 0.1 - 273.15, 1)
        ts1 = round(struct.unpack_from('<H', data2, 4)[0] * 0.1 - 273.15, 1)
        ts2 = round(struct.unpack_from('<H', data2, 6)[0] * 0.1 - 273.15, 1)
        ts3 = round(struct.unpack_from('<H', data2, 8)[0] * 0.1 - 273.15, 1)
        ts4 = round(struct.unpack_from('<H', data2, 10)[0] * 0.1 - 273.15, 1)
        
        if show_temp:
            if runner.targets.get("inttempc_en", False):
                runner.emit_result("Int Temp", "Int Temp (0x0072)", "-", int_temp, suffix=" °C")
            if runner.targets.get("ts1tempc_en", False):
                runner.emit_result("TS1 Temp", "TS1 Temp (0x0072)", "-", ts1, suffix=" °C")
            if runner.targets.get("ts2tempc_en", False):
                runner.emit_result("TS2 Temp", "TS2 Temp (0x0072)", "-", ts2, suffix=" °C")
            if runner.targets.get("ts3tempc_en", False):
                runner.emit_result("TS3 Temp", "TS3 Temp (0x0072)", "-", ts3, suffix=" °C")
            if runner.targets.get("ts4tempc_en", False):
                runner.emit_result("TS4 Temp", "TS4 Temp (0x0072)", "-", ts4, suffix=" °C")
            
    # Read and Dump 0x4000 DataFlash Block Content
    df_4000 = runner.read_mac_block([0x00, 0x40])
    if df_4000:
        runner._log(runner.format_df4000_breakdown(df_4000, f"CH{runner.ch} POST-VERIFY 0x4000 DF BLOCK"))

    if not data_ok and not data2:
        return False
    return True
