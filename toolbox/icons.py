"""Lucide-SVGs als eingefärbte Bilder: image://icons/<name>/<RRGGBB>"""
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


class IconProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._svg: dict[str, str] = {}

    def requestImage(self, id, size, requestedSize):
        name, _, color = id.partition("/")
        color = "#" + (color or "ffffff")
        side = max(requestedSize.width(), requestedSize.height(), 24)
        src = self._svg.get(name)
        if src is None:
            p = ICON_DIR / f"{name}.svg"
            src = p.read_text() if p.exists() else (ICON_DIR / "circle-help.svg").read_text()
            self._svg[name] = src
        data = src.replace("currentColor", color).encode()
        r = QSvgRenderer(QByteArray(data))
        img = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p)
        p.end()
        size.setWidth(side)
        size.setHeight(side)
        return img
