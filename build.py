"""
Build the VSCode Auto-Clicker into a distributable package.

Creates:
  dist/VSCodeAutoClicker/
    ├── VSCodeAutoClicker.exe    # The app (no Python needed)
    ├── config.json              # Settings (user-editable)
    ├── icon.ico                 # App icon
    └── templates/               # Template images go here
        └── (user adds button.png)

Run:  python build.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent
DIST_DIR = APP_DIR / "dist"
PACKAGE_DIR = DIST_DIR / "VSCodeAutoClicker"


def main():
    print("\n=== Building VSCode Auto-Clicker ===\n")

    # 1. Run PyInstaller
    print("[1/3] Running PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",                      # No console window
        "--name", "VSCodeAutoClicker",
        "--icon", str(APP_DIR / "icon.ico"),
        # Bundle the icon inside the exe as well for the tray fallback
        "--add-data", f"{APP_DIR / 'icon.ico'};.",
        str(APP_DIR / "clicker.py"),
    ]
    result = subprocess.run(cmd, cwd=str(APP_DIR))
    if result.returncode != 0:
        print("ERROR: PyInstaller failed.")
        sys.exit(1)

    # 2. Copy config + templates next to the exe
    print("[2/3] Copying config and templates...")
    exe_dir = DIST_DIR  # --onefile puts exe directly in dist/

    # Create the final package folder
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True)

    # Move exe into package folder
    exe_src = exe_dir / "VSCodeAutoClicker.exe"
    shutil.move(str(exe_src), str(PACKAGE_DIR / "VSCodeAutoClicker.exe"))

    # Copy config
    shutil.copy2(APP_DIR / "config.json", PACKAGE_DIR / "config.json")

    # Copy icon
    if (APP_DIR / "icon.ico").exists():
        shutil.copy2(APP_DIR / "icon.ico", PACKAGE_DIR / "icon.ico")

    # Copy templates folder (with any existing templates)
    templates_src = APP_DIR / "templates"
    templates_dst = PACKAGE_DIR / "templates"
    if templates_src.exists():
        shutil.copytree(templates_src, templates_dst)
    else:
        templates_dst.mkdir()

    # 3. Create a README for the recipient
    readme = PACKAGE_DIR / "README.txt"
    readme.write_text("""\
VSCode Auto-Clicker
===================

This tool monitors your screen for a specific button and clicks it
automatically when detected.

SETUP:
  1. Take a screenshot of the button you want auto-clicked.
     - Use Win+Shift+S to snip just the button.
     - Save it as:  templates\\button.png

  2. (Optional) Edit config.json to adjust settings:
     - confidence_threshold: How closely the button must match (0.0-1.0)
     - scan_interval_ms: How often to scan (default 500ms)
     - click_cooldown_seconds: Minimum time between clicks (default 3s)

  3. Double-click VSCodeAutoClicker.exe to start.

  4. A green icon appears in your system tray (bottom-right, near the clock).
     Right-click it to:
     - Pause / Resume monitoring
     - Open the log file
     - Open config or templates folder
     - Stop the application

REQUIREMENTS:
  - Windows 10 or 11
  - No Python installation needed!

TROUBLESHOOTING:
  - If the button isn't detected, try lowering confidence_threshold to 0.7
  - Make sure the template screenshot matches your current display scaling
  - Check clicker.log (created next to the exe) for details
""", encoding="utf-8")

    # 4. Create zip for easy sharing
    print("[3/3] Creating zip archive...")
    zip_path = DIST_DIR / "VSCodeAutoClicker"
    shutil.make_archive(str(zip_path), "zip", str(DIST_DIR), "VSCodeAutoClicker")

    print(f"\n=== Build complete! ===")
    print(f"  Folder:  {PACKAGE_DIR}")
    print(f"  Zip:     {zip_path}.zip")
    print(f"\nShare the zip file with your friend. No Python needed!\n")


if __name__ == "__main__":
    main()
