"""Dev-time: render the app icon (gui/resources/app.png + packaging/app.ico) with Qt.

    python tools/make_icon.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter  # noqa: E402

from gui import icons  # noqa: E402


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor("#4f94ee"))
    grad.setColorAt(1, QColor("#1c5cab"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    glyph = int(size * 0.62)
    pm = icons.pixmap("logo", "#ffffff", glyph, 1.0, 1.7)
    p.drawPixmap((size - glyph) // 2, (size - glyph) // 2, pm)
    p.end()
    return image


def main() -> None:
    app = QGuiApplication([])  # noqa: F841
    (ROOT / "gui" / "resources").mkdir(parents=True, exist_ok=True)
    (ROOT / "packaging").mkdir(parents=True, exist_ok=True)
    render(256).save(str(ROOT / "gui" / "resources" / "app.png"))
    ok = render(256).save(str(ROOT / "packaging" / "app.ico"))
    print("icon written; ico ok =", ok)


if __name__ == "__main__":
    main()
