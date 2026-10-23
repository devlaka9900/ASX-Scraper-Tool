"""Small animation helpers + reduced-motion detection."""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QEasingCurve, QObject, QVariantAnimation

_override: bool | None = None   # set from settings


def set_reduced_motion(value: bool | None) -> None:
    global _override
    _override = value


def reduced_motion() -> bool:
    """True when the user (settings) or Windows asks for no animations."""
    if _override is not None:
        return _override
    if sys.platform == "win32":
        try:
            SPI_GETCLIENTAREAANIMATION = 0x1042
            flag = ctypes.c_int(1)
            ok = ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(flag), 0)
            if ok:
                return not flag.value
        except Exception:
            pass
    return False


def duration(ms: int) -> int:
    return 0 if reduced_motion() else ms


def tween(parent: QObject, start: float, end: float, ms: int, on_value,
          easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
          on_done=None) -> QVariantAnimation:
    """Run a value animation, calling *on_value(v)* each frame. With reduced
    motion the end value is applied immediately."""
    anim = QVariantAnimation(parent)
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.setEasingCurve(easing)
    anim.setDuration(duration(ms))
    anim.valueChanged.connect(lambda v: on_value(float(v)))
    if on_done is not None:
        anim.finished.connect(on_done)
    if anim.duration() == 0:
        on_value(float(end))
        if on_done is not None:
            on_done()
        return anim
    anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim
