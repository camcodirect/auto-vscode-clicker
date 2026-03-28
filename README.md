# VSCode Auto-Clicker

A lightweight Windows utility that watches your screen for a specific button and automatically clicks it when detected. Runs quietly in the system tray with pause/resume controls.

Built for VS Code workflows (e.g., auto-accepting suggestions, clicking recurring prompts), but works with any on-screen button.

## How It Works

1. Takes rapid screenshots of your screen using `mss`
2. Uses OpenCV template matching to find your target button
3. Clicks it with `pyautogui` when the confidence threshold is met
4. Waits for a cooldown period before clicking again

## Quick Start

### Prerequisites

- **Python 3.10+** - [Download here](https://www.python.org/downloads/)
  - During install, check **"Add Python to PATH"**
- **Windows 10 or 11**

### 1. Clone or Download

Download/extract the project folder, then open a terminal in that directory:

```bash
cd path\to\auto-claude-vscode-clicker
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
| `pyautogui` | Mouse clicking |
| `Pillow` | Image manipulation |
| `pystray` | System tray icon and menu |

### 3. Create a Template Image

You need a screenshot of the exact button you want auto-clicked.

1. Open VS Code (or whatever app) with the button visible on screen
2. Press **Win + Shift + S** (Snipping Tool)
3. Select **just the button** - crop tightly, no extra padding
4. Save the screenshot as `templates/button.png`

**Tips for a good template:**
- Use **PNG format** (lossless - no JPEG compression artifacts)
- Capture at your current display scale (100%, 125%, 150%, etc.)
- Include only the button itself, not surrounding UI elements
- The more unique the button looks, the better the matching works

### 4. Run

```bash
python clicker.py
```

A green icon appears in your system tray (bottom-right of taskbar). The tool is now monitoring your screen.

## System Tray Controls

Right-click the tray icon to access the menu:

| Menu Item | Description |
|-----------|-------------|
| **Status** | Shows current state and total click count |
| **Set Template Image** | Pick a different button image via file dialog |
| **Pause / Resume** | Temporarily stop/start monitoring |
| **Open Log File** | View `clicker.log` in your default text editor |
| **Open Config** | Edit `config.json` in your default editor |
| **Open Templates Folder** | Open the templates directory in Explorer |
| **Stop** | Quit the application |

### Tray Icon Colors

| Color | Meaning |
|-------|---------|
| Green | Active - monitoring screen |
| Yellow | Paused |
| Red | Error (check log) |
| Blue | Just clicked (brief flash) |

## Configuration

Edit `config.json` to customize behavior:

```json
{
    "template_path": "templates/button.png",
    "scan_interval_ms": 500,
    "confidence_threshold": 0.8,
    "click_cooldown_seconds": 3,
    "monitor_index": 0,
    "region": null,
    "grayscale": true,
    "log_level": "INFO"
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `template_path` | `templates/button.png` | Path to the button screenshot |
| `scan_interval_ms` | `500` | How often to scan (milliseconds) |
| `confidence_threshold` | `0.8` | Match confidence required (0.0 - 1.0). Lower = more lenient |
| `click_cooldown_seconds` | `3` | Minimum seconds between clicks |
| `monitor_index` | `0` | `0` = all monitors, `1` = primary, `2` = secondary |
| `region` | `null` | Restrict scanning to a specific area (see below) |
| `grayscale` | `true` | Convert to grayscale before matching (faster) |
| `log_level` | `INFO` | `DEBUG`, `INFO`, or `WARNING` |

### Scan Region (Optional)

To improve performance, limit scanning to just the area where the button appears:

```json
"region": {"left": 100, "top": 200, "width": 800, "height": 100}
```

Use the Snipping Tool or a screen coordinate tool to find the pixel coordinates of the area.

## Building a Standalone .exe

If you want to share the tool without requiring Python to be installed:

```bash
pip install pyinstaller
python build.py
```

This creates a `dist/VSCodeAutoClicker/` folder containing:
- `VSCodeAutoClicker.exe` - standalone executable
- `config.json` - settings file
- `templates/` - folder for button images
- `icon.ico` - tray icon

A `dist/VSCodeAutoClicker.zip` is also created, ready to share. Your friend just needs to:
1. Extract the zip
2. Put their button screenshot in the `templates/` folder
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

### Button not detected
- **Lower the threshold**: Try `0.7` or `0.6` in `config.json`
- **Check display scaling**: Recapture the template at your current Windows display scale
- **Recapture the template**: VS Code theme, zoom, or font changes affect button appearance
- **Enable debug logging**: Set `"log_level": "DEBUG"` to see scan details

### Clicking the wrong spot
- Crop a more unique section of the button
- Check `monitor_index` for multi-monitor setups

### High CPU usage
- Increase `scan_interval_ms` to `1000` or `2000`
- Set a `region` to scan a smaller area
- Keep `grayscale` set to `true`

### pyautogui FailSafeException
Moving your mouse to the top-left corner (0,0) triggers pyautogui's safety shutdown. This is intentional - it gives you an emergency stop.

### Import errors
```bash
pip install -r requirements.txt --force-reinstall
```

## Logs

Activity is logged to `clicker.log` in the application directory. Example output:

```
12:30:01 [INFO] Loaded template: button.png (120x32)
12:30:01 [INFO] === VSCode Button Auto-Clicker ===
12:30:01 [INFO] Threshold: 0.80 | Interval: 500ms | Cooldown: 3s
12:30:05 [INFO] Button found (confidence=0.923) at (1045, 567)
12:30:05 [INFO] Clicked at (1045, 567)
```

## Project Structure

```
auto-claude-vscode-clicker/
├── clicker.py              # Main application
├── clicker.pyw             # Windowless launcher (no console window)
├── config.json             # Settings
├── requirements.txt        # Python dependencies
├── build.py                # PyInstaller build script
├── create_icon.py          # Generates tray icon
├── install_shortcuts.py    # Windows shortcut installer
├── icon.ico                # System tray icon
├── templates/
│   └── button.png          # Your button screenshot goes here
└── dist/                   # Built .exe output (after running build.py)
```
