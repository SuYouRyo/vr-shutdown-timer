"""设置窗口：所有高级选项集中在此。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .widgets import Stepper

DIALOG_WIDTH = 580
CHECK_HEIGHT = 40
SEGMENT_HEIGHT = 46
BUTTON_HEIGHT = 54


def _check_box(text: str, checked: bool) -> QCheckBox:
    box = QCheckBox(text)
    box.setChecked(checked)
    box.setMinimumHeight(CHECK_HEIGHT)
    box.setCursor(Qt.PointingHandCursor)
    box.setFocusPolicy(Qt.NoFocus)
    return box


class _Segmented(QWidget):
    """两个互斥的大按钮，用于主题 / 关机方式选择。"""

    def __init__(self, options: list[tuple[str, str]], current: str, parent=None) -> None:
        super().__init__(parent)
        self._values = [value for value, _ in options]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for value, label in options:
            button = QPushButton(label)
            button.setObjectName("ModeButton")
            button.setCheckable(True)
            button.setMinimumHeight(SEGMENT_HEIGHT)
            button.setFocusPolicy(Qt.NoFocus)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(value == current)
            self._group.addButton(button)
            self._buttons[value] = button
            layout.addWidget(button, 1)

    def value(self) -> str:
        for value, button in self._buttons.items():
            if button.isChecked():
                return value
        return self._values[0]

    def set_value(self, value: str) -> None:
        button = self._buttons.get(value)
        if button is not None:
            button.setChecked(True)


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.cfg = config

        self.setWindowTitle("设置")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(config.always_on_top))
        self.setModal(True)
        self.setMinimumWidth(DIALOG_WIDTH)
        self.setSizeGripEnabled(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        title = QLabel("设置")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)
        body_layout.addWidget(self._build_startup_section())
        body_layout.addWidget(self._build_reminder_section())
        body_layout.addWidget(self._build_shutdown_section())
        body_layout.addWidget(self._build_misc_section())

        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        root.addLayout(self._build_buttons())

        self._sync_enabled_states()
        self._fit_to_screen(body, scroll)

    def _fit_to_screen(self, body: QWidget, scroll: QScrollArea) -> None:
        """按屏幕可用高度自适应；内容过高时由滚动区域承载，绝不裁切。"""
        screen = self.screen() or QGuiApplication.primaryScreen()
        available = screen.availableGeometry().height() if screen is not None else 900
        max_total = max(560, available - 80)

        margins = self.layout().contentsMargins()
        chrome = (
            margins.top()
            + margins.bottom()
            + 34  # 标题
            + 14  # 标题与滚动区间距
            + 14  # 滚动区与按钮行间距
            + BUTTON_HEIGHT
        )
        content_height = body.sizeHint().height()
        scroll.setMinimumHeight(int(min(content_height, max(220, max_total - chrome))))
        self.adjustSize()
        self.setFixedSize(DIALOG_WIDTH, int(min(self.sizeHint().height(), max_total)))

    # ------------------------------------------------------------------ 分区
    def _section(self, label: str, widgets: list[QWidget]) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(8)

        header = QLabel(label)
        header.setObjectName("SectionLabel")
        layout.addWidget(header)
        for widget in widgets:
            layout.addWidget(widget)
        return card

    def _build_startup_section(self) -> QFrame:
        self.chk_autostart = _check_box("开机自动启动", self.cfg.autostart)
        self.chk_ontop = _check_box("窗口置顶（VR 桌面推荐）", self.cfg.always_on_top)
        return self._section("启动与窗口", [self.chk_autostart, self.chk_ontop])

    def _build_reminder_section(self) -> QFrame:
        self.chk_reminder = _check_box("关机前弹出提醒", self.cfg.reminder_enabled)
        self.spin_reminder = Stepper(5, 600, self.cfg.reminder_seconds, "秒", step=5)
        reminder_row = QWidget()
        row_layout = QHBoxLayout(reminder_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)
        row_layout.addWidget(self.chk_reminder, 1)
        row_layout.addWidget(self.spin_reminder)

        self.chk_sound = _check_box("提醒时播放声音", self.cfg.sound_enabled)

        self.chk_reminder.toggled.connect(self._sync_enabled_states)
        self.chk_sound.toggled.connect(self._sync_enabled_states)
        return self._section("关机提醒", [reminder_row, self.chk_sound])

    def _build_shutdown_section(self) -> QFrame:
        self.seg_shutdown = _Segmented(
            [("normal", "正常关机"), ("force", "强制关机")],
            "force" if self.cfg.force_shutdown else "normal",
        )
        hint = QLabel("强制关机会直接结束未保存的程序，请谨慎使用。")
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)

        self.spin_grace = Stepper(
            1, 60, max(1, int(self.cfg.grace_seconds)), "秒", step=1
        )
        grace_row = QWidget()
        grace_layout = QHBoxLayout(grace_row)
        grace_layout.setContentsMargins(0, 0, 0, 0)
        grace_layout.setSpacing(12)
        grace_label = QLabel("发出指令后的宽限时间")
        grace_label.setObjectName("FieldLabel")
        grace_layout.addWidget(grace_label, 1)
        grace_layout.addWidget(self.spin_grace)

        grace_hint = QLabel("给程序自身退出的时间，也给用户最后一次取消的机会。")
        grace_hint.setObjectName("HintLabel")
        grace_hint.setWordWrap(True)

        return self._section(
            "关机方式", [self.seg_shutdown, hint, grace_row, grace_hint]
        )

    def _build_misc_section(self) -> QFrame:
        self.chk_autodelete = _check_box(
            "任务执行后自动删除任务（下次打开不残留）", self.cfg.auto_delete_task
        )
        self.seg_theme = _Segmented(
            [("dark", "深色"), ("light", "浅色")],
            self.cfg.theme,
        )
        theme_row = QWidget()
        row_layout = QHBoxLayout(theme_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)
        theme_label = QLabel("主题")
        theme_label.setObjectName("FieldLabel")
        theme_label.setMinimumWidth(48)
        row_layout.addWidget(theme_label)
        row_layout.addWidget(self.seg_theme, 1)
        return self._section("其他", [self.chk_autodelete, theme_row])

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("GhostButton")
        self.btn_cancel.setMinimumHeight(BUTTON_HEIGHT)
        self.btn_cancel.setFocusPolicy(Qt.NoFocus)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("保存")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setMinimumHeight(BUTTON_HEIGHT)
        self.btn_save.setFocusPolicy(Qt.NoFocus)
        self.btn_save.clicked.connect(self._on_save)

        row.addWidget(self.btn_cancel, 1)
        row.addWidget(self.btn_save, 2)
        return row

    # ------------------------------------------------------------------ 逻辑
    def _sync_enabled_states(self) -> None:
        self.spin_reminder.setEnabled(self.chk_reminder.isChecked())
        self.chk_sound.setEnabled(self.chk_reminder.isChecked())

    def values(self) -> dict:
        return {
            "autostart": self.chk_autostart.isChecked(),
            "always_on_top": self.chk_ontop.isChecked(),
            "reminder_enabled": self.chk_reminder.isChecked(),
            "reminder_seconds": self.spin_reminder.value(),
            "sound_enabled": self.chk_sound.isChecked(),
            "force_shutdown": self.seg_shutdown.value() == "force",
            "grace_seconds": self.spin_grace.value(),
            "auto_delete_task": self.chk_autodelete.isChecked(),
            "theme": self.seg_theme.value(),
        }

    def _on_save(self) -> None:
        self.accept()
