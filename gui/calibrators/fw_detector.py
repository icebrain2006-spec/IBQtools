import struct
from gui.calibrators.utils import detect_dataflash_offset, load_calibration_offsets

class FWDetectorMixin:
    """Mixin class for BQ IC firmware version detection and DataFlash configuration parsing."""

    def _read_firmware_version(self):
        """Reads BQ IC firmware version via MAC 0x0002. Returns (device, version, major, minor) or None."""
        data = self.read_mac_block([0x02, 0x00])
        
        if not data:
            self._log("Failed to detect firmware version (0x0002).")
            return None
            
        self._log(f"MAC 0x0002 Raw Read: {data.hex(' ')}")
        
        idx = self._find_header(data, [0x02, 0x00])
        if idx == -1:
            self._log("Warning: 0x0002 echo not found, using index 0")
            idx = 0
                
        if idx + 5 < len(data):
            device = struct.unpack_from('>H', data, idx + 2)[0]
            major = data[idx + 4]
            minor = data[idx + 5]
            version = (major << 8) | minor
            self._log(f"Detected Firmware: Device 0x{device:04X}, Version V{major}.{minor:02d}")
            return device, version, major, minor
        else:
            self._log("Failed to parse firmware version due to invalid length.")
            return None

    def _load_dataflash_map(self, version, major, minor):
        """Looks up DataFlash offset and loads parameter offsets dictionary."""
        offset, csv_name = detect_dataflash_offset(self.ic_name, version, "DA Configuration")
        if offset is None:
            self._log(f"Warning: Could not find DA Configuration offset for {self.ic_name} V{major}.{minor:02d}. Defaulting to 0x4000.")
            return 0x4000
        else:
            self.csv_name = csv_name
            self.df_offsets = load_calibration_offsets(csv_name)
            self._log(f"Loaded CSV: {csv_name}, DA Config Offset: {offset}")
            return 0x4000 + offset

    def _detect_active_cells(self, da_addr):
        """Reads DA Configuration and determines active cell count for the pack."""
        self._log(f"Reading DA Configuration at 0x{da_addr:04X}...")
        addr_bytes = [da_addr & 0xFF, (da_addr >> 8) & 0xFF]
        da_data = self.read_mac_block(addr_bytes)
        
        if da_data:
            self._log(f"DA Config Raw Read: {da_data.hex(' ')}")
            
            idx = self._find_header(da_data, addr_bytes)
            if idx == -1 and len(da_data) >= 4:
                self._log("Warning: Address echo not found in DA Config read, falling back to index 0.")
                idx = 0
                    
            if idx != -1 and idx + 3 < len(da_data):
                da_val = struct.unpack_from('<H', da_data, idx + 2)[0]
                if "BQ78350" in self.ic_name.upper():
                    da_val = struct.unpack_from('>H', da_data, idx + 3)[0]
                    self.afe_cell_map = da_val
                    self.active_cells = bin(da_val).count('1')
                    self._log(f"Parsed AFE Cell Map: 0x{da_val:04X} -> Detected {self.active_cells} active cells.")
                else:
                    cc0 = (da_val >> 0) & 1
                    cc1 = (da_val >> 1) & 1
                    self.active_cells = ((cc1 << 1) | cc0) + 1
                    self._log(f"Parsed DA_VAL: 0x{da_val:04X} -> Detected {self.active_cells} active cells (CC1={cc1}, CC0={cc0}).")
                return True
            else:
                self._log("Failed to locate address echo in DA Config read.")
                
        self._log("Failed to read DA Configuration. Assuming 4 cells.")
        self.active_cells = 4
        return True

    def detect_firmware_and_config(self):
        """Orchestrates firmware detection, DataFlash offset mapping, and cell count detection."""
        fw_info = self._read_firmware_version()
        if not fw_info:
            return False

        device, version, major, minor = fw_info
        da_addr = self._load_dataflash_map(version, major, minor)
        return self._detect_active_cells(da_addr)
