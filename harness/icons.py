"""Icons: monochrome SVGs in qml/icons/, recolored and rasterized on request.

QML asks for `image://icon/<name>/<rrggbb>` (see qml/ui/Icon.qml); the SVGs use `currentColor`,
which is substituted before rendering, so one file serves every state (muted, hover, accent).
Adding an icon = dropping a 16×16 SVG into qml/icons/. Reloadable: edit an SVG and the next
generation picks it up (the cache is per provider instance, one per generation).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "qml" / "icons"
PLACEHOLDER = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">'
               '<rect x="2.5" y="2.5" width="11" height="11" rx="2"/><path d="M5 5l6 6M11 5l-6 6"/></svg>')


def icon_names() -> list[str]:
    return sorted(p.stem for p in ICON_DIR.glob("*.svg"))


class IconProvider(QQuickImageProvider):
    def __init__(self, icon_dir: Path = ICON_DIR):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.icon_dir = Path(icon_dir)
        self._cache: dict[tuple[str, str, int], QImage] = {}

    def requestImage(self, id_: str, size: QSize, requested: QSize) -> QImage:
        name, _, color = id_.partition("/")
        color = color or "ffffff"
        px = requested.width() if requested.isValid() and requested.width() > 0 else 16
        key = (name, color, px)
        img = self._cache.get(key)
        if img is None:
            img = self._render(name, color, px)
            self._cache[key] = img
        return img

    def _render(self, name: str, color: str, px: int) -> QImage:
        path = self.icon_dir / f"{name}.svg"
        svg = path.read_text(encoding="utf-8") if path.exists() else PLACEHOLDER
        svg = svg.replace("currentColor", "#" + color)
        img = QImage(px, px, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        return img
