import sys
import os

_root = os.path.dirname(os.path.abspath(__file__))
_gui_dir = os.path.join(_root, "gui")
if _root not in sys.path:
    sys.path.insert(0, _root)
if _gui_dir not in sys.path:
    sys.path.insert(0, _gui_dir)

from gui.main import main


if __name__ == "__main__":
    main()
