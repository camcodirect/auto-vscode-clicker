"""
Creates Windows shortcuts for the VSCode Auto-Clicker:
  1. Start Menu shortcut
  2. Desktop shortcut (optional)
  3. Startup folder shortcut (optional — auto-run on login)

Run: python install_shortcuts.py
"""

import os
import sys
from pathlib import Path

try:
    import winshell
except ImportError:
    print("Installing winshell...")
    os.system(f"{sys.executable} -m pip install winshell pywin32")
    import winshell

from win32com.client import Dispatch

APP_DIR = Path(__file__).parent
APP_NAME = "VSCode Auto-Clicker"
CLICKER_PATH = APP_DIR / "clicker.py"
STOP_PATH = APP_DIR / "stop_clicker.pyw"
ICON_PATH = APP_DIR / "icon.ico"


def find_pythonw() -> str:
    """Find pythonw.exe (windowless Python interpreter)."""
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if pythonw.exists():
        return str(pythonw)
    # For Windows Store Python
    for p in python_dir.glob("pythonw*.exe"):
        return str(p)
    # Fallback
    return str(pythonw)


def create_shortcut(shortcut_path: Path, target: str, arguments: str, working_dir: str, description: str, icon: str | None = None):
    shell = Dispatch("WScript.Shell")
    sc = shell.CreateShortCut(str(shortcut_path))
    sc.Targetpath = target
    sc.Arguments = arguments
    sc.WorkingDirectory = working_dir
    sc.Description = description
    if icon and Path(icon).exists():
        sc.IconLocation = icon
    sc.save()
    print(f"  Created: {shortcut_path}")


def main():
    pythonw = find_pythonw()
    start_args = f'"{CLICKER_PATH}"'
    stop_args = f'"{STOP_PATH}"'
    working_dir = str(APP_DIR)
    icon = str(ICON_PATH) if ICON_PATH.exists() else None

    print(f"\n=== {APP_NAME} — Shortcut Installer ===\n")
    print(f"  App:      {CLICKER_PATH}")
    print(f"  Stop:     {STOP_PATH}")
    print(f"  Python:   {pythonw}")
    print()

    # 1. Start Menu (Start + Stop)
    start_menu = Path(winshell.start_menu()) / "Programs"
    create_shortcut(start_menu / f"{APP_NAME} - Start.lnk", pythonw, start_args, working_dir, f"Start {APP_NAME}", icon)
    create_shortcut(start_menu / f"{APP_NAME} - Stop.lnk", pythonw, stop_args, working_dir, f"Stop {APP_NAME}", icon)

    # 2. Desktop
    answer = input("\nCreate desktop shortcuts? [y/N]: ").strip().lower()
    if answer == "y":
        desktop = Path(winshell.desktop())
        create_shortcut(desktop / f"{APP_NAME} - Start.lnk", pythonw, start_args, working_dir, f"Start {APP_NAME}", icon)
        create_shortcut(desktop / f"{APP_NAME} - Stop.lnk", pythonw, stop_args, working_dir, f"Stop {APP_NAME}", icon)

    # 3. Startup (auto-run on login)
    answer = input("Start automatically on login? [y/N]: ").strip().lower()
    if answer == "y":
        startup = Path(winshell.startup())
        create_shortcut(startup / f"{APP_NAME}.lnk", pythonw, start_args, working_dir, APP_NAME, icon)

    print(f"\nDone! You can find '{APP_NAME}' in your Start Menu.")
    print("  - 'Start' shortcut launches the clicker")
    print("  - 'Stop' shortcut kills it")
    print("  - You can also right-click the tray icon to stop.\n")


if __name__ == "__main__":
    main()
