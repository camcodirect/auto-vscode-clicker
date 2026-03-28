"""
VSCode Button Auto-Clicker

Monitors the screen for a template image (button) and clicks it when found.
Runs as a system tray application with right-click menu to control.
Uses OpenCV template matching with mss for fast screenshots.
"""

import atexit
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
import mss
import numpy as np
import PIL.Image
import PIL.ImageDraw
import pyautogui
import pystray


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
    pyautogui.click(x, y)
    log.info("Clicked at (%d, %d)", x, y)


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


# ── Main app ───────────────────────────────────────────────────────────────

class ClickerApp:
    def __init__(self):
        self.running = True
        self.paused = False
        self.monitor_thread: threading.Thread | None = None
        self.tray: pystray.Icon | None = None
        self.click_count = 0
        self.last_status = "Starting..."
        self._template_lock = threading.Lock()
        self._pending_template_reload = False

    def _get_template_path(self) -> Path:
        cfg = load_config()
        return APP_DIR / cfg["template_path"]

    def build_menu(self) -> pystray.Menu:
        template_path = self._get_template_path()
        has_template = template_path.exists()

        return pystray.Menu(
            pystray.MenuItem(
                lambda _: self.last_status,
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda _: f"Clicks: {self.click_count}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Set Template Image...",
                self.on_set_template,
            ),
            pystray.MenuItem(
                lambda _: f"Template: {'OK' if has_template else 'NOT SET'}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _: "Resume" if self.paused else "Pause",
                self.on_toggle_pause,
            ),
            pystray.MenuItem("Open Log File", self.on_open_log),
            pystray.MenuItem("Open Config", self.on_open_config),
            pystray.MenuItem("Open Templates Folder", self.on_open_templates),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Stop", self.on_stop),
        )

    def on_set_template(self, icon, item):
        """Let the user pick an image file, copy it to templates/button.png, and reload."""
        threading.Thread(target=self._set_template_flow, daemon=True).start()

    def _set_template_flow(self):
        chosen = pick_template_file()
        if not chosen:
            return

        chosen_path = Path(chosen)
        cfg = load_config()
        dest = APP_DIR / cfg["template_path"]

        # Ensure templates dir exists
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(chosen_path, dest)
            log.info("Template updated: %s -> %s", chosen_path.name, dest)
        except Exception as e:
            log.error("Failed to copy template: %s", e)
            show_error("Template Error", f"Could not copy file:\n{e}")
            return

        # Signal the monitor loop to reload
        with self._template_lock:
            self._pending_template_reload = True

        show_info(
            "Template Updated",
            f"Template image set to:\n{chosen_path.name}\n\n"
            f"Size: {PIL.Image.open(dest).size[0]}x{PIL.Image.open(dest).size[1]} pixels\n\n"
            "The monitor will use the new template immediately."
        )

        if self.tray:
            self.tray.update_menu()

    def on_toggle_pause(self, icon, item):
        self.paused = not self.paused
        if self.paused:
            self.last_status = "Paused"
            icon.icon = create_tray_icon_image("yellow")
            log.info("Paused by user.")
        else:
            self.last_status = "Monitoring..."
            icon.icon = create_tray_icon_image("green")
            log.info("Resumed by user.")
        icon.update_menu()

    def on_open_log(self, icon, item):
        os.startfile(str(LOG_PATH))

    def on_open_config(self, icon, item):
        os.startfile(str(CONFIG_PATH))

    def on_open_templates(self, icon, item):
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(TEMPLATES_DIR))

    def on_stop(self, icon=None, item=None):
        log.info("Stopping application...")
        self.running = False
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        # Force exit to ensure no threads keep the process alive
        os._exit(0)

    def monitor_loop(self):
        """Main screen monitoring loop — runs in a background thread."""
        try:
            cfg = load_config()
            logging.getLogger().setLevel(cfg.get("log_level", "INFO"))

            grayscale = cfg.get("grayscale", True)
            template = load_template(cfg["template_path"], grayscale)
            threshold = cfg["confidence_threshold"]
            interval = cfg["scan_interval_ms"] / 1000.0
            cooldown = cfg["click_cooldown_seconds"]
            monitor_index = cfg.get("monitor_index", 0)
            region = cfg.get("region")

            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.05

            last_click_time = 0.0

            log.info("=== VSCode Button Auto-Clicker ===")
            log.info("Threshold: %.2f | Interval: %dms | Cooldown: %ds",
                     threshold, cfg["scan_interval_ms"], cooldown)

            if template is None:
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
                    # Check for template reload
                    with self._template_lock:
                        if self._pending_template_reload:
                            self._pending_template_reload = False
                            cfg = load_config()
                            new_template = load_template(cfg["template_path"], grayscale)
                            if new_template is not None:
                                template = new_template
                                self.last_status = "Monitoring..."
                                if self.tray:
                                    self.tray.icon = create_tray_icon_image("green")
                                    self.tray.update_menu()
                            else:
                                self.last_status = "Template load failed"
                                if self.tray:
                                    self.tray.icon = create_tray_icon_image("red")
                                    self.tray.update_menu()

                    if self.paused or template is None:
                        time.sleep(0.25)
                        continue

                    start = time.perf_counter()

                    screen, mon = grab_screen(sct, monitor_index, region, grayscale)
                    match = find_button(screen, template, threshold)

                    if match:
                        cx, cy, confidence = match
                        abs_x = mon["left"] + cx
                        abs_y = mon["top"] + cy

                        now = time.time()
                        if now - last_click_time >= cooldown:
                            log.info("Button found (confidence=%.3f) at (%d, %d)",
                                     confidence, abs_x, abs_y)
                            click_at(abs_x, abs_y)
                            last_click_time = now
                            self.click_count += 1
                            self.last_status = f"Clicked at ({abs_x}, {abs_y})"

                            if self.tray:
                                self.tray.icon = create_tray_icon_image("blue")
                                self.tray.update_menu()
                                time.sleep(0.3)
                                self.tray.icon = create_tray_icon_image("green")
                        else:
                            remaining = cooldown - (now - last_click_time)
                            log.debug("Button visible but in cooldown (%.1fs left)", remaining)

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
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

        self.tray = pystray.Icon(
            name="VSCode Auto-Clicker",
            icon=create_tray_icon_image("green"),
            title="VSCode Auto-Clicker",
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
