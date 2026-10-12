"""定时调度器：基于绝对时间戳计时，避免累加误差与休眠漂移。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal


@dataclass
class Task:
    target: float  # 目标时间（Unix 时间戳，秒）
    mode: str  # "countdown" | "clock"
    duration: float  # 设定时的总时长（秒）
    started_at: float  # 创建时间

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "mode": self.mode,
            "duration": self.duration,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            target=float(data["target"]),
            mode=str(data.get("mode", "countdown")),
            duration=float(data.get("duration", 0.0)),
            started_at=float(data.get("started_at", time.time())),
        )


class Scheduler(QObject):
    """每 200ms 检查一次目标时间；界面关闭不影响计时。"""

    tick = Signal(object, object)  # (Task | None, 剩余秒数 | None)
    reminder_due = Signal(object, int)  # (Task, 剩余整秒)
    fired = Signal(object)  # (Task)
    task_changed = Signal(object)  # (Task | None)

    INTERVAL_MS = 200
    MIN_REMAINING_TO_RESTORE = 3.0

    def __init__(self, config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._task: Task | None = None
        self._reminded = False
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    # ------------------------------------------------------------------ 查询
    def task(self) -> Task | None:
        return self._task

    def is_active(self) -> bool:
        return self._task is not None

    def remaining(self) -> float | None:
        if self._task is None:
            return None
        return self._task.target - time.time()

    # ------------------------------------------------------------------ 控制
    def start(self, target: float, mode: str, duration: float) -> Task:
        now = time.time()
        self._task = Task(
            target=float(target),
            mode=mode,
            duration=max(1.0, float(duration)),
            started_at=now,
        )
        self._reminded = False
        self._config.pending_task = self._task.to_dict()
        self._config.save()
        self.task_changed.emit(self._task)
        return self._task

    def cancel(self) -> bool:
        had_task = self._task is not None
        self._task = None
        self._reminded = False
        if self._config.pending_task is not None:
            self._config.pending_task = None
            self._config.save()
        if had_task:
            self.task_changed.emit(None)
        return had_task

    def restore(self) -> str:
        """重启后恢复未完成的任务。

        返回 "restored" / "expired" / "none"。
        """
        data = self._config.pending_task
        if not data:
            return "none"
        try:
            task = Task.from_dict(data)
        except (KeyError, TypeError, ValueError):
            self._config.pending_task = None
            self._config.save()
            return "none"

        if task.target - time.time() <= self.MIN_REMAINING_TO_RESTORE:
            self._config.pending_task = None
            self._config.save()
            return "expired"

        self._task = task
        self._reminded = False
        self.task_changed.emit(task)
        return "restored"

    def poke(self) -> None:
        """立即重新评估一次目标时间（系统从休眠/现代待机唤醒时调用）。

        S0 现代待机下 QTimer 可能被挂起，唤醒瞬间不会立刻触发 tick。
        应用层在收到系统「已恢复」广播后调用本方法，立即用绝对时间戳
        比对一次：若目标时刻已在休眠期间过去，会马上补执行关机或提醒，
        不依赖 QTimer 恢复节拍。
        """
        self._on_tick()

    # ------------------------------------------------------------------ 计时
    def _reminder_threshold(self, task: Task) -> float | None:
        if not self._config.reminder_enabled:
            return None
        configured = float(max(1, int(self._config.reminder_seconds)))
        # 短倒计时不要一开始就弹提醒
        return min(configured, max(5.0, task.duration * 0.5))

    def _on_tick(self) -> None:
        task = self._task
        if task is None:
            self.tick.emit(None, None)
            return

        remaining = task.target - time.time()
        self.tick.emit(task, remaining)

        if remaining <= 0:
            self._task = None
            self._reminded = False
            self.task_changed.emit(None)
            self.fired.emit(task)
            return

        if not self._reminded:
            threshold = self._reminder_threshold(task)
            if threshold is not None and remaining <= threshold:
                self._reminded = True
                self.reminder_due.emit(task, max(1, int(round(remaining))))
