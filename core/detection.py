import re
import threading
import time
import keyboard
import mss
import numpy as np
from PIL import Image, ImageEnhance
from core.crash_logger import get_logger

log = get_logger("questlog.detection")

DEATH_HOTKEY = "f9"
KILL_HOTKEY  = "f10"
RESET_HOTKEY = "f8"

# Normalized fractions of screen — works across 1080p/1440p/ultrawide
SCAN_REGION = {"cx": 0.50, "cy": 0.52, "w": 0.35, "h": 0.10}

DEATH_COOLDOWN = 8.0
KILL_COOLDOWN  = 4.0
POLL_INTERVAL  = 1.0

YOU_DIED_TEXT = "you died"
# Reforged uses dark crimson text that OCR misreads — fuzzy match on what we actually see
_YOU_DIED_RE  = re.compile(r'[xyv]?[yoeui][a-z#]{0,4}\s?d[a-z]?[ti]?ed')


def _find_game_monitor(title_keyword, sct):
    """
    Returns the mss monitor index (1-based) within the given sct context that
    contains the window whose title matches title_keyword.
    Uses only Win32 window/monitor APIs — no screen scanning.
    """
    try:
        import ctypes
        import ctypes.wintypes as wt

        user32 = ctypes.windll.user32
        found_rect = None
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

        def _cb(hwnd, _):
            nonlocal found_rect
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if title_keyword.lower() in buf.value.lower():
                rect = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                found_rect = rect
                return False
            return True

        user32.EnumWindows(EnumWindowsProc(_cb), 0)

        if found_rect is None:
            log.info("Game window '%s' not found — using primary monitor", title_keyword)
            return None

        cx = (found_rect.left + found_rect.right) // 2
        cy = (found_rect.top + found_rect.bottom) // 2

        for i, m in enumerate(sct.monitors[1:], start=1):
            if (m["left"] <= cx < m["left"] + m["width"] and
                    m["top"] <= cy < m["top"] + m["height"]):
                log.info("Auto-detected game on monitor [%d]", i)
                return i
    except Exception:
        pass
    return None


def _load_ocr():
    import warnings
    warnings.filterwarnings("ignore", message="'pin_memory'")
    import easyocr
    return easyocr.Reader(["en"], gpu=False, verbose=False)


class Detector:
    def __init__(self, death_tracker, on_death=None, on_kill=None, on_grace=None, on_reset=None, monitor=None, game_title="ELDEN RING"):
        self.death_tracker = death_tracker
        self.on_death  = on_death or (lambda: None)
        self.on_kill   = on_kill  or (lambda: None)
        self.on_reset  = on_reset or (lambda: None)
        self._running          = False
        self._ocr_thread       = None
        self._ocr_reader       = None
        self._ocr_ready        = False
        self._last_death_time  = 0
        self._last_kill_time   = 0
        self._in_death_screen  = False
        self._reset_hold_start = None
        self._game_title            = game_title
        self._monitor_override      = monitor  # None = auto-detect
        self._force_monitor_recheck = False

    def set_monitor(self, index):
        self._monitor_override = index
        self._force_monitor_recheck = True
        if index is None:
            log.info("Game monitor set to auto-detect")
        else:
            log.info("Game monitor manually overridden to %d", index)

    def start(self):
        self._running = True
        keyboard.add_hotkey(DEATH_HOTKEY, self._manual_death, suppress=False)
        keyboard.add_hotkey(KILL_HOTKEY,  self._manual_kill,  suppress=False)
        keyboard.on_press_key(RESET_HOTKEY,   self._reset_key_down, suppress=False)
        keyboard.on_release_key(RESET_HOTKEY, self._reset_key_up,   suppress=False)

        threading.Thread(target=self._init_ocr, daemon=True).start()

        log.info("Hotkeys active: %s=death  %s=kill  %s=hold 3s to reset",
                 DEATH_HOTKEY.upper(), KILL_HOTKEY.upper(), RESET_HOTKEY.upper())
        log.info("Loading OCR engine in background...")

    def stop(self):
        self._running = False
        try:
            keyboard.remove_hotkey(DEATH_HOTKEY)
            keyboard.remove_hotkey(KILL_HOTKEY)
            keyboard.unhook_key(RESET_HOTKEY)
        except Exception:
            pass

    def _init_ocr(self):
        try:
            self._ocr_reader = _load_ocr()
            self._ocr_ready  = True
            log.info("OCR ready — YOU DIED detection active.")
            self._ocr_thread = threading.Thread(target=self._ocr_loop, daemon=True)
            self._ocr_thread.start()
        except Exception:
            log.exception("OCR failed to load — running in hotkey-only mode.")

    def _manual_death(self):
        log.info("Manual death (F9)")
        self.on_death()

    def _manual_kill(self):
        log.info("Manual kill (F10)")
        self.on_kill()

    def _reset_key_down(self, event):
        if self._reset_hold_start is None:
            self._reset_hold_start = time.time()
            threading.Thread(target=self._reset_hold_watch, daemon=True).start()

    def _reset_key_up(self, event):
        self._reset_hold_start = None

    def _reset_hold_watch(self):
        start = self._reset_hold_start
        while self._reset_hold_start is not None:
            if time.time() - start >= 3.0:
                self._reset_hold_start = None
                self.on_reset()
                return
            time.sleep(0.05)

    def _resolve_monitor(self, sct):
        n = len(sct.monitors) - 1  # number of real monitors (index 0 is virtual combined)
        if self._monitor_override is not None:
            return max(1, min(self._monitor_override, n))
        detected = _find_game_monitor(self._game_title, sct)
        if detected is not None:
            return max(1, min(detected, n))
        for i, m in enumerate(sct.monitors[1:], start=1):
            if m["left"] == 0 and m["top"] == 0:
                return i
        return 1

    def _ocr_loop(self):
        _cached_monitor_idx = None
        with mss.mss() as sct:
            while self._running:
                try:
                    if _cached_monitor_idx is None or self._force_monitor_recheck:
                        self._force_monitor_recheck = False
                        _cached_monitor_idx = min(self._resolve_monitor(sct), len(sct.monitors) - 1)
                        log.info("Scanning monitor [%d]: %dx%d",
                                 _cached_monitor_idx,
                                 sct.monitors[_cached_monitor_idx]["width"],
                                 sct.monitors[_cached_monitor_idx]["height"])
                    monitor = sct.monitors[_cached_monitor_idx]
                    region  = self._get_region(monitor)
                    img     = np.array(sct.grab(region))[:, :, :3]
                    text    = self._run_ocr(img)

                    if YOU_DIED_TEXT in text or _YOU_DIED_RE.search(text):
                        now = time.time()
                        if not self._in_death_screen and now - self._last_death_time > DEATH_COOLDOWN:
                            self._in_death_screen = True
                            self._last_death_time = now
                            log.info("YOU DIED — OCR confirmed")
                            self.on_death()
                    else:
                        self._in_death_screen = False

                except Exception:
                    log.exception("Error in OCR scan loop")
                time.sleep(POLL_INTERVAL)

    def _get_region(self, monitor):
        mw = monitor["width"]
        mh = monitor["height"]
        rw = int(mw * SCAN_REGION["w"])
        rh = int(mh * SCAN_REGION["h"])
        cx = monitor["left"] + int(mw * SCAN_REGION["cx"])
        cy = monitor["top"]  + int(mh * SCAN_REGION["cy"])
        return {
            "top":    cy - rh // 2,
            "left":   cx - rw // 2,
            "width":  rw,
            "height": rh,
        }

    def _run_ocr(self, img_array):
        img = Image.fromarray(img_array).convert("L")
        img = ImageEnhance.Contrast(img).enhance(3.0)
        img = ImageEnhance.Brightness(img).enhance(1.5)
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
        img_np = np.array(img)
        results = self._ocr_reader.readtext(img_np, detail=0, paragraph=True)
        return " ".join(results).lower()
