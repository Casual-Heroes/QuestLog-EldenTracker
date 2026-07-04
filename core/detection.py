import threading
import time
import keyboard
from core.crash_logger import get_logger

log = get_logger("questlog.detection")

DEFAULT_HOTKEYS = {
    "death":    "f9",
    "subtract": "f10",
    "reset":    "f8",
}

_VALID_HOTKEY_RE = __import__("re").compile(r"^[a-z0-9 +\-]+$", __import__("re").IGNORECASE)

def _validate_hotkey(key: str) -> str:
    """Return key unchanged if it looks safe, else fall back to empty string."""
    if key and _VALID_HOTKEY_RE.match(key):
        return key
    log.warning("Ignoring suspicious hotkey value: %r", key)
    return ""


class Detector:
    def __init__(self, death_tracker, on_death=None, on_subtract=None, on_reset=None, hotkeys=None):
        self.death_tracker     = death_tracker
        self.on_death          = on_death    or (lambda: None)
        self.on_subtract       = on_subtract or (lambda: None)
        self.on_reset          = on_reset    or (lambda: None)
        self._hotkeys          = {**DEFAULT_HOTKEYS, **(hotkeys or {})}
        self._running          = False
        self._reset_hold_start = None
        self._reset_lock       = threading.Lock()

    def update_hotkeys(self, hotkeys):
        """Re-register hotkeys without restarting the detector."""
        self._unhook()
        self._hotkeys = {**DEFAULT_HOTKEYS, **hotkeys}
        self._hook()
        log.info("Hotkeys updated: death=%s  subtract=%s  reset=%s (hold 3s)",
                 self._hotkeys["death"].upper(),
                 self._hotkeys["subtract"].upper(),
                 self._hotkeys["reset"].upper())

    def start(self):
        self._running = True
        self._hook()
        log.info("Hotkeys active: %s=death  %s=subtract  %s=hold 3s to reset",
                 self._hotkeys["death"].upper(),
                 self._hotkeys["subtract"].upper(),
                 self._hotkeys["reset"].upper())

    def stop(self):
        self._running = False
        self._unhook()

    def _hook(self):
        self._hooks = []
        try:
            hk_death    = _validate_hotkey(self._hotkeys.get("death", ""))
            hk_subtract = _validate_hotkey(self._hotkeys.get("subtract", ""))
            hk_reset    = _validate_hotkey(self._hotkeys.get("reset", ""))
            if hk_death:
                self._hooks.append(keyboard.on_press_key(hk_death,    lambda _: self._on_death(),    suppress=False))
            if hk_subtract:
                self._hooks.append(keyboard.on_press_key(hk_subtract, lambda _: self._on_subtract(), suppress=False))
            if hk_reset:
                self._hooks.append(keyboard.on_press_key(hk_reset,    self._reset_key_down,           suppress=False))
                self._hooks.append(keyboard.on_release_key(hk_reset,  self._reset_key_up))
        except Exception:
            log.exception("Failed to register hotkeys")

    def _unhook(self):
        for h in getattr(self, "_hooks", []):
            try:
                keyboard.unhook(h)
            except Exception:
                pass
        self._hooks = []

    def _on_death(self):
        log.info("Death hotkey (%s)", self._hotkeys["death"].upper())
        self.on_death()

    def _on_subtract(self):
        log.info("Subtract hotkey (%s)", self._hotkeys["subtract"].upper())
        self.on_subtract()

    def _reset_key_down(self, event):
        with self._reset_lock:
            if self._reset_hold_start is None:
                self._reset_hold_start = time.time()
                threading.Thread(target=self._reset_hold_watch, daemon=True).start()

    def _reset_key_up(self, event):
        with self._reset_lock:
            self._reset_hold_start = None

    def _reset_hold_watch(self):
        with self._reset_lock:
            start = self._reset_hold_start
        while True:
            with self._reset_lock:
                if self._reset_hold_start is None:
                    return
                if time.time() - start >= 3.0:
                    self._reset_hold_start = None
                    log.info("Reset hotkey held 3s — resetting")
                    self.on_reset()
                    return
            time.sleep(0.05)
