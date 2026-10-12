"""关机前提醒弹窗：置顶、大字、按钮大，方便在 VR 中看到并取消。"""

from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .util import clamp_window_size, format_moment

WIDTH = 620
HEIGHT = 380


class ReminderDialog(QDialog):
    def __init__(self, controller, task) -> None:
        super().__init__(None)
        self.ctrl = controller
        self.task = task
        self._drag_offset: QPoint | None = None

        self.setObjectName("ReminderRoot")
        self.setWindowTitle("即将关机")
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        width, height = clamp_window_size(self, WIDTH, HEIGHT)
        self.setFixedSize(width, height)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("ReminderPanel")
        root.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(32, 26, 32, 28)
        layout.setSpacing(10)

        title = QLabel("⚠  准备关机")
        title.setObjectName("ReminderTitle")
        title.setAlignment(Qt.AlignCenter)

        caption = QLabel("距离自动关机还有")
        caption.setObjectName("ReminderCaption")
        caption.setAlignment(Qt.AlignCenter)

        self.count_label = QLabel("00:00")
        self.count_label.setObjectName("ReminderCount")
        self.count_label.setAlignment(Qt.AlignCenter)
        self.count_label.setMinimumHeight(96)

        self.target_label = QLabel("")
        self.target_label.setObjectName("ReminderCaption")
        self.target_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(caption)
        layout.addWidget(self.count_label)
        layout.addWidget(self.target_label)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(16)
        self.btn_cancel = QPushButton("取消关机")
        self.btn_cancel.setObjectName("DangerSolidButton")
        self.btn_cancel.setMinimumHeight(84)
        self.btn_cancel.setFocusPolicy(Qt.NoFocus)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel)

        self.btn_keep = QPushButton("继续关机")
        self.btn_keep.setObjectName("NeutralButton")
        self.btn_keep.setMinimumHeight(84)
        self.btn_keep.setFocusPolicy(Qt.NoFocus)
        self.btn_keep.setCursor(Qt.PointingHandCursor)
        self.btn_keep.clicked.connect(self.accept)

        buttons.addWidget(self.btn_cancel, 1)
        buttons.addWidget(self.btn_keep, 1)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()
        self._center_on_screen()

    # ------------------------------------------------------------------ 内部
    def _center_on_screen(self) -> None:
        """居中显示在光标所在的屏幕。

        原实现固定用 primaryScreen()，在 VR 或多屏环境下提醒窗可能弹到
        用户看不见的那块屏，等于没有提醒。优先使用鼠标所在屏。
        """
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(
                area.center().x() - self.width() // 2,
                area.center().y() - self.height() // 2,
            )

    def present(self) -> None:
        """把提醒窗强制拉到最前（含抢焦点），确保用户能看到。"""
        self.show()
        self.raise_()
        self.activateWindow()

    def _refresh(self) -> None:
        remaining = self.task.target - time.time()
        if remaining <= 0:
            self.count_label.setText("00:00")
            return
        seconds = int(remaining)
        minutes, secs = divmod(seconds, 60)
        if minutes >= 60:
            hours, minutes = divmod(minutes, 60)
            self.count_label.setText("%d:%02d:%02d" % (hours, minutes, secs))
        else:
            self.count_label.setText("%02d:%02d" % (minutes, secs))
        target_dt = datetime.fromtimestamp(self.task.target)
        self.target_label.setText("目标时间 %s" % format_moment(target_dt))

    def _on_cancel(self) -> None:
        self.ctrl.cancel_task()
        self.reject()

    # ------------------------------------------------------------ 窗口拖动
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # 避免误按 Esc / 回车导致误判
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            event.ignore()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().closeEvent(event)
