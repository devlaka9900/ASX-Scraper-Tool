"""Rich text for Notes, restricted to bold, italic, underline and text colour.

Qt's own `toHtml()` is verbose and carries fonts, sizes, links and images. Instead the note
body is serialised by walking the QTextDocument and emitting a minimal, escaped subset:

    <p>plain <b>bold</b> <i>italic</i> <u>underline</u> <span style="color:#rrggbb">colour</span></p>

Anything else (fonts, sizes, links, images, scripts, tables) is dropped. Loading goes through the
same canonicalisation, so a hand-edited or hostile notes.json cannot inject anything either.
A colour equal to the current theme's default text colour is treated as "no colour" so that
notes follow the dark/light theme.
"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QTextDocument

from gui import theme

# Readable (>= 3:1) on both the dark (#1a1a19) and light (#fcfcfb) surfaces
PALETTE: tuple[tuple[str, str], ...] = (
    ("Red", "#e5484d"),
    ("Orange", "#d9730d"),
    ("Green", "#2e9e4f"),
    ("Teal", "#0d9488"),
    ("Blue", "#3b82f6"),
    ("Purple", "#8f5cf7"),
    ("Pink", "#db2777"),
)

_DOC_STYLE = "p { margin-top: 0px; margin-bottom: 0px; }"
# pre-wrap keeps runs of spaces, leading indentation and tabs (HTML would collapse them)
_P_OPEN = '<p style="white-space:pre-wrap">'
_OBJECT_CHAR = "￼"          # image / object placeholder inside a fragment


def _default_text_colors() -> set[str]:
    return {theme.DARK["text"].lower(), theme.LIGHT["text"].lower()}


def _fragment_html(fmt: QTextCharFormat, text: str) -> str:
    text = text.replace(_OBJECT_CHAR, "")
    if not text:
        return ""
    out = escape(text, quote=False).replace(" ", "<br>").replace("\n", "<br>")
    if fmt.fontUnderline():
        out = f"<u>{out}</u>"
    if fmt.fontItalic():
        out = f"<i>{out}</i>"
    if int(fmt.fontWeight()) >= 600:
        out = f"<b>{out}</b>"
    brush = fmt.foreground()
    if brush.style() != Qt.BrushStyle.NoBrush:
        color = QColor(brush.color())
        if color.isValid() and color.name().lower() not in _default_text_colors():
            out = f'<span style="color:{color.name().lower()}">{out}</span>'
    return out


def document_to_html(doc: QTextDocument) -> str:
    paragraphs: list[str] = []
    block = doc.begin()
    while block.isValid():
        runs: list[str] = []
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                runs.append(_fragment_html(fragment.charFormat(), fragment.text()))
            it += 1
        paragraphs.append(_P_OPEN + ("".join(runs) or "<br>") + "</p>")
        block = block.next()
    return "".join(paragraphs)


def _strip_empty_breaks(doc: QTextDocument) -> None:
    """`<p><br></p>` loads as a block holding a U+2028 line separator, which would make every
    blank line twice as tall (and add a newline to the plain text) after each reopen."""
    starts: list[int] = []
    block = doc.begin()
    while block.isValid():
        if block.text() == " ":
            starts.append(block.position())
        block = block.next()
    for pos in reversed(starts):
        cursor = QTextCursor(doc)
        cursor.setPosition(pos)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()


def load_html(doc: QTextDocument, html: str) -> None:
    """Fill *doc* from stored HTML (minimal subset, or anything — it is re-canonicalised on save)."""
    doc.setDefaultStyleSheet(_DOC_STYLE)
    doc.setHtml(html or "")
    _strip_empty_breaks(doc)


def sanitize_html(html: str) -> str:
    """Canonical minimal HTML for arbitrary input (used when loading stored notes)."""
    doc = QTextDocument()
    load_html(doc, html)
    return document_to_html(doc)


def plain_text(doc: QTextDocument) -> str:
    return doc.toPlainText().replace(_OBJECT_CHAR, "")
