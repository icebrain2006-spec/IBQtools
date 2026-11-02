import time
import struct
import logging
from typing import Optional, Tuple

from gui.protocol import (
    make_packet, parse_response, RESP_OK,
    CMD_SMBUS_CMD, PROTOCOL_STX
)

SMBUS_ADDR_BQ = 0x0B  # Standard 7-bit SMBus Address for BQ chips (0x16 in 8-bit)


def _send_and_recv_smbus(ser, payload: bytes, timeout: float = 0.5) -> Optional[bytes]:
    """Helper to send CMD_SMBUS_CMD packet to RP2040 and wait for STX response."""
    if not ser or not ser.is_open:
        return None
        
    packet = make_packet(CMD_SMBUS_CMD, payload)
    ser.reset_input_buffer()
    ser.write(packet)
    
    start_time = time.time()
    buf = b""
    old_timeout = ser.timeout
    ser.timeout = 0.05
    try:
        while time.time() - start_time < timeout:
            rx = ser.read(128)
            if rx:
                buf += rx
            stx_idx = buf.find(PROTOCOL_STX)
            if stx_idx != -1 and len(buf) >= stx_idx + 7:
                length = struct.unpack(">H", buf[stx_idx+1:stx_idx+3])[0]
                expected_total = length + 6
                if len(buf) >= stx_idx + expected_total:
                    pkt_chunk = buf[stx_idx:stx_idx+expected_total]
                    cmd, resp = parse_response(pkt_chunk)
                    if cmd == CMD_SMBUS_CMD:
                        return resp
                    buf = buf[stx_idx+expected_total:]
    finally:
        ser.timeout = old_timeout
    return None


def read_mfg_block_a(ser, ch: int) -> Optional[bytes]:
    """
    Reads 32-byte Manufacturer Info Block A from BQ chip via Subcommand 0x0070.
    """
    # 1. Write Subcommand 0x0070 to ManufacturerBlockAccess (0x44)
    # Payload format: [ch, addr, reg, rw(0=write), len, use_pec, data_bytes...]
    subcmd_payload = bytes([ch, SMBUS_ADDR_BQ, 0x44, 0, 2, 1, 0x70, 0x00])
    resp = _send_and_recv_smbus(ser, subcmd_payload, timeout=0.3)
    if not resp or resp[0] != RESP_OK:
        return None
        
    time.sleep(0.05)
    
    # 2. Read 32-byte block from 0x44
    # Payload format: [ch, addr, reg, rw(1=read), len(32), use_pec, dummy]
    read_payload = bytes([ch, SMBUS_ADDR_BQ, 0x44, 1, 32, 1, 0])
    resp = _send_and_recv_smbus(ser, read_payload, timeout=0.5)
    if resp and resp[0] == RESP_OK and len(resp) >= 34:
        # resp[1] is length (32), resp[2:34] is the 32 bytes data
        rx_len = resp[1]
        return bytes(resp[2:2+rx_len])
    elif resp and resp[0] == RESP_OK and len(resp) >= 3:
        return bytes(resp[2:])
        
    return None


def write_mfg_block_a(ser, ch: int, data_32b: bytes) -> bool:
    """
    Writes 32-byte Manufacturer Info Block A to BQ chip with Checksum (0x60) & Length (0x61).
    """
    if len(data_32b) != 32:
        return False
        
    # Full block payload: subcommand 0x0070 (2b) + data (32b) = 34 bytes
    full_data = bytes([0x70, 0x00]) + data_32b
    
    # 1. Write block to 0x44
    # [ch, addr, reg, rw(0), len(34), use_pec(1)] + 34 bytes
    write_payload = bytes([ch, SMBUS_ADDR_BQ, 0x44, 0, len(full_data), 1]) + full_data
    resp = _send_and_recv_smbus(ser, write_payload, timeout=0.5)
    if not resp or resp[0] != RESP_OK:
        return False
        
    # 2. Compute DataFlash checksum: 0xFF - (sum(full_data) & 0xFF)
    checksum = (0xFF - (sum(full_data) & 0xFF)) & 0xFF
    
    # 3. Write Checksum to 0x60
    chk_payload = bytes([ch, SMBUS_ADDR_BQ, 0x60, 0, 1, 1, checksum])
    resp = _send_and_recv_smbus(ser, chk_payload, timeout=0.2)
    if not resp or resp[0] != RESP_OK:
        return False
        
    # 4. Write Length (34 bytes = 0x22) to 0x61
    len_payload = bytes([ch, SMBUS_ADDR_BQ, 0x61, 0, 1, 1, len(full_data)])
    resp = _send_and_recv_smbus(ser, len_payload, timeout=0.2)
    if not resp or resp[0] != RESP_OK:
        return False
        
    time.sleep(0.1)  # Allow DataFlash flash write to complete
    return True


def write_and_verify_mfg_serial(
    ser, ch: int, start_block: str, sn_val: int, fmt: str = "DEC", log_cb=None
) -> Tuple[bool, str]:
    """
    Writes 16-bit serial across 2 blocks starting at start_block (e.g. A02 -> A02, A03).
    Format: Big-Endian (0x0001 -> Block1=0x00, Block2=0x01).
    """
    def _log(msg):
        if log_cb:
            log_cb(msg)
        else:
            logging.getLogger("IBQtools").info(msg)

    try:
        blk_idx = int(start_block.upper().replace("A", "")) - 1
    except ValueError:
        return False, f"Invalid block: {start_block}"

    if blk_idx < 0 or blk_idx > 30:
        return False, f"Start block {start_block} out of range (A01~A31)"

    b1_name = f"A{blk_idx+1:02d}"
    b2_name = f"A{blk_idx+2:02d}"

    # 1. Read existing 32-byte Block A
    orig_block = read_mfg_block_a(ser, ch)
    if not orig_block or len(orig_block) < 32:
        _log(f"[CH {ch}] Failed to read Manufacturer Block A before write")
        return False, "Read Block A Failed"

    # 2. Modify target 2 bytes (Big-Endian: MSB in b1, LSB in b2)
    val_hi = (sn_val >> 8) & 0xFF
    val_lo = sn_val & 0xFF
    
    modified = bytearray(orig_block[:32])
    modified[blk_idx] = val_hi
    modified[blk_idx + 1] = val_lo

    sn_display = f"0x{sn_val:04X}" if fmt == "HEX" else str(sn_val)
    _log(f"[CH {ch}] Writing Mfg Serial: {sn_display} to {b1_name}=0x{val_hi:02X}, {b2_name}=0x{val_lo:02X}")

    # 3. Write back to chip
    ok = write_mfg_block_a(ser, ch, bytes(modified))
    if not ok:
        _log(f"[CH {ch}] Write Mfg Serial FAILED!")
        return False, "Write Block A Failed"

    # 4. Verify by reading back
    time.sleep(0.05)
    verify_block = read_mfg_block_a(ser, ch)
    if not verify_block or len(verify_block) < 32:
        _log(f"[CH {ch}] Verification read failed for Mfg Block A")
        return False, "Verify Read Failed"

    actual_hi = verify_block[blk_idx]
    actual_lo = verify_block[blk_idx + 1]
    actual_sn = (actual_hi << 8) | actual_lo

    if actual_hi == val_hi and actual_lo == val_lo:
        _log(f"[CH {ch}] Mfg Serial Verified: {sn_display} ({b1_name}=0x{actual_hi:02X}, {b2_name}=0x{actual_lo:02X}) [PASS]")
        return True, sn_display
    else:
        _log(f"[CH {ch}] Mfg Serial Mismatch! Expected: {sn_display}, Actual: 0x{actual_sn:04X} ({b1_name}=0x{actual_hi:02X}, {b2_name}=0x{actual_lo:02X}) [FAIL]")
        return False, f"Mismatch (0x{actual_sn:04X})"
