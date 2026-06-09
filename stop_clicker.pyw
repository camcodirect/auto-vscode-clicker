"""Kill any running VSCode Auto-Clicker process."""
import subprocess

# Kill compiled .exe if present
subprocess.run(
    ["taskkill", "/IM", "VSCodeAutoClicker.exe", "/F"],
    capture_output=True, text=True,
)

# Kill python/pythonw processes running clicker.py — wmic is removed on
# Windows 11 24H2, so use PowerShell + Get-CimInstance instead.
subprocess.run(
    [
        "powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"name like 'python%'\" | "
        "Where-Object { $_.CommandLine -like '*clicker.py*' -and "
        "$_.ProcessId -ne $PID } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
        "-ErrorAction SilentlyContinue }",
    ],
    capture_output=True, text=True,
)
