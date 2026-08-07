import serial, time, struct

def make_packet(cmd, payload=b""):
    length = len(payload)
    packet = bytearray([0x02, (length >> 8) & 0xFF, length & 0xFF, cmd])
    packet.extend(payload)
    return packet

def smbus_pec_calculate(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07
            else:
                crc = crc << 1
            crc &= 0xFF
    return crc

ch = 6
addr = 0x0B

with serial.Serial("COM6", 115200, timeout=0.1) as ser:
    # 0x2D 0x00 to toggle CAL_EN
    data_bytes = [0x2D, 0x00]
    tx_data = bytearray([0x44, len(data_bytes)]) + bytearray(data_bytes)
    pec_data = bytearray([(addr << 1)]) + tx_data
    tx_data.append(smbus_pec_calculate(pec_data))
    
    payload = struct.pack('<BBBB', ch, addr, len(tx_data), 0) + tx_data
    ser.write(make_packet(0x23, payload)) # CMD_I2C_RAW = 0x23
    time.sleep(0.5)
    print("CAL_EN toggled (hopefully disabled).")
