import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# The GUI sets ASX_CHECKER_GUI=1 (no console, so no Rich handler) and points
# ASX_CHECKER_LOG_DIR at a writable folder. The CLI keeps the relative "logs".
_GUI_MODE = os.environ.get("ASX_CHECKER_GUI") == "1"
_LOG_DIR = Path(os.environ.get("ASX_CHECKER_LOG_DIR", "logs"))

_FILE_HANDLER: logging.Handler
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _FILE_HANDLER = RotatingFileHandler(
        _LOG_DIR / "asx_checker.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    _FILE_HANDLER.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
except OSError:
    # Unwritable working directory (e.g. frozen exe started from System32)
    _FILE_HANDLER = logging.NullHandler()
_FILE_HANDLER.setLevel(logging.DEBUG)

_CONSOLE_HANDLER: logging.Handler | None = None
if not _GUI_MODE and sys.stderr is not None:
    from rich.logging import RichHandler

    _CONSOLE_HANDLER = RichHandler(rich_tracebacks=True, show_path=False)
    _CONSOLE_HANDLER.setLevel(logging.INFO)

# Loggers use propagate=False with their own handlers, so extra handlers
# (e.g. the GUI's live log) have to be attached to each logger explicitly.
_LOGGERS: dict[str, logging.Logger] = {}
_EXTRA: list[logging.Handler] = []


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        if _CONSOLE_HANDLER is not None:
            logger.addHandler(_CONSOLE_HANDLER)
        logger.addHandler(_FILE_HANDLER)
        for handler in _EXTRA:
            logger.addHandler(handler)
        logger.propagate = False
    _LOGGERS[name] = logger
    return logger


def add_handler(handler: logging.Handler) -> None:
    """Attach *handler* to every current and future project logger."""
    if handler in _EXTRA:
        return
    _EXTRA.append(handler)
    for logger in _LOGGERS.values():
        logger.addHandler(handler)


def remove_handler(handler: logging.Handler) -> None:
    if handler in _EXTRA:
        _EXTRA.remove(handler)
    for logger in _LOGGERS.values():
        logger.removeHandler(handler)
