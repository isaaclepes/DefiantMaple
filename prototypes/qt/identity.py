"""Stable Linux desktop identity shared by launcher and packaging."""
from pathlib import Path

from PySide6.QtGui import QIcon, QPainter, QPixmap, QColor
from PySide6.QtCore import Qt

APP_ID = "io.github.isaaclepes.DefiantMaple"
ICON_PATH = Path(__file__).with_name("assets") / f"{APP_ID}.png"


def app_icon() -> QIcon:
    if ICON_PATH.is_file():
        icon = QIcon(str(ICON_PATH))
        if not icon.isNull():
            return icon
    # The frozen executable still has a product icon if data assets are relocated.
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#204e56"))
    painter.drawRoundedRect(4, 4, 120, 120, 26, 26)
    painter.setBrush(QColor("#e9994b"))
    from PySide6.QtGui import QPolygon
    from PySide6.QtCore import QPoint
    points = [(64, 13), (75, 38), (93, 29), (88, 48), (110, 54), (92, 70),
              (101, 88), (72, 82), (68, 109), (60, 109), (56, 82), (27, 88),
              (36, 70), (18, 54), (40, 48), (35, 29), (53, 38)]
    painter.drawPolygon(QPolygon([QPoint(x, y) for x, y in points]))
    painter.end()
    return QIcon(pixmap)
