import serial.tools.list_ports
from PySide6.QtWidgets import QComboBox

def get_available_ports(include_none=False):
    """
    Scans and filters available USB serial ports.
    Prioritizes RP2040 Pico devices (VID 2E8A) at the top of the list.
    """
    rp2040_ports = []
    other_usb_ports = []
    
    for p in serial.tools.list_ports.comports():
        hwid = str(p.hwid).upper()
        desc = str(p.description).upper()
        if "BTHENUM" in hwid or "BLUETOOTH" in desc:
            continue
        if "USB" not in hwid and "USB" not in desc:
            continue
            
        port_num = 9999
        if p.device.upper().startswith("COM"):
            try:
                port_num = int(p.device[3:])
            except ValueError:
                pass
                
        if "2E8A" in hwid or "RP2040" in desc or "PICO" in desc:
            rp2040_ports.append((port_num, p.device))
        else:
            other_usb_ports.append((port_num, p.device))
            
    rp2040_ports.sort(key=lambda x: x[0])
    other_usb_ports.sort(key=lambda x: x[0])
    
    sorted_ports = [dev for _, dev in rp2040_ports] + [dev for _, dev in other_usb_ports]
    
    if include_none:
        sorted_ports.insert(0, "None")
        
    if not sorted_ports:
        sorted_ports = ["Select COM"]
        
    return sorted_ports, len(rp2040_ports) > 0

class PortComboBox(QComboBox):
    """
    Smart COM Port selection dropdown.
    Automatically scans and updates available ports when clicked (showPopup).
    """
    def __init__(self, parent=None, include_none=False):
        super().__init__(parent)
        self.include_none = include_none
        self.refresh_ports()
        
    def refresh_ports(self):
        current_text = self.currentText()
        self.clear()
        
        sorted_ports, has_rp2040 = get_available_ports(include_none=self.include_none)
        self.addItems(sorted_ports)
        
        if has_rp2040 and not self.include_none:
            self.setCurrentIndex(0)
        elif current_text and current_text in sorted_ports:
            self.setCurrentText(current_text)
        elif sorted_ports and sorted_ports[0] != "Select COM":
            self.setCurrentIndex(0)

    def showPopup(self):
        self.refresh_ports()
        super().showPopup()
