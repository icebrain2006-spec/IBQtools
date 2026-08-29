import argparse
import subprocess
import struct
import os
import time

# Version: v1.0.10

UF2_MAGIC_START0 = 0x0A324655
UF2_MAGIC_START1 = 0x9E5D5157
UF2_MAGIC_END    = 0x0AB16F30
RP2040_FAMILY_ID = 0xe48bff56

PROTOCOL_STX = 0x02
PROTOCOL_ETX = 0x03
CMD_REBOOT_BOOTSEL = 0x02
RESP_OK = 0x00

def crc16_calculate(data):
    """
    RP2040 프로토콜 호환 CRC16 (MODBUS 방식 / Polynomial 0xA001) 계산.
    :param data: CRC 계산할 bytes 데이터
    :return: 16비트 정수형 CRC 값
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

def make_packet(cmd, payload):
    """
    RP2040 시리얼 패킷 생성 (STX + LEN + CMD + PAYLOAD + CRC16 + ETX).
    :param cmd: 명령어 바이트 (예: CMD_REBOOT_BOOTSEL 0x02)
    :param payload: 패킷에 실을 바이너리 페이로드
    :return: 최종 전송용 바이너리 패킷 (bytes)
    """
    total_len = 1 + len(payload)
    header = struct.pack(">B H B", PROTOCOL_STX, total_len, cmd)
    crc_data = bytes([cmd]) + payload
    crc = crc16_calculate(crc_data)
    footer = struct.pack(">H B", crc, PROTOCOL_ETX)
    return header + payload + footer

def send_bootsel_reboot(port_name):
    """
    시리얼 포트를 통해 실행 중인 RP2040에 소프트웨어 리셋 명령을 보내 BOOTSEL 모드로 전환시킴.
    :param port_name: RP2040이 연결된 시리얼 포트명 (예: COM7)
    :return: 성공 여부 (bool)
    """
    # Try importing serial dynamically so users without pyserial can still run basic make_uf2 without -port
    try:
        import serial
    except ImportError:
        print("Error: pyserial package is required to use the -port option.")
        print("Please install it (e.g., 'uv run --with pyserial ...' or 'pip install pyserial')")
        return False
        
    print(f"Connecting to RP2040 on {port_name} to trigger BOOTSEL reset...")
    try:
        ser = serial.Serial(port_name, 115200, timeout=1.0)
        ser.dtr = True
        ser.rts = True
        packet = make_packet(CMD_REBOOT_BOOTSEL, b"")
        ser.write(packet)
        time.sleep(0.1)
        ser.close()
        print("BOOTSEL reboot command sent successfully. Waiting 2.0s for mount...")
        time.sleep(2.0)
        return True
    except Exception as e:
        print(f"Failed to send boot reset command: {e}")
        return False

def bin_to_uf2(bin_path, uf2_path, target_addr=0x10000000):
    """
    컴파일된 raw binary(.bin) 데이터를 RP2040 플래시 용 UF2 포맷으로 변환.
    :param bin_path: 입력 .bin 파일 경로
    :param uf2_path: 출력 .uf2 파일 경로
    :param target_addr: RP2040 플래시 메모리 시작 주소 (기본값: 0x10000000)
    :return: 성공 여부 (bool)
    """
    if not os.path.exists(bin_path):
        print(f"Error: {bin_path} not found. Please build the project first.")
        return False
        
    with open(bin_path, "rb") as f:
        bin_data = f.read()
        
    num_bytes = len(bin_data)
    block_size = 256
    num_blocks = (num_bytes + block_size - 1) // block_size
    
    print(f"Converting {bin_path} ({num_bytes} bytes) to {uf2_path} ({num_blocks} blocks)...")
    
    with open(uf2_path, "wb") as out:
        for block_no in range(num_blocks):
            flags = 0x00002000
            addr = target_addr + block_no * block_size
            
            start = block_no * block_size
            end = start + block_size
            payload = bin_data[start:end]
            
            if len(payload) < block_size:
                payload = payload + b'\x00' * (block_size - len(payload))
                
            data_padding = b'\x00' * (476 - block_size)
            
            block = struct.pack(
                "<IIIIIIII",
                UF2_MAGIC_START0,
                UF2_MAGIC_START1,
                flags,
                addr,
                block_size,
                block_no,
                num_blocks,
                RP2040_FAMILY_ID
            )
            block += payload
            block += data_padding
            block += struct.pack("<I", UF2_MAGIC_END)
            
            out.write(block)
            
    print(f"UF2 generation successful: {uf2_path}")
    return True

def main():
    """
    메인 빌드 프로세스:
    1. (선택사항) 지정된 시리얼 포트로 BOOTSEL 소프트웨어 리셋 명령 송신
    2. cmake/ninja 명령어로 C/C++ 프로젝트 컴파일
    3. arm-none-eabi-objcopy로 .elf를 .bin으로 변환
    4. bin_to_uf2 함수를 호출하여 최종 .uf2 바이너리 생성
    """
    parser = argparse.ArgumentParser(description="Build firmware and generate UF2 with optional BOOTSEL reset")
    parser.add_argument("-port", help="Serial port of RP2040 to auto-reset to BOOTSEL mode (optional)")
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(base_dir, "build")
    
    # 1. Send soft reset if port is specified
    if args.port:
        send_bootsel_reboot(args.port)
        
    # 2. Run ninja in build directory
    print("Executing cmake build...")
    try:
        result = subprocess.run(["cmake", "--build", "."], cwd=build_dir, shell=True)
        if result.returncode != 0:
            print("Make compilation failed. Aborting UF2 creation.")
            return
    except Exception as e:
        print(f"Failed to start make: {e}")
        return
        
    elf_path = os.path.join(build_dir, "firmware.elf")
    bin_path = os.path.join(build_dir, "firmware.bin")
    uf2_path = os.path.join(build_dir, "firmware.uf2")
    
    print("Converting firmware.elf to firmware.bin using arm-none-eabi-objcopy...")
    try:
        objcopy_res = subprocess.run(
            ["arm-none-eabi-objcopy", "-O", "binary", elf_path, bin_path],
            shell=True
        )
        if objcopy_res.returncode != 0:
            print("Failed to convert ELF to BIN. Aborting UF2 creation.")
            return
    except Exception as e:
        print(f"Failed to run objcopy: {e}")
        return
    
    bin_to_uf2(bin_path, uf2_path)

if __name__ == "__main__":
    main()
