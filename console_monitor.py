"""
Console Monitor — Background terminal monitoring via Win32 Console API.

Reads terminal text directly from console buffers and sends keystrokes,
working even when windows are minimized or not in focus.
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import re
import threading
import time
from contextlib import contextmanager

import psutil

log = logging.getLogger("clicker.console")

# ── Win32 Constants ──────────────────────────────────────────────────────

kernel32 = ctypes.windll.kernel32

ATTACH_PARENT_PROCESS = 0xFFFFFFFF
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
KEY_EVENT = 0x0001
VK_RETURN = 0x0D


# ── Win32 Structures ─────────────────────────────────────────────────────

class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [
        ("Left", ctypes.c_short), ("Top", ctypes.c_short),
        ("Right", ctypes.c_short), ("Bottom", ctypes.c_short),
    ]


class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", COORD),
        ("dwCursorPosition", COORD),
        ("wAttributes", ctypes.c_ushort),
        ("srWindow", SMALL_RECT),
        ("dwMaximumWindowSize", COORD),
    ]


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("uChar", ctypes.c_wchar),
        ("dwControlKeyState", wintypes.DWORD),
    ]


class _EventUnion(ctypes.Union):
    _fields_ = [("KeyEvent", KEY_EVENT_RECORD)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [
        ("EventType", wintypes.WORD),
        ("Event", _EventUnion),
    ]


# ── Function prototypes ─────────────────────────────────────────────────

kernel32.AttachConsole.argtypes = [wintypes.DWORD]
kernel32.AttachConsole.restype = wintypes.BOOL

kernel32.FreeConsole.argtypes = []
kernel32.FreeConsole.restype = wintypes.BOOL

kernel32.GetConsoleWindow.argtypes = []
kernel32.GetConsoleWindow.restype = wintypes.HWND

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE

kernel32.GetConsoleScreenBufferInfo.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(CONSOLE_SCREEN_BUFFER_INFO),
]
kernel32.GetConsoleScreenBufferInfo.restype = wintypes.BOOL

kernel32.ReadConsoleOutputCharacterW.argtypes = [
    wintypes.HANDLE, ctypes.c_wchar_p, wintypes.DWORD,
    ctypes.c_ulong,  # COORD passed as DWORD by value
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.ReadConsoleOutputCharacterW.restype = wintypes.BOOL

kernel32.WriteConsoleInputW.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(INPUT_RECORD),
    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
]
kernel32.WriteConsoleInputW.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD


# ── Console attachment ───────────────────────────────────────────────────

_console_lock = threading.Lock()


@contextmanager
def _attached_console(pid: int):
    """Attach to a process's console, yield, then restore previous state."""
    with _console_lock:
        # Always free first — GetConsoleWindow() returns 0 for ConPTY
        # but the process may still be attached to a pseudo-console.
        kernel32.FreeConsole()
        attached = False
        try:
            if not kernel32.AttachConsole(wintypes.DWORD(pid)):
                err = kernel32.GetLastError()
                raise OSError(f"AttachConsole({pid}) failed: error {err}")
            attached = True
            yield
        finally:
            if attached:
                kernel32.FreeConsole()
            # Reattach to parent console (best-effort)
            kernel32.AttachConsole(wintypes.DWORD(ATTACH_PARENT_PROCESS))


def _open_handle(name: str, access: int):
    """Open CONOUT$ or CONIN$ handle."""
    h = kernel32.CreateFileW(
        name, access, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None,
    )
    if h == INVALID_HANDLE_VALUE or h is None:
        raise OSError(f"CreateFileW({name}) failed: error {kernel32.GetLastError()}")
    return h


# ── Read / Write ─────────────────────────────────────────────────────────

def read_console_buffer(pid: int, num_lines: int = 15) -> tuple[list[str], int]:
    """
    Read the last *num_lines* near the cursor from a process's console.

    Returns (lines, cursor_y).
    """
    with _attached_console(pid):
        handle = _open_handle("CONOUT$", GENERIC_READ)
        try:
            info = CONSOLE_SCREEN_BUFFER_INFO()
            if not kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
                raise OSError("GetConsoleScreenBufferInfo failed")

            width = info.dwSize.X
            cursor_y = info.dwCursorPosition.Y

            start_y = max(0, cursor_y - num_lines + 1)
            lines: list[str] = []

            for y in range(start_y, cursor_y + 1):
                buf = ctypes.create_unicode_buffer(width + 1)
                chars_read = wintypes.DWORD()
                # COORD by value: X in low word, Y in high word
                coord = ctypes.c_ulong((y << 16) | 0)
                kernel32.ReadConsoleOutputCharacterW(
                    handle, buf, wintypes.DWORD(width),
                    coord, ctypes.byref(chars_read),
                )
                lines.append(buf.value.rstrip())

            return lines, cursor_y
        finally:
            kernel32.CloseHandle(handle)


def send_console_keys(pid: int, text: str) -> None:
    """Send *text* followed by Enter to a process's console input buffer."""
    with _attached_console(pid):
        handle = _open_handle("CONIN$", GENERIC_WRITE)
        try:
            chars = list(text) + ["\r"]
            records = (INPUT_RECORD * (len(chars) * 2))()

            for i, ch in enumerate(chars):
                vk = VK_RETURN if ch == "\r" else 0
                # Key down
                r_down = records[i * 2]
                r_down.EventType = KEY_EVENT
                r_down.Event.KeyEvent.bKeyDown = True
                r_down.Event.KeyEvent.wRepeatCount = 1
                r_down.Event.KeyEvent.wVirtualKeyCode = vk
                r_down.Event.KeyEvent.uChar = ch
                r_down.Event.KeyEvent.dwControlKeyState = 0
                # Key up
                r_up = records[i * 2 + 1]
                r_up.EventType = KEY_EVENT
                r_up.Event.KeyEvent.bKeyDown = False
                r_up.Event.KeyEvent.wRepeatCount = 1
                r_up.Event.KeyEvent.wVirtualKeyCode = vk
                r_up.Event.KeyEvent.uChar = ch
                r_up.Event.KeyEvent.dwControlKeyState = 0

            written = wintypes.DWORD()
            if not kernel32.WriteConsoleInputW(
                handle, records, len(records), ctypes.byref(written),
            ):
                raise OSError(
                    f"WriteConsoleInputW failed: error {kernel32.GetLastError()}")
            log.debug("Sent %d key events to PID %d", written.value, pid)
        finally:
            kernel32.CloseHandle(handle)


# ── Prompt detection ─────────────────────────────────────────────────────

# (pattern, response_to_send)
PROMPT_PATTERNS: list[tuple[str, str]] = [
    (r">\s*1\.\s*Yes", "1"),       # Numbered options with > selector
    (r"\[y/N\]", "y"),             # [y/N] confirmation
    (r"\(y/n\)", "y"),             # (y/n) confirmation
]

# At least one context pattern must also appear to reduce false positives
CONTEXT_PATTERNS: list[str] = [
    r"Do you want to proceed",
    r"Do you want to allow",
    r"Do you want to make",
    r"requires approval",
    r"Esc to cancel",
    r"Yes,?\s+and don.t ask again",
    r"No.*\(esc\)",
]


def detect_prompt(lines: list[str]) -> tuple[str, str] | None:
    """
    Check if *lines* contain a Claude Code confirmation prompt.

    Returns ``(matched_pattern, response)`` or ``None``.
    """
    if not lines:
        return None

    text = "\n".join(lines)

    for pattern, response in PROMPT_PATTERNS:
        if re.search(pattern, text):
            if any(re.search(cp, text, re.IGNORECASE) for cp in CONTEXT_PATTERNS):
                return pattern, response

    return None


# ── Process discovery ────────────────────────────────────────────────────

TARGET_PROCESS_NAMES = frozenset({
    "cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe",
})


class ProcessCache:
    """Cache target process PIDs with a TTL to avoid repeated full scans."""

    def __init__(self, ttl: float = 10.0):
        self._pids: list[int] = []
        self._last_scan = 0.0
        self._ttl = ttl
        self._own_pid = os.getpid()

    def get_pids(self) -> list[int]:
        now = time.time()
        if now - self._last_scan > self._ttl:
            self._rescan()
            self._last_scan = now
        return list(self._pids)

    def _rescan(self):
        pids: list[int] = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info["name"]
                pid = proc.info["pid"]
                if (name and name.lower() in TARGET_PROCESS_NAMES
                        and pid != self._own_pid):
                    pids.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        self._pids = pids
        if pids:
            log.debug("Process scan: %d console targets", len(pids))

    def invalidate(self):
        self._last_scan = 0.0
