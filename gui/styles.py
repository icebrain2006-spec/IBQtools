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
    HEX_BORDER_LIGHT = "#444444"
    HEX_TEXT_MUTED = "#aaaaaa"
    HEX_TEXT_DISABLED = "#555555"
    HEX_SUCCESS = "#00e676"
    HEX_FAIL = "#ff4444"
    HEX_WHITE = "#ffffff"
    HEX_PASS_GREEN = "#69F0AE"
    HEX_WARN_CYAN = "#18FFFF"

    # Board LED & Theme Colors
    BOARD_LED_COLORS = [0x0000FFFF, 0x0000FF00, 0x00FF00FF, 0x00FFFF00]
    BOARD_BG_COLORS = [
        "rgba(0, 255, 255, 0.25)",
        "rgba(0, 255, 0, 0.25)",
        "rgba(255, 0, 255, 0.25)",
        "rgba(255, 255, 0, 0.25)"
    ]
    BOARD_BORDER_COLORS = [
        "rgba(0, 255, 255, 0.6)",
        "rgba(0, 255, 0, 0.6)",
        "rgba(255, 0, 255, 0.6)",
        "rgba(255, 255, 0, 0.6)"
    ]


class Styles:
    """Centralized QSS Style Templates for UI Components."""
    
    CH_BAR_BOX = f"QGroupBox {{ background-color: {Colors.HEX_BG_DARK}; border: 1px solid {Colors.HEX_BORDER_DARK}; border-radius: 6px; margin-top: 0px; padding: 4px; }}"
    
    CH_NAV_BTN = f"QPushButton {{ background-color: #333333; color: white; border: 1px solid #444444; border-radius: 4px; font-weight: bold; font-size: 11px; padding: 0px; }} QPushButton:hover {{ background-color: {Colors.HEX_BORDER_LIGHT}; }}"
    
    CH_LABEL = f"font-size: 15px; font-weight: bold; color: {Colors.HEX_SUCCESS}; padding: 0 14px;"
    
    CH_TITLE = f"font-weight: bold; color: #CCCCCC; font-size: 13px;"

    # Board & SN Checker Tab Styles
    BOARD_TITLE_LABEL = "background: transparent; color: white; font-weight: bold; font-size: 13px; margin-left: 2px; margin-bottom: 2px;"
    BOARD_LABEL = "background: transparent; color: white; font-weight: bold;"
    BOARD_FW_LABEL = "background: transparent; color: #EEEEEE; font-weight: bold; margin-left: 10px;"
    BOARD_SLFS_LABEL = "background: transparent; color: #EEEEEE; font-weight: bold; margin-left: 15px;"
    BOARD_CH_TITLE = "background: transparent; color: #AAAAAA; font-weight: bold; font-size: 11px;"
    BOARD_CH_BOX = "QGroupBox { border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px; background-color: rgba(0, 0, 0, 0.2); }"
    
    BOARD_REFRESH_BTN = """
        QPushButton {
            background-color: rgba(0, 0, 0, 0.4);
            border: 1px solid #777;
            border-radius: 4px;
            color: white;
            padding: 4px 10px;
        }
        QPushButton:hover {
            background-color: rgba(255, 255, 255, 0.1);
        }
    """
    
    QUICK_START_BTN = f"""
        QPushButton {{
            background-color: #222222;
            color: #AAAAAA;
            border: 1px solid #444444;
            border-radius: 4px;
            padding: 4px 15px;
            font-weight: bold;
        }}
        QPushButton:checked {{
            background-color: #004d40;
            color: white;
            border: 1px solid {Colors.HEX_SUCCESS};
        }}
    """
    
    LOG_CONSOLE = f"background-color: #1A1A1A; color: {Colors.HEX_PASS_GREEN}; font-family: Consolas;"

    @staticmethod
    def get_board_group_style(board_id: int, bg_color: str, border_color: str) -> str:
        return f"""
            QGroupBox#board_group_{board_id} {{ 
                background-color: {bg_color}; 
                border: 1px solid {border_color}; 
                border-radius: 5px; 
                margin-top: 2px; 
            }}
        """

    @staticmethod
    def get_board_start_btn_style(border_color: str) -> str:
        return f"""
            QPushButton {{
                background-color: rgba(0, 0, 0, 0.4);
                border: 1px solid {border_color};
                border-radius: 4px;
                color: white;
                font-weight: bold;
                padding: 4px 15px;
            }}
            QPushButton:hover {{
                background-color: {border_color};
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 0, 0, 0.8);
            }}
        """

