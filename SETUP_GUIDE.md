# Setup Guide

## Prerequisites
- Python 3.10+
- Windows 10/11

## Installation

```bash
cd E:\claude-projects\auto-claude-vscode-clicker
pip install -r requirements.txt
```

## Step 1: Capture a Template Image

You need a screenshot of the exact button you want the tool to click.

1. Open VS Code with the button visible
2. Use **Win + Shift + S** (Snipping Tool) to select just the button
3. Save the image as `templates/button.png`

**Tips for a good template:**
- Crop tightly around the button — no extra padding
- Capture at your normal display scale (100%, 125%, 150%, etc.)
- Include just the button, not surrounding UI
- PNG format (lossless — no JPEG artifacts)

## Step 2: Configure (Optional)

Edit `config.json` to tune behavior:

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

### Narrowing the scan region

To improve performance, restrict scanning to just the area where the button appears:

```json
"region": {"left": 100, "top": 200, "width": 800, "height": 100}
```

Use the Snipping Tool or a screen coordinate tool to find the pixel coordinates.

### Monitor selection

- `0` — all monitors combined (default)
- `1` — primary monitor
- `2` — secondary monitor, etc.

## Step 3: Run

```bash
python clicker.py
```

Output will look like:

```
12:30:01 [INFO] Loaded template: button.png (120x32)
12:30:01 [INFO] === VSCode Button Auto-Clicker ===
12:30:01 [INFO] Threshold: 0.80 | Interval: 500ms | Cooldown: 3s
12:30:01 [INFO] Monitoring screen (Ctrl+C to stop)...
12:30:05 [INFO] Button found (confidence=0.923) at (1045, 567)
12:30:05 [INFO] Clicked at (1045, 567)
```

Press **Ctrl+C** to stop.

## Using Multiple Templates

To watch for different buttons, create multiple config files and run separate instances:

```bash
# Copy and edit for a second button
copy config.json config_button2.json
```

Then modify `clicker.py` to accept a `--config` argument (future enhancement), or just change `config.json` between runs.
