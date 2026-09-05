import struct

def verify_bq78350(runner, show_voltage: bool, show_temp: bool) -> bool:
    """Post-calibration verification for BQ78350 series ICs."""
    if show_voltage:
        for i in range(runner.active_cells):
            cmd = 0x3F - i
            val = runner.smbus_read_word(cmd)
            if val:
                val = struct.unpack('<H', bytes(val))[0]
                runner.emit_result(f"V_Cell {i+1}", f"V_Cell {i+1} (0x{cmd:02X})", "-", val, suffix=" mV")
                
        if runner.targets.get('extaveragecellmv', 0) > 0:
            v_ext = runner.smbus_read_word(0x4D)
            if v_ext:
                v_ext = struct.unpack('<H', bytes(v_ext))[0]
                runner.emit_result("V_Ext", "Ext Ave Cell (0x4D)", "-", v_ext, suffix=" mV")
                
        if runner.targets.get('vauxmv', 0) > 0:
            v_aux = runner.smbus_read_word(0x2E)
            if v_aux:
                v_aux = struct.unpack('<H', bytes(v_aux))[0]
                runner.emit_result("V_Aux", "VAux (0x2E)", "-", v_aux, suffix=" mV")
            
    if show_temp:
        int_temp_raw = runner.smbus_read_word(0x28) # InternalTemp is 0x28
        if int_temp_raw:
            val = struct.unpack('<H', bytes(int_temp_raw))[0]
            temp_c = round(val * 0.1 - 273.15, 1)
            if runner.targets.get("inttempc_en", False):
                runner.emit_result("Int Temp", "Int Temp (0x28)", "-", temp_c, suffix=" °C")
                
        for i, (name, cmd) in enumerate([("TS1", 0x5E), ("TS2", 0x5F), ("TS3", 0x60), ("TS4", 0x61)]):
            if runner.targets.get(f"{name.lower()}tempc_en", False):
                raw = runner.smbus_read_word(cmd)
                if raw:
                    val = struct.unpack('<H', bytes(raw))[0]
                    temp_c = round(val * 0.1 - 273.15, 1)
                    runner.emit_result(f"{name} Temp", f"{name} Temp (0x{cmd:02X})", "-", temp_c, suffix=" °C")
    return True
