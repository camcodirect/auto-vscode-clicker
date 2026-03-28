# VSCode Button Auto-Clicker — Project Plan

## Goal
A lightweight Windows utility that monitors the screen for a specific button in VS Code and automatically clicks it when detected.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  mss (fast   │────▶│  OpenCV      │────▶│  pyautogui   │
│  screenshot) │     │  template    │     │  click()     │
│              │     │  matching    │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
       ▲                    ▲
       │                    │
   config.json        templates/
   (settings)         (button images)
```

### Core Loop
1. Capture screenshot using `mss` (fastest Python screen capture on Windows)
2. Convert to grayscale (optional, faster matching)
3. Run `cv2.matchTemplate()` with `TM_CCOEFF_NORMED`
4. If confidence ≥ threshold → click at the button center
5. Respect cooldown to avoid rapid repeated clicks
6. Sleep for the configured interval, then repeat

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Screenshot lib | `mss` | ~30ms per capture vs ~200ms for PIL/pyautogui |
| Matching method | OpenCV template matching | Simple, fast, no ML overhead — perfect for exact button matching |
| Grayscale mode | On by default | ~2x faster matching, works well for UI buttons |
| Config format | JSON file | Easy to edit, no extra dependencies |
| Click method | `pyautogui` | Cross-platform, reliable, handles multi-monitor |

## File Structure

```
auto-claude-vscode-clicker/
├── clicker.py           # Main program — screen monitor + clicker
├── config.json          # All configurable settings
├── requirements.txt     # Python dependencies
├── templates/           # Template images go here
│   └── button.png       # ← User places their button screenshot here
├── PROJECT_PLAN.md      # This file
├── SETUP_GUIDE.md       # How to set up and use the tool
└── TROUBLESHOOTING.md   # Common issues and fixes
```

## Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `template_path` | `templates/button.png` | Path to the button screenshot |
| `scan_interval_ms` | `500` | Time between scans (ms) |
| `confidence_threshold` | `0.8` | Match confidence (0.0–1.0). Lower = more lenient |
| `click_cooldown_seconds` | `3` | Minimum seconds between clicks |
| `monitor_index` | `0` | Which monitor (0 = all, 1 = primary, 2 = secondary) |
| `region` | `null` | Optional `{"left":x,"top":y,"width":w,"height":h}` to scan a sub-area |
| `grayscale` | `true` | Convert to grayscale before matching |
| `log_level` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING) |

## Status

- [x] Core screen capture + template matching loop
- [x] Config file support
- [x] Multi-monitor support
- [x] Cooldown to prevent rapid re-clicking
- [x] Dependencies installed and verified
- [ ] User adds template image to `templates/button.png`
- [ ] Test with actual VS Code button
