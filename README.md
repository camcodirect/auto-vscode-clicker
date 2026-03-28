# VSCode Auto-Clicker / Auto-Confirm

A lightweight Windows utility with two modes:

- **Auto Click** - Watches your screen for a specific button and clicks it automatically. Great for VS Code users who need to auto-accept suggestions or click recurring prompts.
- **Auto Confirm** - Watches for a Claude CLI confirmation prompt ("1. Yes / 2. No") in any console window (standalone cmd/PowerShell or VS Code integrated terminal), focuses it, and sends `1` + Enter automatically.

Runs quietly in the system tray with pause/resume controls and a built-in settings GUI.

## How It Works

1. Takes rapid screenshots of your screen using `mss`
2. Uses OpenCV template matching to find your target (button or prompt)
3. **Auto Click mode**: clicks the matched button
4. **Auto Confirm mode**: clicks the console area to focus it, types `1`, presses Enter
5. Waits for a cooldown period before acting again

## Quick Start

### Prerequisites

- **Python 3.10+** - [Download here](https://www.python.org/downloads/)
  - During install, check **"Add Python to PATH"**
- **Windows 10 or 11**

### 1. Clone or Download

```bash
git clone https://github.com/camcodirect/auto-vscode-clicker.git
cd auto-vscode-clicker
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
| Package | Purpose |
|---------|---------|
| `opencv-python` | Image template matching |
| `numpy` | Array operations for image processing |
| `mss` | Fast screenshot capture (~30ms) |
| `pyautogui` | Mouse clicking and keyboard input |
| `Pillow` | Image manipulation |
| `pystray` | System tray icon and menu |

### 3. Create a Template Image

You need a screenshot of what the tool should look for on screen.

**For Auto Click mode** (default):
1. Open VS Code with the button visible on screen
2. Press **Win + Shift + S** (Snipping Tool)
3. Select **just the button** - crop tightly, no extra padding
4. Save as `templates/button.png`

**For Auto Confirm mode**:
1. Open your Claude CLI session (in cmd, PowerShell, or VS Code terminal)
2. Wait for a confirmation prompt to appear ("Do you want to proceed?" / "1. Yes, 2. No")
3. Press **Win + Shift + S** and capture the prompt text
4. Save as `templates/confirm_prompt.png`

**Tips for a good template:**
- Use **PNG format** (lossless - no JPEG compression artifacts)
- Capture at your current display scale (100%, 125%, 150%, etc.)
- Crop tightly around the target - include only the button/prompt text
- The more unique the captured area looks, the better the matching works

### 4. Run

```bash
python clicker.py
```

A green icon appears in your system tray (bottom-right of taskbar). The tool is now monitoring your screen.

## Choosing a Mode

You can switch modes in three ways:

1. **Tray menu** - Right-click tray icon > Mode > pick Auto Click or Auto Confirm
2. **Settings dialog** - Right-click tray icon > Settings > change Mode
3. **Config file** - Set `"mode"` to `"auto_click"` or `"auto_confirm"` in `config.json`

### Auto Click mode
Best for **VS Code users** who want to auto-click a button in the editor UI (accept suggestions, dismiss dialogs, etc.).

### Auto Confirm mode
Best for **Claude CLI users** running Claude Code in any terminal:
- Windows Command Prompt (cmd)
- PowerShell
- VS Code integrated terminal
- Windows Terminal

When the tool detects the confirmation prompt on screen, it clicks the console to focus it and sends `1` + Enter to confirm.

## System Tray Controls

Right-click the tray icon to access the menu:

| Menu Item | Description |
|-----------|-------------|
| **Status** | Shows current state and action count |
| **Mode** | Shows current mode (Auto Click / Auto Confirm) |
| **Mode submenu** | Switch between Auto Click and Auto Confirm |
| **Set Template** | Pick a template image for the current mode |
| **Pause / Resume** | Temporarily stop/start monitoring |
| **Settings** | Open the settings GUI to adjust all options |
| **Open Log File** | View `clicker.log` in your default text editor |
| **Open Templates Folder** | Open the templates directory in Explorer |
| **Stop** | Quit the application |

### Tray Icon Colors

| Color | Meaning |
|-------|---------|
| Green | Active - monitoring screen |
| Yellow | Paused or no template set |
| Red | Error (check log) |
| Blue | Just acted (brief flash after click/confirm) |

## Settings

Right-click the tray icon and select **Settings** to open the settings GUI. All options can be adjusted without editing files:

| Setting | Default | Description |
|---------|---------|-------------|
| **Mode** | Auto Click | `auto_click` or `auto_confirm` |
| **Scan Interval** | 500 ms | How often to scan the screen |
| **Confidence Threshold** | 0.80 | Match confidence required (0.0 - 1.0). Lower = more lenient |
| **Click Cooldown** | 3 sec | Minimum seconds between clicks (Auto Click mode) |
| **Confirm Cooldown** | 5 sec | Minimum seconds between confirms (Auto Confirm mode) |
| **Monitor Index** | 0 | `0` = all monitors, `1` = primary, `2` = secondary |
| **Grayscale** | On | Faster matching when enabled |
| **Log Level** | INFO | `DEBUG` for verbose output, `WARNING` for quiet |
| **Scan Region** | None | Optional pixel region to limit scanning area |

You can also edit `config.json` directly:

```json
{
    "mode": "auto_click",
    "template_path": "templates/button.png",
    "confirm_template_path": "templates/confirm_prompt.png",
    "scan_interval_ms": 500,
    "confidence_threshold": 0.8,
    "click_cooldown_seconds": 3,
    "confirm_cooldown_seconds": 5,
    "monitor_index": 0,
    "region": null,
    "grayscale": true,
    "log_level": "INFO"
}
```

### Scan Region (Optional)

To improve performance, limit scanning to just the area where the button/prompt appears:

```json
"region": {"left": 100, "top": 200, "width": 800, "height": 100}
```

## Building a Standalone .exe

If you want to share the tool without requiring Python to be installed:

```bash
pip install pyinstaller
python build.py
```

This creates a `dist/VSCodeAutoClicker/` folder and a `dist/VSCodeAutoClicker.zip` ready to share. The recipient just needs to:
1. Extract the zip
2. Capture their button/prompt screenshot into the `templates/` folder
3. Run `VSCodeAutoClicker.exe`

No Python installation needed.

## Installing Shortcuts (Optional)

To add Start Menu and Desktop shortcuts:

```bash
pip install winshell pywin32
python install_shortcuts.py
```

This can also set up the tool to run automatically on Windows login.

## Troubleshooting

### Button/prompt not detected
- **Lower the threshold**: Open Settings and try 0.70 or 0.60
- **Check display scaling**: Recapture the template at your current Windows display scale
- **Recapture the template**: Theme, zoom, or font changes affect appearance
- **Enable debug logging**: Set log level to `DEBUG` in Settings to see scan details

### Auto Confirm not working
- Make sure the console window with the Claude prompt is **visible on screen** (not minimized)
- The template should capture the prompt text as it appears in your specific terminal (cmd vs PowerShell vs VS Code terminal may look different)
- Try lowering the confidence threshold if the prompt has slight visual variations

### Clicking the wrong spot
- Crop a more unique section of the button/prompt
- Check monitor index for multi-monitor setups

### High CPU usage
- Increase scan interval to 1000-2000 ms in Settings
- Set a scan region to limit the search area
- Keep grayscale enabled

### pyautogui FailSafeException
Moving your mouse to the top-left corner (0,0) triggers pyautogui's safety shutdown. This is intentional - it gives you an emergency stop.

### Import errors
```bash
pip install -r requirements.txt --force-reinstall
```

## Logs

Activity is logged to `clicker.log` in the application directory. Example output:

```
12:30:01 [INFO] === VSCode Button Auto Click ===
12:30:01 [INFO] Mode: auto_click | Threshold: 0.80 | Interval: 500ms
12:30:05 [INFO] Button found (confidence=0.923) at (1045, 567)
12:30:05 [INFO] Clicked at (1045, 567)
```

Auto Confirm mode log:
```
12:30:01 [INFO] === VSCode Button Auto Confirm ===
12:30:01 [INFO] Mode: auto_confirm | Threshold: 0.80 | Interval: 500ms
12:30:05 [INFO] Confirm prompt found (confidence=0.891) at (800, 450)
12:30:05 [INFO] Sent confirmation '1' + Enter at (800, 450)
```

## Project Structure

```
auto-vscode-clicker/
├── clicker.py              # Main application
├── clicker.pyw             # Windowless launcher (no console window)
├── config.json             # Settings
├── requirements.txt        # Python dependencies
├── build.py                # PyInstaller build script
├── create_icon.py          # Generates tray icon
├── install_shortcuts.py    # Windows shortcut installer
├── icon.ico                # System tray icon
├── templates/
│   ├── button.png          # Auto Click template (you create this)
│   └── confirm_prompt.png  # Auto Confirm template (you create this)
└── dist/                   # Built .exe output (after running build.py)
```
