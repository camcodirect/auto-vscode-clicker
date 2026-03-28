"""
Windowless launcher — double-click this file or use the Start Menu shortcut.
Runs clicker.py without showing a console window.
"""
import runpy
import sys
from pathlib import Path

# Ensure the app directory is on the path
sys.path.insert(0, str(Path(__file__).parent))

runpy.run_path(str(Path(__file__).parent / "clicker.py"), run_name="__main__")
