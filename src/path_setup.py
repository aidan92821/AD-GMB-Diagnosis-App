"""
gui-app/path_setup.py
──────────────────────
Import this module ONCE at the very top of gui-app/main.py (before any other
local imports).  It adds the project root to sys.path so that both:

    from utils.data_loader import load_file           # gui-app/utils/
    from src.services.assessment_service import ...   # src/services/

resolve correctly no matter which directory you launch the app from.

USAGE in main.py:
─────────────────
    import path_setup   # ← must be first local import
    from ui.main_window import MainWindow
    ...

WHY THIS IS NEEDED
──────────────────
Your project root looks like:

    capstone/                  ← PROJECT ROOT  (add this to sys.path)
    ├── gui-app/
    │   ├── main.py
    │   ├── path_setup.py      ← this file
    │   ├── utils/
    │   │   └── data_loader.py
    │   └── ui/
    └── src/
        └── services/
            └── assessment_service.py

When you run  `python main.py`  from inside gui-app/, Python adds gui-app/ to
sys.path automatically — but NOT the project root.  So `from src.services...`
fails with ModuleNotFoundError.

This file resolves that by walking up the directory tree to find the folder
that contains BOTH gui-app/ and src/, then inserting it at position 0.
"""
from __future__ import annotations
import sys
from pathlib import Path


def _find_project_root(start: Path, marker: str = "src") -> Path:
    """
    Walk up from *start* until we find a directory that contains *marker*.
    This is the project root.  Raises RuntimeError if not found.
    """
    current = start.resolve()
    for _ in range(10):   # safety limit — never walk more than 10 levels up
        if (current / marker).is_dir():
            return current
        parent = current.parent
        if parent == current:
            break          # reached filesystem root
        current = parent
    raise RuntimeError(
        f"Could not find project root (a directory containing '{marker}') "
        f"starting from {start}. Make sure you run the app from inside "
        f"gui-app/ or the project root."
    )


# ── Patch sys.path ────────────────────────────────────────────────────────────
_this_file   = Path(__file__).resolve()      # .../capstone/gui-app/path_setup.py
_gui_app_dir = _this_file.parent             # .../capstone/gui-app/
_project_root = _find_project_root(_gui_app_dir, marker="src")

# Insert project root first so it takes priority over any installed packages
# with the same name.
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Also ensure gui-app/ itself is on the path (for `from utils.data_loader ...`)
if str(_gui_app_dir) not in sys.path:
    sys.path.insert(1, str(_gui_app_dir))