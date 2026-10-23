"""QStackedWidget that fades the incoming page in.

A cheap overlay painted in the page-background colour fades from opaque to clear
after the page switch (no QGraphicsOpacityEffect, which would rasterise the whole
page subtree and make tables/charts janky).
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QVariantAnimation, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QStackedWidget, QWidget

from gui import anim, theme


class _Overlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.alpha = 0.0
        self.hide()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        color = theme.current().color("bg")
        color.setAlphaF(self.alpha)
        p.fillRect(self.rect(), color)


class FadeStack(QStackedWidget):
    DURATION_MS = 150

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._overlay = _Overlay(self)
        self._anim: QVariantAnimation | None = None

    def fade_to(self, widget: QWidget) -> None:
        if widget is self.currentWidget():
            return
        self.setCurrentWidget(widget)
        if anim.reduced_motion() or not self.isVisible():
            return
        if self._anim is not None:
            try:
                self._anim.stop()          # may already be deleted by DeleteWhenStopped
            except RuntimeError:
                pass
            self._anim = None
        self._overlay.setGeometry(self.rect())
        self._overlay.alpha = 0.85
        self._overlay.show()
        self._overlay.raise_()
        a = QVariantAnimation(self)
        a.setStartValue(0.85)
        a.setEndValue(0.0)
        a.setDuration(self.DURATION_MS)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.valueChanged.connect(self._tick)
        a.finished.connect(lambda anim=a: self._on_done(anim))
        self._anim = a
        a.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _on_done(self, finished_anim) -> None:
        if self._anim is finished_anim:     # a newer fade may already have replaced it
            self._anim = None
            self._overlay.hide()

    def _tick(self, v) -> None:
        self._overlay.alpha = float(v)
        self._overlay.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())
