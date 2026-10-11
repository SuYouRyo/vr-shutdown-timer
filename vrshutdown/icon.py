"""程序图标：优先使用打包的 app.ico，否则用 QPainter 现画电源符号。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap

BG_COLOR = "#0ea5e9"
FG_COLOR = "#ffffff"


def resource_path(*parts: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base).joinpath(*parts)
    return Path(__file__).resolve().parent.parent.joinpath(*parts)


def power_image(
    size: int,
    bg: str = BG_COLOR,
    fg: str = FG_COLOR,
    rounded: bool = True,
) -> QImage:
    """绘制电源符号（QImage 版本，无需 QGuiApplication 即可离屏生成）。"""
    size = max(8, int(size))
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(bg))

    rect = QRectF(0.5, 0.5, size - 1.0, size - 1.0)
    if rounded:
        radius = size * 0.24
        painter.drawRoundedRect(rect, radius, radius)
    else:
        painter.drawEllipse(rect)

    cx = size / 2.0
    cy = size / 2.0
    arc_r = size * 0.255
    pen = QPen(QColor(fg), max(1.6, size * 0.105))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    # Qt 角度：0° 在 3 点钟方向、逆时针为正。128° 起、284° 跨度 => 顶部留 76° 缺口。
    painter.drawArc(
        QRectF(cx - arc_r, cy - arc_r + size * 0.035, arc_r * 2, arc_r * 2),
        128 * 16,
        284 * 16,
    )
    painter.drawLine(
        QPointF(cx, cy - arc_r - size * 0.055),
        QPointF(cx, cy + size * 0.02),
    )
    painter.end()
    return image


def power_pixmap(
    size: int,
    bg: str = BG_COLOR,
    fg: str = FG_COLOR,
    rounded: bool = True,
) -> QPixmap:
    """绘制电源符号图标。"""
    return QPixmap.fromImage(power_image(size, bg, fg, rounded))


def app_icon() -> QIcon:
    ico = resource_path("assets", "app.ico")
    if ico.exists():
        icon = QIcon(str(ico))
        if not icon.isNull():
            return icon
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(power_pixmap(size))
    return icon
