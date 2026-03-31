"""
VSCode Button Auto-Clicker / Auto-Confirm

Modes of operation:
  - Auto Click:        Monitors screen for a button image and clicks it.
  - Auto Confirm:      Monitors screen for a Claude CLI confirmation prompt
                       and sends "1" + Enter (requires window to be visible).
  - Background Confirm: Reads terminal console buffers directly via Win32 API
                       and sends keystrokes — works even when minimized.
  - Both:              Auto Click + Auto Confirm simultaneously.

Runs as a system tray application with right-click menu to control.
"""

import atexit
import ctypes
import json
import logging
import os
import signal
import shutil
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import cv2
import keyboard
import mss
import numpy as np
import PIL.Image
import PIL.ImageDraw
import pyautogui
import pystray

from console_monitor import (
    ProcessCache, detect_prompt, read_console_buffer, send_console_keys,
)

# Ensure correct DPI awareness for accurate screen coordinates on Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    pass


def get_app_dir() -> Path:
    """Resolve the app directory — works for both script and PyInstaller exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


APP_DIR = get_app_dir()
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "clicker.log"
TEMPLATES_DIR = APP_DIR / "templates"

# Log to file (no console window in background mode)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("clicker")


# ── Config ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ── Template matching ───────────────────────────────────────────────────────

def load_template(path: str, grayscale: bool) -> np.ndarray | None:
    full_path = APP_DIR / path
    if not full_path.exists():
        log.warning("Template not found: %s", full_path)
        return None

    img = cv2.imread(str(full_path), cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR)
    if img is None:
        log.warning("Failed to read template image: %s", full_path)
        return None

    log.info("Loaded template: %s (%dx%d)", full_path.name, img.shape[1], img.shape[0])
    return img


def load_confirm_templates(cfg: dict, grayscale: bool) -> list[tuple[str, np.ndarray]]:
    """Load all confirm templates from the confirm directory and legacy single file."""
    templates = []
    image_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')

    # Load from confirm templates directory
    confirm_dir = APP_DIR / cfg.get("confirm_templates_dir", "templates/confirm")
    if confirm_dir.exists():
        for f in sorted(confirm_dir.iterdir()):
            if f.suffix.lower() in image_exts:
                flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
                img = cv2.imread(str(f), flag)
                if img is not None:
                    log.info("Loaded confirm template: %s (%dx%d)",
                             f.name, img.shape[1], img.shape[0])
                    templates.append((f.name, img))
                else:
                    log.warning("Failed to read confirm template: %s", f)

    # Also load legacy single confirm template if it exists outside confirm dir
    legacy_rel = cfg.get("confirm_template_path", "templates/confirm_prompt.png")
    legacy_path = APP_DIR / legacy_rel
    if legacy_path.exists() and legacy_path.parent != confirm_dir:
        flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
        img = cv2.imread(str(legacy_path), flag)
        if img is not None:
            log.info("Loaded legacy confirm template: %s (%dx%d)",
                     legacy_path.name, img.shape[1], img.shape[0])
            templates.append((legacy_path.name, img))

    log.info("Total confirm templates loaded: %d", len(templates))
    return templates


def find_any_match(
    screen: np.ndarray,
    templates: list[tuple[str, np.ndarray]],
    threshold: float,
):
    """Try matching screen against multiple templates. Returns (cx, cy, confidence) or None."""
    for name, tpl in templates:
        result = find_button(screen, tpl, threshold)
        if result:
            log.debug("Matched confirm template: %s (confidence=%.3f)", name, result[2])
            return result
    return None


def grab_screen(sct: mss.mss, monitor_index: int, region: dict | None, grayscale: bool):
    if region:
        mon = region
    else:
        mon = sct.monitors[monitor_index]

    shot = sct.grab(mon)
    frame = np.array(shot)

    if grayscale:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    else:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    return frame, mon


def find_button(screen: np.ndarray, template: np.ndarray, threshold: float):
    if screen.shape[0] < template.shape[0] or screen.shape[1] < template.shape[1]:
        return None

    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        cx = max_loc[0] + template.shape[1] // 2
        cy = max_loc[1] + template.shape[0] // 2
        return cx, cy, max_val

    return None


def click_at(x: int, y: int) -> None:
    """Move to the target, hover briefly, then click. The delay helps Electron apps."""
    pyautogui.moveTo(x, y)
    time.sleep(0.08)
    pyautogui.click()
    log.info("Clicked at (%d, %d)", x, y)


def confirm_at(x: int, y: int) -> None:
    """Click the console area to focus it, then type '1' and press Enter."""
    pyautogui.moveTo(x, y)
    time.sleep(0.08)
    pyautogui.click()
    time.sleep(0.15)  # brief pause to let the window focus
    pyautogui.typewrite("1", interval=0.03)
    pyautogui.press("enter")
    log.info("Sent confirmation '1' + Enter at (%d, %d)", x, y)


# ── Tray icon ──────────────────────────────────────────────────────────────

def load_ico_icon() -> PIL.Image.Image | None:
    ico_path = APP_DIR / "icon.ico"
    if ico_path.exists():
        try:
            return PIL.Image.open(ico_path)
        except Exception:
            pass
    return None


def create_tray_icon_image(color: str = "green") -> PIL.Image.Image:
    if color == "green":
        ico = load_ico_icon()
        if ico:
            return ico

    size = 64
    img = PIL.Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = PIL.ImageDraw.Draw(img)

    colors = {
        "green": (76, 175, 80, 255),
        "yellow": (255, 193, 7, 255),
        "red": (244, 67, 54, 255),
        "blue": (33, 150, 243, 255),
    }
    fill = colors.get(color, colors["green"])

    draw.ellipse([4, 4, size - 4, size - 4], fill=fill)
    draw.ellipse([18, 18, size - 18, size - 18], fill=(255, 255, 255, 120))

    return img


# ── Template file picker (runs in its own thread to avoid blocking tray) ───

def pick_template_file() -> str | None:
    """Open a file dialog and return the chosen path, or None if cancelled."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title="Select button template image",
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()
    return path if path else None


def show_info(title: str, message: str):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showinfo(title, message)
    root.destroy()


def show_error(title: str, message: str):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showerror(title, message)
    root.destroy()


# ── Settings dialog ───────────────────────────────────────────────────────

def open_settings_dialog(current_cfg: dict, on_save) -> None:
    """Open a GUI settings window. Calls on_save(new_cfg) when the user clicks Save."""
    win = tk.Tk()
    win.title("VSCode Auto-Clicker — Settings")
    win.resizable(False, False)
    win.attributes("-topmost", True)

    # Center the window
    win.update_idletasks()
    w, h = 460, 480
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")

    pad = {"padx": 10, "pady": 4}

    # ── Mode ──
    tk.Label(win, text="Mode", font=("Segoe UI", 9, "bold")).grid(
        row=0, column=0, sticky="w", **pad)
    mode_var = tk.StringVar(value=current_cfg.get("mode", "auto_click"))
    mode_frame = tk.Frame(win)
    mode_frame.grid(row=0, column=1, sticky="w", **pad)
    tk.Radiobutton(mode_frame, text="Auto Click", variable=mode_var,
                   value="auto_click").pack(side="left")
    tk.Radiobutton(mode_frame, text="Auto Confirm", variable=mode_var,
                   value="auto_confirm").pack(side="left", padx=(10, 0))
    tk.Radiobutton(mode_frame, text="Both", variable=mode_var,
                   value="both").pack(side="left", padx=(10, 0))
    tk.Radiobutton(mode_frame, text="BG Confirm", variable=mode_var,
                   value="bg_confirm").pack(side="left", padx=(10, 0))

    # ── Scan interval ──
    tk.Label(win, text="Scan Interval (ms)").grid(row=1, column=0, sticky="w", **pad)
    interval_var = tk.IntVar(value=current_cfg.get("scan_interval_ms", 500))
    tk.Spinbox(win, from_=100, to=10000, increment=100,
               textvariable=interval_var, width=10).grid(row=1, column=1, sticky="w", **pad)

    # ── Confidence threshold ──
    tk.Label(win, text="Confidence Threshold").grid(row=2, column=0, sticky="w", **pad)
    threshold_var = tk.DoubleVar(value=current_cfg.get("confidence_threshold", 0.8))
    tk.Spinbox(win, from_=0.1, to=1.0, increment=0.05, format="%.2f",
               textvariable=threshold_var, width=10).grid(row=2, column=1, sticky="w", **pad)

    # ── Click cooldown ──
    tk.Label(win, text="Click Cooldown (sec)").grid(row=3, column=0, sticky="w", **pad)
    click_cd_var = tk.IntVar(value=current_cfg.get("click_cooldown_seconds", 3))
    tk.Spinbox(win, from_=0, to=60, increment=1,
               textvariable=click_cd_var, width=10).grid(row=3, column=1, sticky="w", **pad)

    # ── Confirm cooldown ──
    tk.Label(win, text="Confirm Cooldown (sec)").grid(row=4, column=0, sticky="w", **pad)
    confirm_cd_var = tk.IntVar(value=current_cfg.get("confirm_cooldown_seconds", 5))
    tk.Spinbox(win, from_=0, to=60, increment=1,
               textvariable=confirm_cd_var, width=10).grid(row=4, column=1, sticky="w", **pad)

    # ── Monitor index ──
    tk.Label(win, text="Monitor Index").grid(row=5, column=0, sticky="w", **pad)
    monitor_var = tk.IntVar(value=current_cfg.get("monitor_index", 0))
    mon_frame = tk.Frame(win)
    mon_frame.grid(row=5, column=1, sticky="w", **pad)
    tk.Spinbox(mon_frame, from_=0, to=10, increment=1,
               textvariable=monitor_var, width=5).pack(side="left")
    tk.Label(mon_frame, text="(0 = all)", fg="gray").pack(side="left", padx=(5, 0))

    # ── Grayscale ──
    grayscale_var = tk.BooleanVar(value=current_cfg.get("grayscale", True))
    tk.Checkbutton(win, text="Grayscale matching (faster)",
                   variable=grayscale_var).grid(row=6, column=0, columnspan=2, sticky="w", **pad)

    # ── Log level ──
    tk.Label(win, text="Log Level").grid(row=7, column=0, sticky="w", **pad)
    log_var = tk.StringVar(value=current_cfg.get("log_level", "INFO"))
    tk.OptionMenu(win, log_var, "DEBUG", "INFO", "WARNING").grid(
        row=7, column=1, sticky="w", **pad)

    # ── Scan region ──
    region = current_cfg.get("region") or {}
    tk.Label(win, text="Scan Region (optional)", font=("Segoe UI", 9, "bold")).grid(
        row=8, column=0, columnspan=2, sticky="w", **pad)

    region_frame = tk.Frame(win)
    region_frame.grid(row=9, column=0, columnspan=2, sticky="w", padx=10)

    tk.Label(region_frame, text="Left:").grid(row=0, column=0)
    left_var = tk.StringVar(value=str(region.get("left", "")))
    tk.Entry(region_frame, textvariable=left_var, width=6).grid(row=0, column=1, padx=2)

    tk.Label(region_frame, text="Top:").grid(row=0, column=2)
    top_var = tk.StringVar(value=str(region.get("top", "")))
    tk.Entry(region_frame, textvariable=top_var, width=6).grid(row=0, column=3, padx=2)

    tk.Label(region_frame, text="Width:").grid(row=0, column=4)
    width_var = tk.StringVar(value=str(region.get("width", "")))
    tk.Entry(region_frame, textvariable=width_var, width=6).grid(row=0, column=5, padx=2)

    tk.Label(region_frame, text="Height:").grid(row=0, column=6)
    height_var = tk.StringVar(value=str(region.get("height", "")))
    tk.Entry(region_frame, textvariable=height_var, width=6).grid(row=0, column=7, padx=2)

    # ── Template paths (read-only info) ──
    tk.Label(win, text="Templates", font=("Segoe UI", 9, "bold")).grid(
        row=10, column=0, columnspan=2, sticky="w", **pad)
    tk.Label(win, text=f"Click:    {current_cfg.get('template_path', '')}",
             fg="gray").grid(row=11, column=0, columnspan=2, sticky="w", padx=10)
    confirm_dir = current_cfg.get('confirm_templates_dir', 'templates/confirm')
    tk.Label(win, text=f"Confirm: {confirm_dir}/ (multiple templates)",
             fg="gray").grid(row=12, column=0, columnspan=2, sticky="w", padx=10)

    # ── Buttons ──
    def on_save_click():
        # Build region dict or None
        region_val = None
        try:
            l, t, rw, rh = left_var.get(), top_var.get(), width_var.get(), height_var.get()
            if l and t and rw and rh:
                region_val = {
                    "left": int(l), "top": int(t),
                    "width": int(rw), "height": int(rh),
                }
        except ValueError:
            pass

        new_cfg = {
            "mode": mode_var.get(),
            "template_path": current_cfg.get("template_path", "templates/button.png"),
            "confirm_template_path": current_cfg.get("confirm_template_path",
                                                     "templates/confirm_prompt.png"),
            "confirm_templates_dir": current_cfg.get("confirm_templates_dir",
                                                     "templates/confirm"),
            "scan_interval_ms": interval_var.get(),
            "confidence_threshold": round(threshold_var.get(), 2),
            "click_cooldown_seconds": click_cd_var.get(),
            "confirm_cooldown_seconds": confirm_cd_var.get(),
            "monitor_index": monitor_var.get(),
            "region": region_val,
            "grayscale": grayscale_var.get(),
            "log_level": log_var.get(),
        }
        win.destroy()
        on_save(new_cfg)

    btn_frame = tk.Frame(win)
    btn_frame.grid(row=13, column=0, columnspan=2, pady=15)
    tk.Button(btn_frame, text="Save", width=12, command=on_save_click).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Cancel", width=12, command=win.destroy).pack(side="left", padx=5)

    win.mainloop()


# ── Main app ───────────────────────────────────────────────────────────────

HOTKEY_PAUSE = "ctrl+alt+p"
HOTKEY_STOP = "ctrl+alt+q"


class ClickerApp:
    def __init__(self):
        self.running = True
        self.paused = True
        self.monitor_thread: threading.Thread | None = None
        self.tray: pystray.Icon | None = None
        self.click_count = 0
        self.confirm_count = 0
        self.last_status = "Paused — right-click or Ctrl+Alt+P to resume"
        self._template_lock = threading.Lock()
        self._pending_template_reload = False
        self._pending_mode_change: str | None = None
        # Background confirm state
        self._process_cache = ProcessCache(ttl=10.0)
        self._bg_cooldowns: dict[int, float] = {}  # pid → last confirm time
        self._bg_cursor_positions: dict[int, int] = {}  # pid → cursor_y at confirm

        cfg = load_config()
        self.mode = cfg.get("mode", "auto_click")

    def _get_template_path(self) -> Path:
        cfg = load_config()
        return APP_DIR / cfg["template_path"]

    def _get_confirm_template_path(self) -> Path:
        cfg = load_config()
        return APP_DIR / cfg.get("confirm_template_path", "templates/confirm_prompt.png")

    def _count_confirm_templates(self) -> int:
        """Count available confirm templates across directory and legacy path."""
        count = 0
        cfg = load_config()
        confirm_dir = APP_DIR / cfg.get("confirm_templates_dir", "templates/confirm")
        image_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        if confirm_dir.exists():
            count += len([f for f in confirm_dir.iterdir()
                         if f.suffix.lower() in image_exts])
        legacy_path = APP_DIR / cfg.get("confirm_template_path", "templates/confirm_prompt.png")
        if legacy_path.exists() and legacy_path.parent != confirm_dir:
            count += 1
        return count

    def build_menu(self) -> pystray.Menu:
        template_path = self._get_template_path()
        has_template = template_path.exists()
        confirm_count = self._count_confirm_templates()
        has_confirm_template = confirm_count > 0

        mode_label = {"auto_click": "Auto Click", "auto_confirm": "Auto Confirm",
                      "both": "Both", "bg_confirm": "BG Confirm",
                      }.get(self.mode, self.mode)

        return pystray.Menu(
            pystray.MenuItem(
                lambda _: self.last_status,
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda _: f"Mode: {mode_label}",
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda _: (f"Clicks: {self.click_count} | Confirms: {self.confirm_count}"
                           if self.mode == "both"
                           else f"Clicks: {self.click_count}"
                           if self.mode == "auto_click"
                           else f"Confirms: {self.confirm_count}"),
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Mode",
                pystray.Menu(
                    pystray.MenuItem(
                        "Auto Click (screen button)",
                        self.on_set_mode_click,
                        checked=lambda _: self.mode == "auto_click",
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Auto Confirm (Claude CLI)",
                        self.on_set_mode_confirm,
                        checked=lambda _: self.mode == "auto_confirm",
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Both (Click + Confirm)",
                        self.on_set_mode_both,
                        checked=lambda _: self.mode == "both",
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Background Confirm (minimized OK)",
                        self.on_set_mode_bg_confirm,
                        checked=lambda _: self.mode == "bg_confirm",
                        radio=True,
                    ),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Set Click Template...",
                self._on_set_click_template,
                visible=lambda _: self.mode in ("auto_click", "both"),
            ),
            pystray.MenuItem(
                "Add Confirm Template...",
                self._on_set_confirm_template,
                visible=lambda _: self.mode in ("auto_confirm", "both"),
            ),
            pystray.MenuItem(
                lambda _: f"Click Template: {'OK' if has_template else 'NOT SET'}",
                None,
                enabled=False,
                visible=lambda _: self.mode in ("auto_click", "both"),
            ),
            pystray.MenuItem(
                lambda _: (f"Confirm Templates: {confirm_count} loaded"
                           if confirm_count > 0
                           else "Confirm Templates: none — add via menu"),
                None,
                enabled=False,
                visible=lambda _: self.mode in ("auto_confirm", "both"),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _: ("Resume  (Ctrl+Alt+P)" if self.paused
                           else "Pause  (Ctrl+Alt+P)"),
                self.on_toggle_pause,
            ),
            pystray.MenuItem("Settings...", self.on_open_settings),
            pystray.MenuItem("Open Log File", self.on_open_log),
            pystray.MenuItem("Open Templates Folder", self.on_open_templates),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Stop  (Ctrl+Alt+Q)", self.on_stop),
        )

    def on_set_mode_click(self, icon, item):
        self._switch_mode("auto_click")

    def on_set_mode_confirm(self, icon, item):
        self._switch_mode("auto_confirm")

    def on_set_mode_both(self, icon, item):
        self._switch_mode("both")

    def on_set_mode_bg_confirm(self, icon, item):
        self._switch_mode("bg_confirm")

    def _switch_mode(self, new_mode: str):
        if self.mode == new_mode:
            return
        self.mode = new_mode
        log.info("Mode changed to: %s", new_mode)

        # Persist to config
        try:
            cfg = load_config()
            cfg["mode"] = new_mode
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=4)
        except Exception as e:
            log.warning("Could not persist mode to config: %s", e)

        # Signal monitor loop to reload template for new mode
        with self._template_lock:
            self._pending_mode_change = new_mode
            self._pending_template_reload = True

        if self.tray:
            self.tray.update_menu()

    def _on_set_click_template(self, icon, item):
        threading.Thread(
            target=lambda: self._set_template_flow("auto_click"), daemon=True,
        ).start()

    def _on_set_confirm_template(self, icon, item):
        threading.Thread(
            target=lambda: self._set_template_flow("auto_confirm"), daemon=True,
        ).start()

    def _set_template_flow(self, target_mode=None):
        if target_mode is None:
            target_mode = self.mode

        chosen = pick_template_file()
        if not chosen:
            return

        chosen_path = Path(chosen)
        cfg = load_config()

        # Pick destination based on target mode
        if target_mode == "auto_confirm":
            # Add to confirm templates directory (multiple templates supported)
            confirm_dir = APP_DIR / cfg.get("confirm_templates_dir", "templates/confirm")
            confirm_dir.mkdir(parents=True, exist_ok=True)
            dest = confirm_dir / chosen_path.name
            # Avoid overwriting existing templates
            if dest.exists():
                stem = chosen_path.stem
                suffix = chosen_path.suffix
                i = 1
                while dest.exists():
                    dest = confirm_dir / f"{stem}_{i}{suffix}"
                    i += 1
        else:
            dest = APP_DIR / cfg["template_path"]
            dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(chosen_path, dest)
            log.info("Template added: %s -> %s", chosen_path.name, dest)
        except Exception as e:
            log.error("Failed to copy template: %s", e)
            show_error("Template Error", f"Could not copy file:\n{e}")
            return

        # Signal the monitor loop to reload
        with self._template_lock:
            self._pending_template_reload = True

        if target_mode == "auto_confirm":
            total = self._count_confirm_templates()
            show_info(
                "Confirm Template Added",
                f"Added confirm template:\n{dest.name}\n\n"
                f"Size: {PIL.Image.open(dest).size[0]}x{PIL.Image.open(dest).size[1]} pixels\n"
                f"Total confirm templates: {total}\n\n"
                "The monitor will use the new template immediately.\n"
                "Tip: Capture just the '> 1. Yes' line for best results."
            )
        else:
            show_info(
                "Template Updated",
                f"Click template image set to:\n{chosen_path.name}\n\n"
                f"Size: {PIL.Image.open(dest).size[0]}x{PIL.Image.open(dest).size[1]} pixels\n\n"
                "The monitor will use the new template immediately."
            )

        if self.tray:
            self.tray.update_menu()

    def toggle_pause(self):
        """Toggle pause/resume — called by both tray menu and hotkey."""
        self.paused = not self.paused
        if self.paused:
            self.last_status = "Paused"
            log.info("Paused by user.")
        else:
            self.last_status = "Monitoring..."
            log.info("Resumed by user.")
        if self.tray:
            self.tray.icon = create_tray_icon_image(
                "yellow" if self.paused else "green")
            self.tray.update_menu()

    def on_toggle_pause(self, icon, item):
        self.toggle_pause()

    def on_open_settings(self, icon, item):
        threading.Thread(target=self._settings_flow, daemon=True).start()

    def _settings_flow(self):
        cfg = load_config()

        def on_save(new_cfg):
            try:
                with open(CONFIG_PATH, "w") as f:
                    json.dump(new_cfg, f, indent=4)
                    f.write("\n")
                log.info("Settings saved.")
            except Exception as e:
                log.error("Failed to save settings: %s", e)
                show_error("Settings Error", f"Could not save config:\n{e}")
                return

            # Apply mode change if needed
            if new_cfg.get("mode") != self.mode:
                self._switch_mode(new_cfg["mode"])
            else:
                # Trigger a config + template reload
                with self._template_lock:
                    self._pending_template_reload = True

            if self.tray:
                self.tray.update_menu()

        open_settings_dialog(cfg, on_save)

    def on_open_log(self, icon, item):
        os.startfile(str(LOG_PATH))

    def on_open_templates(self, icon, item):
        if self.mode == "auto_confirm":
            cfg = load_config()
            confirm_dir = APP_DIR / cfg.get("confirm_templates_dir", "templates/confirm")
            confirm_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(confirm_dir))
        else:
            TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(TEMPLATES_DIR))

    def on_stop(self, icon=None, item=None):
        log.info("Stopping application...")
        self.running = False
        self._unregister_hotkeys()
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        # Force exit to ensure no threads keep the process alive
        os._exit(0)

    def _register_hotkeys(self):
        """Register global keyboard hotkeys for pause/resume and stop."""
        try:
            keyboard.add_hotkey(HOTKEY_PAUSE, self.toggle_pause, suppress=False)
            keyboard.add_hotkey(HOTKEY_STOP, self.on_stop, suppress=False)
            log.info("Hotkeys registered: %s = pause/resume, %s = stop",
                     HOTKEY_PAUSE, HOTKEY_STOP)
        except Exception as e:
            log.warning("Failed to register hotkeys: %s", e)

    def _unregister_hotkeys(self):
        """Remove all registered hotkeys."""
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

    def _get_active_template_path_key(self) -> str:
        """Return the config key for the template path based on current mode."""
        if self.mode == "auto_confirm":
            return "confirm_template_path"
        return "template_path"

    def monitor_loop(self):
        """Main screen monitoring loop — runs in a background thread."""
        try:
            cfg = load_config()
            logging.getLogger().setLevel(cfg.get("log_level", "INFO"))

            grayscale = cfg.get("grayscale", True)
            if self.mode in ("auto_confirm", "both"):
                confirm_templates = load_confirm_templates(cfg, grayscale)
            else:
                confirm_templates = []
            if self.mode in ("auto_click", "both"):
                template = load_template(cfg["template_path"], grayscale)
            else:
                template = None
            threshold = cfg["confidence_threshold"]
            interval = cfg["scan_interval_ms"] / 1000.0
            click_cooldown = cfg["click_cooldown_seconds"]
            confirm_cooldown = cfg.get("confirm_cooldown_seconds", 5)
            monitor_index = cfg.get("monitor_index", 0)
            region = cfg.get("region")

            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.05

            last_click_time = 0.0
            last_confirm_time = 0.0

            mode_label = {"auto_click": "Auto Click", "auto_confirm": "Auto Confirm",
                      "both": "Both", "bg_confirm": "BG Confirm",
                      }.get(self.mode, self.mode)
            log.info("=== VSCode Button %s ===", mode_label)
            log.info("Mode: %s | Threshold: %.2f | Interval: %dms",
                     self.mode, threshold, cfg["scan_interval_ms"])

            if self.mode == "bg_confirm":
                has_templates = True  # No templates needed
            elif self.mode == "both":
                has_templates = template is not None or len(confirm_templates) > 0
            elif self.mode == "auto_confirm":
                has_templates = len(confirm_templates) > 0
            else:
                has_templates = template is not None
            if not has_templates:
                self.last_status = "No template — set one via tray menu"
                if self.tray:
                    self.tray.icon = create_tray_icon_image("yellow")
                    self.tray.update_menu()
            else:
                self.last_status = "Monitoring..."
                if self.tray:
                    self.tray.update_menu()

            with mss.mss() as sct:
                while self.running:
                    # Check for template reload or mode change
                    with self._template_lock:
                        if self._pending_template_reload:
                            self._pending_template_reload = False
                            if self._pending_mode_change:
                                self._pending_mode_change = None
                            cfg = load_config()
                            if self.mode in ("auto_confirm", "both"):
                                confirm_templates = load_confirm_templates(
                                    cfg, grayscale)
                            else:
                                confirm_templates = []
                            if self.mode in ("auto_click", "both"):
                                new_tpl = load_template(
                                    cfg.get("template_path", "templates/button.png"),
                                    grayscale,
                                )
                                template = new_tpl
                            else:
                                template = None

                            if self.mode == "bg_confirm":
                                has_templates = True
                            elif self.mode == "both":
                                has_templates = (template is not None
                                                 or len(confirm_templates) > 0)
                            elif self.mode == "auto_confirm":
                                has_templates = len(confirm_templates) > 0
                            else:
                                has_templates = template is not None

                            if has_templates:
                                self.last_status = "Monitoring..."
                                if self.tray:
                                    self.tray.icon = create_tray_icon_image("green")
                                    self.tray.update_menu()
                            else:
                                self.last_status = "No template — set one via tray menu"
                                if self.tray:
                                    self.tray.icon = create_tray_icon_image("yellow")
                                    self.tray.update_menu()

                            # Reload config values that may have changed
                            threshold = cfg["confidence_threshold"]
                            interval = cfg["scan_interval_ms"] / 1000.0
                            click_cooldown = cfg["click_cooldown_seconds"]
                            confirm_cooldown = cfg.get("confirm_cooldown_seconds", 5)
                            monitor_index = cfg.get("monitor_index", 0)
                            region = cfg.get("region")

                    if self.paused or not has_templates:
                        time.sleep(0.25)
                        continue

                    start = time.perf_counter()
                    acted = False

                    # ── Background Confirm mode ──
                    if self.mode == "bg_confirm":
                        now = time.time()
                        for pid in self._process_cache.get_pids():
                            try:
                                lines, cursor_y = read_console_buffer(
                                    pid, num_lines=15)
                                # Skip if cursor hasn't moved since last confirm
                                prev_y = self._bg_cursor_positions.get(pid, -1)
                                if cursor_y <= prev_y:
                                    continue
                                match = detect_prompt(lines)
                                if not match:
                                    continue
                                # Per-process cooldown
                                last_t = self._bg_cooldowns.get(pid, 0.0)
                                if now - last_t < confirm_cooldown:
                                    continue
                                pattern, response = match
                                send_console_keys(pid, response)
                                self._bg_cooldowns[pid] = now
                                self._bg_cursor_positions[pid] = cursor_y
                                self.confirm_count += 1
                                self.last_status = (
                                    f"BG Confirmed PID {pid}")
                                log.info("BG confirm: sent '%s' to PID %d"
                                         " (pattern: %s)", response, pid,
                                         pattern)
                                acted = True
                                break  # One confirm per cycle
                            except OSError as exc:
                                log.debug("PID %d: %s", pid, exc)
                    else:
                        # ── Visual matching modes ──
                        screen, mon = grab_screen(
                            sct, monitor_index, region, grayscale)

                        # Check for confirm match (higher priority)
                        confirm_match = None
                        if (self.mode in ("auto_confirm", "both")
                                and confirm_templates):
                            confirm_match = find_any_match(
                                screen, confirm_templates, threshold)

                        # Check for click match
                        click_match = None
                        if (self.mode in ("auto_click", "both")
                                and template is not None):
                            click_match = find_button(
                                screen, template, threshold)

                        now = time.time()

                        if confirm_match:
                            cx, cy, confidence = confirm_match
                            abs_x = mon["left"] + cx
                            abs_y = mon["top"] + cy
                            if now - last_confirm_time >= confirm_cooldown:
                                log.info(
                                    "Confirm prompt found (confidence=%.3f)"
                                    " at (%d, %d)", confidence, abs_x, abs_y)
                                confirm_at(abs_x, abs_y)
                                last_confirm_time = now
                                self.confirm_count += 1
                                self.last_status = (
                                    f"Confirmed at ({abs_x}, {abs_y})")
                                acted = True
                            else:
                                remaining = confirm_cooldown - (
                                    now - last_confirm_time)
                                log.debug("Confirm match but in cooldown"
                                          " (%.1fs left)", remaining)

                        if click_match and not acted:
                            cx, cy, confidence = click_match
                            abs_x = mon["left"] + cx
                            abs_y = mon["top"] + cy
                            if now - last_click_time >= click_cooldown:
                                log.info(
                                    "Button found (confidence=%.3f)"
                                    " at (%d, %d)", confidence, abs_x, abs_y)
                                click_at(abs_x, abs_y)
                                last_click_time = now
                                self.click_count += 1
                                self.last_status = (
                                    f"Clicked at ({abs_x}, {abs_y})")
                                acted = True
                            else:
                                remaining = click_cooldown - (
                                    now - last_click_time)
                                log.debug("Click match but in cooldown"
                                          " (%.1fs left)", remaining)

                    if acted and self.tray:
                        self.tray.icon = create_tray_icon_image("blue")
                        self.tray.update_menu()
                        time.sleep(0.3)
                        self.tray.icon = create_tray_icon_image("green")

                    elapsed = time.perf_counter() - start
                    sleep_time = max(0, interval - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)

        except Exception:
            log.exception("Monitor loop crashed")
            self.last_status = "Error — check log"
            if self.tray:
                self.tray.icon = create_tray_icon_image("red")
                self.tray.update_menu()

    def run(self):
        self._register_hotkeys()

        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

        self.tray = pystray.Icon(
            name="VSCode Auto-Clicker",
            icon=create_tray_icon_image("yellow"),
            title="VSCode Auto-Clicker — Paused",
            menu=self.build_menu(),
        )
        self.tray.run()


if __name__ == "__main__":
    app = ClickerApp()

    # Ensure clean shutdown on kill signals (Ctrl+C, taskkill, etc.)
    def _shutdown_handler(signum, frame):
        log.info("Received signal %s, shutting down.", signum)
        app.on_stop()

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _shutdown_handler)

    # Safety net: force kill on exit if threads are stuck
    atexit.register(lambda: os._exit(0))

    app.run()
