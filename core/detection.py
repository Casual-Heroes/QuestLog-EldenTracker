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


class Detector:
    def __init__(self, death_tracker, on_death=None, on_subtract=None, on_reset=None, hotkeys=None):
        self.death_tracker     = death_tracker
        self.on_death          = on_death    or (lambda: None)
        self.on_subtract       = on_subtract or (lambda: None)
        self.on_reset          = on_reset    or (lambda: None)
        self._hotkeys          = {**DEFAULT_HOTKEYS, **(hotkeys or {})}
        self._running          = False
        self._reset_hold_start = None

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
        try:
            keyboard.on_press_key(self._hotkeys["death"],    lambda _: self._on_death(),    suppress=False)
            keyboard.on_press_key(self._hotkeys["subtract"], lambda _: self._on_subtract(), suppress=False)
            keyboard.on_press_key(self._hotkeys["reset"],    self._reset_key_down,           suppress=False)
            keyboard.on_release_key(self._hotkeys["reset"],  self._reset_key_up)
        except Exception:
            log.exception("Failed to register hotkeys")

    def _unhook(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def _on_death(self):
        log.info("Death hotkey (%s)", self._hotkeys["death"].upper())
        self.on_death()

    def _on_subtract(self):
        log.info("Subtract hotkey (%s)", self._hotkeys["subtract"].upper())
        self.on_subtract()

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
                log.info("Reset hotkey held 3s — resetting")
                self.on_reset()
                return
            time.sleep(0.05)
