"""端到端流程自测：提醒弹窗、取消、到点执行、任务自动删除。

通过 VRSHUTDOWN_DRY_RUN=1 保证**绝不会真的关机**。

    python tests/test_flow.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="vrflow-")
os.environ["VRSHUTDOWN_DRY_RUN"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from vrshutdown.app import Controller  # noqa: E402
from vrshutdown import platform_win  # noqa: E402

PASSED = 0
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if condition:
        PASSED += 1
        print("  ok   %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL %s %s" % (name, detail))


def pump(app: QApplication, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def main() -> int:
    check("dry-run enabled", platform_win.dry_run())
    # 关机命令用 System32 下的绝对路径，避免 PATH 被劫持或裁剪。
    exe = platform_win.shutdown_exe()
    check("shutdown path is absolute",
          exe.lower().endswith("system32\\shutdown.exe"), exe)
    check("normal shutdown args",
          platform_win.shutdown_args(False, 3) ==
          [exe, "/s", "/t", "3", "/c", "VR Shutdown Timer"],
          str(platform_win.shutdown_args(False, 3)))
    check("forced shutdown args",
          platform_win.shutdown_args(True, 5) ==
          [exe, "/s", "/f", "/t", "5", "/c", "VR Shutdown Timer"],
          str(platform_win.shutdown_args(True, 5)))

    app = QApplication(sys.argv[:1])
    ctrl = Controller(app, enable_tray=False)
    cfg = ctrl.config
    cfg.reminder_enabled = True
    cfg.reminder_seconds = 5
    cfg.sound_enabled = False
    cfg.auto_delete_task = True

    # ---------------------------------------------------------- 场景一：提醒 + 取消
    print("[提醒与取消]")
    ctrl.start_task(target=time.time() + 6, mode="countdown", duration=6.0)
    check("task started", ctrl.scheduler.is_active())
    check("persisted for crash recovery", isinstance(cfg.pending_task, dict))

    pump(app, 4.0)
    check("reminder dialog shown",
          ctrl.reminder_dialog is not None and ctrl.reminder_dialog.isVisible())
    check("main window refreshed in countdown state",
          ctrl.window.timer_label.text() != "00:00:00")

    if ctrl.reminder_dialog is not None:
        ctrl.reminder_dialog._on_cancel()
    pump(app, 1.0)
    check("cancel from reminder clears task", not ctrl.scheduler.is_active())
    check("cancel clears persisted task", cfg.pending_task is None)
    check("reminder dialog closed", ctrl.reminder_dialog is None)
    check("cancel status message", "取消" in ctrl.window.status_label.text(),
          ctrl.window.status_label.text())

    # ---------------------------------------------------------- 场景二：到点执行
    print("[到点执行 - 自动删除]")
    ctrl.start_task(target=time.time() + 2, mode="countdown", duration=2.0)
    pump(app, 4.0)
    check("task cleared after fire", not ctrl.scheduler.is_active())
    check("auto delete cleared pending", cfg.pending_task is None)
    check("auto delete reset defaults",
          cfg.last_countdown_minutes == 30 and cfg.last_mode == "countdown",
          "minutes=%s mode=%s" % (cfg.last_countdown_minutes, cfg.last_mode))
    check("status reports shutdown issued",
          "关机指令已发出" in ctrl.window.status_label.text(),
          ctrl.window.status_label.text())

    # ---------------------------------------------------------- 场景三：保留设定
    print("[到点执行 - 保留设定]")
    cfg.auto_delete_task = False
    ctrl.window.set_mode("countdown")
    ctrl.window.spin_hours.setValue(2)
    ctrl.window.spin_minutes.setValue(15)
    ctrl.start_task(target=time.time() + 1, mode="countdown", duration=1.0)
    pump(app, 3.0)
    check("pending cleared even when keeping settings", cfg.pending_task is None)
    check("last countdown kept", cfg.last_countdown_minutes == 135,
          str(cfg.last_countdown_minutes))

    # ---------------------------------------------------------- 场景四：无任务时的取消
    print("[边界情况]")
    ctrl.cancel_task()
    check("cancel without task is safe", not ctrl.scheduler.is_active())
    check("cancel without task reports idle",
          "没有进行中" in ctrl.window.status_label.text(),
          ctrl.window.status_label.text())

    ctrl.window.spin_hours.setValue(0)
    ctrl.window.spin_minutes.setValue(0)
    ctrl.window.set_mode("countdown")
    ctrl.window._on_start()
    check("reject zero-length countdown",
          "大于 0" in ctrl.window.status_label.text(),
          ctrl.window.status_label.text())

    # ---------------------------------------------------------- 场景五：时钟模式
    cfg.reminder_enabled = False
    ctrl.window.set_mode("clock")
    ctrl.window.spin_clock_hour.setValue(3)
    ctrl.window.spin_clock_minute.setValue(0)
    ctrl.window._on_start()
    check("clock mode starts task", ctrl.scheduler.is_active())
    task = ctrl.scheduler.task()
    from datetime import datetime, timedelta

    expected = datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
    if expected <= datetime.now():
        expected += timedelta(days=1)
    check("clock target computed correctly",
          abs(task.target - expected.timestamp()) < 2.0,
          "%s vs %s" % (datetime.fromtimestamp(task.target), expected))
    ctrl.cancel_task()

    print()
    print("通过 %d 项，失败 %d 项" % (PASSED, len(FAILED)))
    for name in FAILED:
        print(" - " + name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
