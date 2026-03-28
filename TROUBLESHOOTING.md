# Troubleshooting

## Button not detected

**Lower the confidence threshold:**
In `config.json`, try reducing `confidence_threshold` from `0.8` to `0.7` or `0.6`.

**Check display scaling:**
If your Windows display scale is not 100%, the button may appear at a different size than your template. Recapture the template at your current scale.

**Recapture the template:**
VS Code themes, zoom levels, or font sizes can change button appearance. Make sure the template matches the current look.

**Enable DEBUG logging:**
Set `"log_level": "DEBUG"` in `config.json`. The tool will log every scan cycle so you can see what's happening.

## Clicking the wrong spot

**Template is too generic:**
If the template matches multiple places on screen, crop a more unique section of the button or include a small amount of surrounding context.

**Multi-monitor offset:**
Make sure `monitor_index` is set correctly. `0` captures all monitors, which handles offsets automatically.

## High CPU usage

**Increase scan interval:**
Set `scan_interval_ms` to `1000` or `2000` for less frequent scanning.

**Use a scan region:**
Set the `region` field in `config.json` to only scan the area where the button appears. This dramatically reduces the amount of image data processed.

**Enable grayscale:**
Keep `"grayscale": true` — it processes ~3x less data than color matching.

## pyautogui FailSafeException

If you move your mouse to the top-left corner of the screen (0,0), pyautogui will raise a `FailSafeException` and stop. This is a safety feature. If you want to disable it (not recommended), add `pyautogui.FAILSAFE = False` in the code.

## Import errors

Re-install dependencies:
```bash
pip install -r requirements.txt --force-reinstall
```
