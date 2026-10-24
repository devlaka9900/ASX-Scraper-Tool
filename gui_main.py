"""ASX Reg Data — desktop GUI entry point.

    python gui_main.py            # normal start
    python gui_main.py --selftest # headless smoke test (used as the build gate)
"""
import os
import sys

# A windowed (no-console) PyInstaller exe has sys.stdout/stderr == None, which
# breaks tqdm/print/warnings. Must run before anything else is imported.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

os.environ["ASX_CHECKER_GUI"] = "1"

import faulthandler  # noqa: E402
import multiprocessing  # noqa: E402
import traceback  # noqa: E402

from core.paths import log_dir  # noqa: E402

os.environ.setdefault("ASX_CHECKER_LOG_DIR", str(log_dir()))

_crash_file = None


def _install_crash_handlers() -> None:
    """Write unhandled exceptions (Python and native) to crash.log; there is no console."""
    global _crash_file
    try:
        _crash_file = open(log_dir() / "crash.log", "a", encoding="utf-8")
        faulthandler.enable(_crash_file)
    except OSError:
        return

    def _write(kind: str, text: str) -> None:
        try:
            _crash_file.write(f"\n--- {kind} ---\n{text}\n")
            _crash_file.flush()
        except Exception:
            pass

    def _excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        _write("unhandled exception", text)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(None, "ASX Reg Data",
                                     f"Unexpected error:\n\n{exc}\n\nDetails were saved to:\n{log_dir() / 'crash.log'}")
        except Exception:
            pass

    sys.excepthook = _excepthook
    import threading
    threading.excepthook = lambda args: _write(
        "thread exception", "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


def main() -> int:
    multiprocessing.freeze_support()

    if "--selftest" in sys.argv:
        from gui import selftest
        return selftest.run()

    _install_crash_handlers()

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QGuiApplication
    from PySide6.QtWidgets import QApplication

    from core.version import APP_NAME
    from gui import anim, theme
    from gui.main_window import MainWindow
    from gui.settings import Settings

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("CUBE")
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    font.setPointSizeF(10)
    app.setFont(font)

    settings = Settings()
    anim.set_reduced_motion(settings.reduced_motion)
    theme.apply(app, settings.theme)
    theme.follow_system(app)

    window = MainWindow(settings)
    window.show()
    code = app.exec()
    if window.runner.busy:
        # The user confirmed closing while a job was stuck in an uninterruptible network
        # call: destroying a running QThread aborts the process, so skip interpreter teardown.
        sys.stdout.flush()
        os._exit(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
