"""Author signature drawn as a very faint watermark on a few app pages (see
gui/widgets/watermark.py). It is never shown as regular UI text."""

_SIGNATURE = "binura.lakshan@cube.global"


def signature() -> str:
    return _SIGNATURE
