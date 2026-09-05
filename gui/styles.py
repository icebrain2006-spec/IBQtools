from PySide6.QtGui import QColor

class Colors:
    """Centralized Theme Palette and Design Tokens for IBQtools UI."""
    
    # Background Colors
    BG_DARK = QColor("#1e1e1e")
    BG_PANEL = QColor("#2b2b2b")
    BG_INACTIVE = QColor("#222222")
    BG_ACTIVE_GREEN = QColor("#2d5a2d")
    
    # Border & Grid Colors
    BORDER_DARK = QColor("#3a3a3a")
    BORDER_LIGHT = QColor("#444444")
    
    # Text Colors
    TEXT_WHITE = QColor("#ffffff")
    TEXT_MUTED = QColor("#888888")
    TEXT_DISABLED = QColor("#aaaaaa")
    TEXT_ROW = QColor("#e0e0e0")
    
    # Status & Highlight Colors
    SUCCESS = QColor("#00e676")
    FAIL = QColor("#ff4444")
    
    # String Hex Constants for QSS and HTML styling
    HEX_BG_DARK = "#1e1e1e"
    HEX_BG_PANEL = "#2b2b2b"
    HEX_BORDER_DARK = "#3a3a3a"
    HEX_TEXT_MUTED = "#aaaaaa"
    HEX_SUCCESS = "#00e676"
    HEX_FAIL = "#ff4444"
    HEX_WHITE = "#ffffff"
