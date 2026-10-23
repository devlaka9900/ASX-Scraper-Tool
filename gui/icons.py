"""Inline-SVG icon set (24x24 grid, stroke style) rendered through QtSvg.

No external assets: every icon is a few SVG elements; colour is substituted at
render time so icons follow the theme. Pixmaps are cached per (name, colour, size).
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_BODY = {
    "play":       '<path d="M7 4.5v15l12-7.5z"/>',
    "plus":       '<path d="M12 5v14M5 12h14"/>',
    "chart":      '<path d="M4 20V11M10 20V4M16 20v-7M22 20H2"/>',
    "history":    '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/>',
    "calendar":   '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4M9 15l2 2 4-4"/>',
    "sun":        '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon":       '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "folder":     '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "file":       '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "sheet":      '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 9h16M4 15h16M10 3v18"/>',
    "check":      '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "pause":      '<path d="M9 5v14M15 5v14"/>',
    "question":   '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.2a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.2 1-1.2 1.8"/><path d="M12 17h.01"/>',
    "x":          '<path d="M6 6l12 12M18 6L6 18"/>',
    "search":     '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "external":   '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "copy":       '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    "stop":       '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "trash":      '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "chevron":    '<path d="M6 9l6 6 6-6"/>',
    "chevron_r":  '<path d="M9 6l6 6-6 6"/>',
    "download":   '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
    "refresh":    '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "alert":      '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    "file_x":     '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M10 13l4 4M14 13l-4 4"/>',
    "layers":     '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "logo":       '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5"/><path d="M9.5 15.5l2 2 3.5-4"/>',
}

_cache: dict[tuple, QPixmap] = {}


def _svg(name: str, color: str, stroke: float) -> bytes:
    body = _BODY[name]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    ).encode()


def pixmap(name: str, color: str, size: int = 18, dpr: float = 1.0, stroke: float = 1.9) -> QPixmap:
    key = (name, color, size, round(dpr, 2), stroke)
    pm = _cache.get(key)
    if pm is not None:
        return pm
    px = max(1, int(round(size * dpr)))
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(_svg(name, color, stroke))).render(painter, QRectF(0, 0, px, px))
    painter.end()
    pm = QPixmap.fromImage(image)
    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    return pm


def icon(name: str, color: str, size: int = 18, on_color: str | None = None) -> QIcon:
    """QIcon with an optional different colour for the checked (On) state."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size, 2.0), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, on_color or color, size, 2.0), QIcon.Mode.Normal, QIcon.State.On)
    return ic


def clear_cache() -> None:
    _cache.clear()
