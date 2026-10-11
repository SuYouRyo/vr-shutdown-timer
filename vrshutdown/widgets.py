"""可复用的小控件：数字步进器（VR 友好的大加减按钮）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

BUTTON_SIZE = 52
VALUE_WIDTH = 76


class Stepper(QWidget):
    """[−] 00 [+] 形式的大按钮步进器，支持长按连续调整与滚轮。

    默认在边界处**钳制**（不回绕）：到 0 再减仍是 0，到上限再加仍是上限，
    并自动禁用对应的按钮。这样用户设置「0 分钟」之类的边界值时不会手滑。
    """

    valueChanged = Signal(int)

    def __init__(
        self,
        minimum: int = 0,
        maximum: int = 59,
        value: int = 0,
        suffix: str = "",
        step: int = 1,
        wrap: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min = int(minimum)
        self._max = int(maximum)
        self._step = max(1, int(step))
        self._wrap = bool(wrap)
        self._value = self._clamp(value)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.minus_button = self._make_button("\u2212")
        self.plus_button = self._make_button("+")

        self.value_label = QLabel(self._format(self._value))
        self.value_label.setObjectName("StepValue")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setFixedWidth(VALUE_WIDTH)
        self.value_label.setFixedHeight(BUTTON_SIZE)

        layout.addWidget(self.minus_button)
        layout.addWidget(self.value_label)
        layout.addWidget(self.plus_button)

        self.suffix_label: QLabel | None = None
        if suffix:
            self.suffix_label = QLabel(suffix)
            self.suffix_label.setObjectName("FieldLabel")
            layout.addWidget(self.suffix_label)

        self.setFixedHeight(BUTTON_SIZE)
        self.setFocusPolicy(Qt.NoFocus)
        self.minus_button.clicked.connect(lambda: self._bump(-1))
        self.plus_button.clicked.connect(lambda: self._bump(1))
        self._update_enabled()

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _format(value: int) -> str:
        return "%02d" % value

    def _make_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("StepButton")
        button.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        button.setAutoRepeat(True)
        button.setAutoRepeatDelay(400)
        button.setAutoRepeatInterval(90)
        button.setFocusPolicy(Qt.NoFocus)
        return button

    def _clamp(self, value: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return self._min
        if self._wrap:
            span = self._max - self._min + 1
            if span > 0:
                return self._min + (number - self._min) % span
        return max(self._min, min(self._max, number))

    def _update_enabled(self) -> None:
        if self._wrap:
            return
        self.minus_button.setEnabled(self._value > self._min)
        self.plus_button.setEnabled(self._value < self._max)

    def _bump(self, direction: int) -> None:
        self.setValue(self._value + direction * self._step)

    # ------------------------------------------------------------------ 接口
    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        new_value = self._clamp(value)
        if new_value == self._value:
            return
        self._value = new_value
        self.value_label.setText(self._format(new_value))
        self._update_enabled()
        self.valueChanged.emit(new_value)

    def setRange(self, minimum: int, maximum: int) -> None:
        self._min = int(minimum)
        self._max = int(maximum)
        self.setValue(self._value)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if not self.isEnabled():
            return
        delta = event.angleDelta().y()
        if delta:
            self._bump(1 if delta > 0 else -1)
        event.accept()
