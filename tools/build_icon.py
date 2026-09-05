"""Render the app icon from qml/brand/zharn.svg into the PNG sizes and the Windows .ico.

Run: QT_QPA_PLATFORM=offscreen python tools/build_icon.py
Rendering goes through Qt's own SVG renderer, so what this writes is exactly what the running
app will show — if a construct is outside SVG Tiny 1.2, it is missing here too, visibly.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "qml" / "brand"
MASTER = BRAND / "zharn.svg"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(px: int, dest: Path) -> bytes:
    """The master rendered at `px`, written to `dest`, returned as PNG bytes for the .ico."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    img = QImage(px, px, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    QSvgRenderer(str(MASTER)).render(painter)
    painter.end()

    if not img.save(str(dest), "PNG"):
        raise RuntimeError(f"Qt could not write {dest}")
    return dest.read_bytes()


def pack_ico(pngs: dict[int, bytes]) -> bytes:
    """An .ico is a directory of embedded PNGs — no dependency needed to write one."""
    entries, blobs = [], []
    offset = 6 + 16 * len(pngs)
    for px, data in sorted(pngs.items()):
        entries.append(struct.pack("<BBBBHHII", px % 256, px % 256, 0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)
    return struct.pack("<HHH", 0, 1, len(pngs)) + b"".join(entries) + b"".join(blobs)


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # must stay referenced
    pngs = {px: render(px, BRAND / f"zharn-{px}.png") for px in SIZES}
    (BRAND / "zharn.ico").write_bytes(pack_ico(pngs))
    print(f"wrote {len(pngs)} PNGs + zharn.ico to {BRAND.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
