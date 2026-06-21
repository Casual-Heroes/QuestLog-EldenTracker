import sys
import os
import logging
import traceback
import platform
import datetime

# Logs live in data/logs/ alongside runs and settings
_BASE_DIR  = os.path.join(os.path.dirname(__file__), "..", "data", "logs")
_LOG_FILE  = None   # set by setup()
_LOGGER    = logging.getLogger("questlog")


def setup():
    """Call once at startup — creates log file and installs the global crash hook."""
    global _LOG_FILE

    os.makedirs(_BASE_DIR, exist_ok=True)

    stamp    = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _LOG_FILE = os.path.join(_BASE_DIR, f"session_{stamp}.log")

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    root.addHandler(sh)

    _LOGGER.info("=== QuestLog Mortality Tracker — session started ===")
    _LOGGER.info("Python %s  |  %s", sys.version.split()[0], platform.platform())
    _LOGGER.info("Log file: %s", _LOG_FILE)

    sys.excepthook = _excepthook
    _prune_old_logs()


def get_log_path() -> str:
    return _LOG_FILE or ""


def get_logger(name: str = "questlog") -> logging.Logger:
    return logging.getLogger(name)


def _excepthook(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _LOGGER.critical("UNHANDLED EXCEPTION\n%s", tb_text)

    _show_crash_dialog(tb_text)


def _show_crash_dialog(tb_text: str):
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        import subprocess

        app = QApplication.instance()
        if app is None:
            return

        dlg = QMessageBox()
        dlg.setWindowTitle("QuestLog — Crash Report")
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setText(
            "<b>QuestLog Mortality Tracker encountered an unexpected error and needs to close.</b>"
            "<br><br>"
            "A log file has been saved. Please send it to the developer so this can be fixed."
        )
        dlg.setInformativeText(
            f"<b>Log file:</b><br><code>{_LOG_FILE}</code>"
            "<br><br>"
            "Send to: <b>trocco@casual-heroes.com</b>"
        )
        dlg.setDetailedText(tb_text)

        open_btn = dlg.addButton("Open Log Folder", QMessageBox.ButtonRole.ActionRole)
        dlg.addButton(QMessageBox.StandardButton.Close)

        dlg.exec()

        if dlg.clickedButton() == open_btn and _LOG_FILE:
            folder = os.path.dirname(_LOG_FILE)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    except Exception:
        pass


def _prune_old_logs(keep: int = 30):
    try:
        logs = sorted(
            (f for f in os.listdir(_BASE_DIR) if f.startswith("session_") and f.endswith(".log")),
            reverse=True,
        )
        for old in logs[keep:]:
            try:
                os.remove(os.path.join(_BASE_DIR, old))
            except Exception:
                pass
    except Exception:
        pass
