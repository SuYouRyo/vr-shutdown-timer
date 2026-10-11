"""主界面：极简、大字号、大按钮，适合 VR 桌面环境操作。"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .config import APP_DISPLAY_NAME
from .icon import app_icon, power_pixmap
from . import platform_win
from .util import format_hms, format_moment, humanize, next_occurrence
from .widgets import Stepper

WINDOW_WIDTH = 620
MIN_WINDOW_HEIGHT = 700
PRESETS = ((15, "15 分钟"), (30, "30 分钟"), (60, "1 小时"), (120, "2 小时"))


class MainWindow(QWidget):
    def __init__(self, controller) -> None:
        super().__init__(None)
        self.ctrl = controller
        self.cfg = controller.config

        self._mode = self.cfg.last_mode
        self._timer_state = ""
        self._status_kind = "info"
        self._suppress_preview = False

        self.setObjectName("Root")
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._build_ui()
        self._apply_config_to_inputs()
        self._connect_signals()
        self.apply_window_flags()
        self.refresh()

    # -------------------------------------------------------------- 界面搭建
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 24)
        root.setSpacing(16)

        root.addLayout(self._build_header())
        root.addWidget(self._build_timer_card())
        root.addWidget(self._build_control_card())
        root.addWidget(self._build_actions())
        root.addWidget(self._build_status())

        self.layout().activate()
        height = max(MIN_WINDOW_HEIGHT, self.sizeHint().height())
        self.setFixedSize(WINDOW_WIDTH, height)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(power_pixmap(30))
        logo.setFixedSize(30, 30)

        title = QLabel(APP_DISPLAY_NAME)
        title.setObjectName("TitleLabel")

        self.btn_settings = QPushButton("设置")
        self.btn_settings.setObjectName("GhostButton")
        self.btn_settings.setFixedSize(88, 40)
        self.btn_settings.setFocusPolicy(Qt.NoFocus)
        self.btn_settings.setCursor(Qt.PointingHandCursor)

        row.addWidget(logo)
        row.addWidget(title)
        row.addStretch(1)
        row.addWidget(self.btn_settings)
        return row

    def _build_timer_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(8)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("TimerLabel")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setMinimumHeight(96)

        self.sub_label = QLabel("当前时间")
        self.sub_label.setObjectName("SubLabel")
        self.sub_label.setAlignment(Qt.AlignCenter)
        self.sub_label.setMinimumHeight(24)

        layout.addWidget(self.timer_label)
        layout.addWidget(self.sub_label)
        return card

    def _build_control_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # 模式切换
        self.btn_mode_countdown = QPushButton("倒计时")
        self.btn_mode_clock = QPushButton("指定时间")
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        for button in (self.btn_mode_countdown, self.btn_mode_clock):
            button.setObjectName("ModeButton")
            button.setCheckable(True)
            button.setMinimumHeight(50)
            button.setFocusPolicy(Qt.NoFocus)
            button.setCursor(Qt.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.mode_group.addButton(button)
            mode_row.addWidget(button, 1)
        self.btn_mode_countdown.setChecked(True)
        layout.addLayout(mode_row)

        # 设定区域（两种模式高度一致）
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_countdown_page())
        self.stack.addWidget(self._build_clock_page())
        layout.addWidget(self.stack)

        self.preview_label = QLabel("")
        self.preview_label.setObjectName("PreviewLabel")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(24)
        layout.addWidget(self.preview_label)
        return card

    def _build_countdown_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(18)
        self.spin_hours = Stepper(0, 23, 0, "小时")
        self.spin_minutes = Stepper(0, 59, 30, "分钟")
        row.addStretch(1)
        row.addWidget(self.spin_hours)
        row.addWidget(self.spin_minutes)
        row.addStretch(1)
        layout.addLayout(row)

        presets = QHBoxLayout()
        presets.setSpacing(10)
        self.preset_buttons: list[QPushButton] = []
        for minutes, label in PRESETS:
            button = QPushButton(label)
            button.setObjectName("PresetButton")
            button.setMinimumHeight(46)
            button.setFocusPolicy(Qt.NoFocus)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, m=minutes: self._apply_preset(m))
            self.preset_buttons.append(button)
            presets.addWidget(button, 1)
        layout.addLayout(presets)
        layout.addStretch(1)
        return page

    def _build_clock_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(18)
        self.spin_clock_hour = Stepper(0, 23, 23, "时")
        self.spin_clock_minute = Stepper(0, 59, 0, "分")
        row.addStretch(1)
        row.addWidget(self.spin_clock_hour)
        row.addWidget(self.spin_clock_minute)
        row.addStretch(1)
        layout.addLayout(row)

        hint = QLabel("提示：若所选时间已过，将自动安排在明天同一时间。")
        hint.setObjectName("HintLabel")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _build_actions(self) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.btn_start = QPushButton("开始定时关机")
        self.btn_start.setObjectName("PrimaryButton")
        self.btn_start.setMinimumHeight(80)
        self.btn_start.setFocusPolicy(Qt.NoFocus)
        self.btn_start.setCursor(Qt.PointingHandCursor)

        self.btn_cancel = QPushButton("取消定时")
        self.btn_cancel.setObjectName("DangerButton")
        self.btn_cancel.setMinimumHeight(64)
        self.btn_cancel.setFocusPolicy(Qt.NoFocus)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)

        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_cancel)
        return holder

    def _build_status(self) -> QLabel:
        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(24)
        return self.status_label

    # ------------------------------------------------------------------ 信号
    def _connect_signals(self) -> None:
        self.btn_mode_countdown.clicked.connect(lambda: self.set_mode("countdown"))
        self.btn_mode_clock.clicked.connect(lambda: self.set_mode("clock"))
        self.btn_settings.clicked.connect(self.ctrl.show_settings)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel.clicked.connect(self.ctrl.cancel_task)

        for stepper in (
            self.spin_hours,
            self.spin_minutes,
            self.spin_clock_hour,
            self.spin_clock_minute,
        ):
            stepper.valueChanged.connect(self._on_input_changed)

    # ------------------------------------------------------------ 配置同步
    def _apply_config_to_inputs(self) -> None:
        self._suppress_preview = True
        minutes = max(1, int(self.cfg.last_countdown_minutes))
        self.spin_hours.setValue(minutes // 60)
        self.spin_minutes.setValue(minutes % 60)
        self.spin_clock_hour.setValue(self.cfg.last_clock_hour)
        self.spin_clock_minute.setValue(self.cfg.last_clock_minute)
        self._suppress_preview = False
        self.set_mode(self.cfg.last_mode, save=False)
        self._update_preview()

    def apply_window_flags(self) -> None:
        on_top = bool(self.cfg.always_on_top)
        if bool(self.windowFlags() & Qt.WindowStaysOnTopHint) == on_top:
            return
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on_top)
        if self.isVisible():
            self.present()

    # ------------------------------------------------------------------ 模式
    def set_mode(self, mode: str, save: bool = True) -> None:
        if mode not in ("countdown", "clock"):
            mode = "countdown"
        self._mode = mode
        self.btn_mode_countdown.setChecked(mode == "countdown")
        self.btn_mode_clock.setChecked(mode == "clock")
        self.stack.setCurrentIndex(0 if mode == "countdown" else 1)
        if save:
            self.cfg.last_mode = mode
            self.ctrl.schedule_config_save()
        self._update_preview()

    def mode(self) -> str:
        return self._mode

    def _on_input_changed(self, _value: int) -> None:
        self._update_preview()
        self.ctrl.schedule_config_save()

    def _apply_preset(self, minutes: int) -> None:
        self._suppress_preview = True
        self.spin_hours.setValue(minutes // 60)
        self.spin_minutes.setValue(minutes % 60)
        self._suppress_preview = False
        self._update_preview()

    # ------------------------------------------------------------ 目标计算
    def countdown_seconds(self) -> int:
        return self.spin_hours.value() * 3600 + self.spin_minutes.value() * 60

    def clock_target(self) -> datetime:
        return next_occurrence(self.spin_clock_hour.value(), self.spin_clock_minute.value())

    def _update_preview(self) -> None:
        if self._suppress_preview:
            return
        now = datetime.now()
        if self._mode == "countdown":
            total = self.countdown_seconds()
            if total <= 0:
                self._set_preview_text("请设置大于 0 的倒计时时长")
                return
            target = now + timedelta(seconds=total)
            self._set_preview_text(
                "将于 %s 关机（%s后）" % (format_moment(target, now), humanize(total))
            )
        else:
            target = self.clock_target()
            self._set_preview_text("将于 %s 关机" % format_moment(target, now))

    # ------------------------------------------------------------ 刷新显示
    def refresh(self) -> None:
        task = self.ctrl.scheduler.task()
        now = time.time()

        if task is not None:
            remaining = max(0.0, task.target - now)
            target_dt = datetime.fromtimestamp(task.target)
            self._set_timer_text(format_hms(remaining), "active")
            self._set_sub_text(
                "目标 %s · 还剩 %s" % (format_moment(target_dt), humanize(remaining))
            )
            self._set_inputs_enabled(False)
            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self._set_button_text(self.btn_start, "定时中…")
            self._set_preview_text("定时任务进行中，设定已锁定")
        else:
            current = datetime.now()
            self._set_timer_text(current.strftime("%H:%M:%S"), "idle")
            self._set_sub_text(current.strftime("%Y年%m月%d日") + " · 未设置定时关机")
            self._set_inputs_enabled(True)
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self._set_button_text(self.btn_start, "开始定时关机")
            self._update_preview()

    @staticmethod
    def _set_button_text(button: QPushButton, text: str) -> None:
        if button.text() != text:
            button.setText(text)

    def _set_sub_text(self, text: str) -> None:
        if self.sub_label.text() != text:
            self.sub_label.setText(text)

    def _set_preview_text(self, text: str) -> None:
        if self.preview_label.text() != text:
            self.preview_label.setText(text)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        self.stack.setEnabled(enabled)
        for button in (self.btn_mode_countdown, self.btn_mode_clock, *self.preset_buttons):
            button.setEnabled(enabled)

    def _set_timer_text(self, text: str, state: str) -> None:
        if self.timer_label.text() != text:
            self.timer_label.setText(text)
        if state != self._timer_state:
            self._timer_state = state
            self.timer_label.setProperty("state", state)
            style = self.timer_label.style()
            style.unpolish(self.timer_label)
            style.polish(self.timer_label)

    # ------------------------------------------------------------ 状态文本
    def set_status(self, text: str, kind: str = "info") -> None:
        self._status_kind = kind
        colors = {"error": "#ef4444", "warn": "#f59e0b", "info": ""}
        color = colors.get(kind, "")
        if color:
            self.status_label.setStyleSheet("color: %s; font-weight: 600;" % color)
        else:
            self.status_label.setStyleSheet("")
        self.status_label.setText(text)

    # ------------------------------------------------------------------ 动作
    def _on_start(self) -> None:
        now = time.time()
        if self._mode == "countdown":
            total = self.countdown_seconds()
            if total <= 0:
                self.set_status("请先设置大于 0 的倒计时时长", "error")
                return
            target = now + total
            duration = float(total)
            self.cfg.last_countdown_minutes = max(1, total // 60)
        else:
            target_dt = self.clock_target()
            target = target_dt.timestamp()
            duration = max(1.0, target - now)
            self.cfg.last_clock_hour = self.spin_clock_hour.value()
            self.cfg.last_clock_minute = self.spin_clock_minute.value()

        self.ctrl.start_task(target=target, mode=self._mode, duration=duration)

    # ------------------------------------------------------------ 窗口行为
    def apply_theme_refresh(self) -> None:
        """主题切换后重新应用窗口标志与样式状态。"""
        self.apply_window_flags()
        self._timer_state = ""
        task = self.ctrl.scheduler.task()
        self._set_timer_text(
            self.timer_label.text(), "active" if task is not None else "idle"
        )
        self.set_status(self.status_label.text(), self._status_kind)

    def present(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def nativeEvent(self, event_type, message):  # noqa: N802 - Qt 命名
        """响应第二个实例投递的“显示主界面”窗口消息。"""
        message_id = self.ctrl.show_window_message_id()
        # 先做廉价的类型判断，避免每条原生消息都去解析 MSG 结构
        if message_id and event_type == b"windows_generic_MSG":
            if platform_win.window_message_from_native(message) == message_id:
                self.present()
                return True, 0
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self.ctrl.should_quit_on_close():
            # 托盘不可用时，「关闭」就是真的退出。
            # 这里必须显式 quit：全局设置了 setQuitOnLastWindowClosed(False)，
            # 只 accept 的话窗口没了、进程和计时器却还在后台活着，而且再也唤不回来。
            event.accept()
            self.ctrl.qapp.quit()
            return
        event.ignore()
        self.hide()
        self.ctrl.on_window_hidden()
