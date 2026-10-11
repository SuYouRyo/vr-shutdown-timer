"""主题：深色 / 浅色 QSS，针对 VR 环境放大字号与点击区域。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

from .config import assets_dir

DARK = {
    "bg": "#0b1220",
    "card": "#151d2e",
    "card_alt": "#1b2740",
    "border": "#27354f",
    "text": "#eaf0fb",
    "muted": "#94a6c4",
    "timer": "#7dd3fc",
    "timer_active": "#4ade80",
    "accent": "#38bdf8",
    "accent_soft": "#12314a",
    "accent_text": "#bae6fd",
    "primary": "#16a34a",
    "primary_hover": "#1fbf5c",
    "primary_press": "#128a41",
    "primary_disabled": "#1d3b2b",
    "danger": "#ef4444",
    "danger_hover": "#f87171",
    "danger_press": "#b91c1c",
    "danger_soft": "#3b1416",
    "neutral": "#1e293b",
    "neutral_hover": "#26364d",
    "neutral_press": "#18222f",
    "input_bg": "#0f1729",
    "disabled": "#66768f",
    "menu_bg": "#151d2e",
    "menu_sel": "#1f3b5c",
}

LIGHT = {
    "bg": "#eef2f8",
    "card": "#ffffff",
    "card_alt": "#f6f8fc",
    "border": "#cdd7e6",
    "text": "#0f172a",
    "muted": "#5c6b83",
    "timer": "#0369a1",
    "timer_active": "#15803d",
    "accent": "#0284c7",
    "accent_soft": "#e0f2fe",
    "accent_text": "#075985",
    "primary": "#16a34a",
    "primary_hover": "#1fbf5c",
    "primary_press": "#128a41",
    "primary_disabled": "#bfe3cc",
    "danger": "#dc2626",
    "danger_hover": "#ef4444",
    "danger_press": "#b91c1c",
    "danger_soft": "#fee2e2",
    "neutral": "#ffffff",
    "neutral_hover": "#e8eef8",
    "neutral_press": "#dbe4f0",
    "input_bg": "#ffffff",
    "disabled": "#9aa7ba",
    "menu_bg": "#ffffff",
    "menu_sel": "#dbeafe",
}

_CHECK_NAME = "check_{theme}.png"
_check_cache: dict[str, str] = {}


def _checkmark_file(theme: str) -> str:
    """生成带白色对勾的透明 PNG，供 QCheckBox::indicator:checked 使用。

    目录不可写时返回空串：此时复选框退化为纯色方块，功能不受影响。
    """
    if theme in _check_cache:
        return _check_cache[theme]

    directory = assets_dir()
    if directory is None:
        _check_cache[theme] = ""
        return ""

    size = 48
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath(QPointF(size * 0.22, size * 0.52))
    path.lineTo(size * 0.42, size * 0.72)
    path.lineTo(size * 0.79, size * 0.29)
    pen = QPen(QColor("#ffffff"), size * 0.14)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)
    painter.end()

    target = directory / _CHECK_NAME.format(theme=theme)
    try:
        pix.save(str(target), "PNG")
    except Exception:
        _check_cache[theme] = ""
        return ""
    text = str(target).replace("\\", "/")
    _check_cache[theme] = text
    return text


_QSS = """
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
}
QWidget {
    color: @text;
    font-size: 16px;
}
QWidget#Root, QDialog {
    background-color: @bg;
}
QFrame#Card {
    background-color: @card;
    border: 1px solid @border;
    border-radius: 14px;
}
QLabel#TitleLabel {
    font-size: 21px;
    font-weight: 700;
    color: @text;
}
QLabel#TimerLabel {
    font-family: "Consolas", "Cascadia Mono", "Courier New", monospace;
    font-size: 66px;
    font-weight: 700;
    color: @timer;
}
QLabel#TimerLabel[state="active"] {
    color: @timer_active;
}
QLabel#SubLabel {
    font-size: 16px;
    color: @muted;
}
QLabel#FieldLabel {
    font-size: 16px;
    color: @muted;
}
QLabel#PreviewLabel {
    font-size: 17px;
    font-weight: 600;
    color: @accent_text;
}
QLabel#StatusLabel {
    font-size: 15px;
    color: @muted;
}
QLabel#DialogTitle {
    font-size: 24px;
    font-weight: 700;
    color: @text;
}
QLabel#SectionLabel {
    font-size: 14px;
    font-weight: 700;
    color: @muted;
    letter-spacing: 1px;
}
QLabel#HintLabel {
    font-size: 14px;
    color: @muted;
}
QLabel#StepValue {
    font-family: "Consolas", "Cascadia Mono", "Courier New", monospace;
    font-size: 30px;
    font-weight: 700;
    color: @text;
    background-color: @input_bg;
    border: 1px solid @border;
    border-radius: 10px;
    padding: 6px 2px;
}

/* ------------------------------------------------------------- 普通按钮 -- */
QPushButton {
    background-color: @neutral;
    border: 1px solid @border;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 16px;
    font-weight: 600;
    color: @text;
}
QPushButton:hover {
    background-color: @neutral_hover;
}
QPushButton:pressed {
    background-color: @neutral_press;
}
QPushButton:disabled {
    color: @disabled;
    background-color: @card;
    border-color: @border;
}

QPushButton#PrimaryButton {
    background-color: @primary;
    border: none;
    border-radius: 14px;
    color: #ffffff;
    font-size: 26px;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background-color: @primary_hover;
}
QPushButton#PrimaryButton:pressed {
    background-color: @primary_press;
}
QPushButton#PrimaryButton:disabled {
    background-color: @primary_disabled;
    color: @disabled;
}

QPushButton#DangerButton {
    background-color: transparent;
    border: 2px solid @danger;
    border-radius: 14px;
    color: @danger;
    font-size: 22px;
    font-weight: 700;
}
QPushButton#DangerButton:hover {
    background-color: @danger;
    color: #ffffff;
}
QPushButton#DangerButton:pressed {
    background-color: @danger_press;
    border-color: @danger_press;
    color: #ffffff;
}
QPushButton#DangerButton:disabled {
    border-color: @border;
    color: @disabled;
    background-color: transparent;
}

QPushButton#DangerSolidButton {
    background-color: @danger;
    border: none;
    border-radius: 14px;
    color: #ffffff;
    font-size: 24px;
    font-weight: 700;
}
QPushButton#DangerSolidButton:hover {
    background-color: @danger_hover;
}
QPushButton#DangerSolidButton:pressed {
    background-color: @danger_press;
}

QPushButton#NeutralButton {
    background-color: @neutral;
    border: 2px solid @border;
    border-radius: 14px;
    color: @text;
    font-size: 22px;
    font-weight: 700;
}
QPushButton#NeutralButton:hover {
    background-color: @neutral_hover;
}

QPushButton#ModeButton {
    background-color: @input_bg;
    border: 2px solid @border;
    border-radius: 12px;
    color: @muted;
    font-size: 19px;
    font-weight: 700;
    padding: 6px 10px;
}
QPushButton#ModeButton:hover {
    border-color: @accent;
}
QPushButton#ModeButton:checked {
    background-color: @accent_soft;
    border: 2px solid @accent;
    color: @accent_text;
}
QPushButton#ModeButton:disabled {
    color: @disabled;
    border-color: @border;
    background-color: @card;
}

QPushButton#PresetButton {
    background-color: @input_bg;
    border: 1px solid @border;
    border-radius: 10px;
    color: @text;
    font-size: 15px;
    font-weight: 600;
    padding: 6px 2px;
}
QPushButton#PresetButton:hover {
    border-color: @accent;
    color: @accent_text;
}
QPushButton#PresetButton:pressed {
    background-color: @accent_soft;
}
QPushButton#PresetButton:disabled {
    color: @disabled;
    border-color: @border;
}

QPushButton#GhostButton {
    background-color: transparent;
    border: 1px solid @border;
    border-radius: 10px;
    color: @muted;
    font-size: 15px;
    font-weight: 600;
    padding: 6px 14px;
}
QPushButton#GhostButton:hover {
    border-color: @accent;
    color: @accent_text;
}

QPushButton#StepButton {
    background-color: @neutral;
    border: 1px solid @border;
    border-radius: 10px;
    color: @text;
    font-size: 26px;
    font-weight: 700;
    padding: 0px;
}
QPushButton#StepButton:hover {
    background-color: @neutral_hover;
    border-color: @accent;
    color: @accent_text;
}
QPushButton#StepButton:pressed {
    background-color: @accent_soft;
}
QPushButton#StepButton:disabled {
    color: @disabled;
    border-color: @border;
    background-color: @card;
}

/* ------------------------------------------------------------ 提醒弹窗 -- */
QDialog#ReminderRoot {
    background: transparent;
}
QFrame#ReminderPanel {
    background-color: @card;
    border: 3px solid @danger;
    border-radius: 16px;
}
QLabel#ReminderTitle {
    font-size: 30px;
    font-weight: 700;
    color: @danger;
}
QLabel#ReminderCaption {
    font-size: 17px;
    color: @muted;
}
QLabel#ReminderCount {
    font-family: "Consolas", "Cascadia Mono", "Courier New", monospace;
    font-size: 72px;
    font-weight: 700;
    color: @danger;
}

/* --------------------------------------------------------------- 复选框 -- */
QCheckBox {
    font-size: 17px;
    color: @text;
    spacing: 14px;
    padding: 4px 0px;
}
QCheckBox:disabled {
    color: @disabled;
}
QCheckBox::indicator {
    width: 26px;
    height: 26px;
    border: 2px solid @border;
    border-radius: 7px;
    background-color: @input_bg;
}
QCheckBox::indicator:hover {
    border-color: @accent;
}
QCheckBox::indicator:checked {
    background-color: @primary;
    border: 2px solid @primary;
    image: url("@check_img");
}
QCheckBox::indicator:disabled {
    border-color: @border;
    background-color: @card;
}

/* ---------------------------------------------------------------- 滚动条 -- */
QScrollArea#SettingsScroll {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background-color: @border;
    border-radius: 5px;
    min-height: 48px;
}
QScrollBar::handle:vertical:hover {
    background-color: @accent;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: transparent;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    height: 0px;
}

/* ------------------------------------------------------------------ 菜单 -- */QMenu {
    background-color: @menu_bg;
    border: 1px solid @border;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 10px 22px 10px 16px;
    border-radius: 8px;
    font-size: 15px;
    color: @text;
}
QMenu::item:selected {
    background-color: @menu_sel;
}
QMenu::item:disabled {
    color: @disabled;
}
QMenu::separator {
    height: 1px;
    background-color: @border;
    margin: 6px 8px;
}

QToolTip {
    background-color: @menu_bg;
    color: @text;
    border: 1px solid @border;
    padding: 6px 10px;
    font-size: 14px;
}
"""


def palette(theme: str) -> dict[str, str]:
    return LIGHT if theme == "light" else DARK


def build_qss(theme: str) -> str:
    colors = dict(palette(theme))
    colors["check_img"] = _checkmark_file(theme)
    qss = _QSS
    # 先替换较长的键，避免 @primary 抢先匹配 @primary_hover
    for key in sorted(colors, key=len, reverse=True):
        qss = qss.replace("@" + key, colors[key])
    return qss
