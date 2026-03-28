"""Kill any running VSCode Auto-Clicker process."""
import subprocess
import sys

result = subprocess.run(
    ["taskkill", "/IM", "VSCodeAutoClicker.exe", "/F"],
    capture_output=True, text=True,
)

# Also kill if running via python directly
subprocess.run(
    ["taskkill", "/FI", f"WINDOWTITLE eq VSCode Auto-Clicker", "/F"],
    capture_output=True, text=True,
)

# Find python processes running clicker.py/clicker.pyw
import os, signal

wmic = subprocess.run(
    ["wmic", "process", "where", "name like '%python%'", "get", "processid,commandline"],
    capture_output=True, text=True,
)
for line in wmic.stdout.splitlines():
    if "clicker.py" in line or "clicker.pyw" in line:
        parts = line.strip().split()
        try:
            pid = int(parts[-1])
            if pid != os.getpid():
                os.kill(pid, signal.SIGTERM)
        except (ValueError, IndexError, OSError):
            pass
