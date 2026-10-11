"""开发辅助：把各个界面渲染成 PNG，用于检查排版是否错乱。

    python tools/screenshot.py [输出目录]
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 用工作区内的临时目录当 APPDATA，避免污染真实配置
_TMP = ROOT / ".screenshot-tmp"
_TMP.mkdir(parents=True, exist_ok=True)
os.environ["APPDATA"] = str(_TMP)

# 默认使用真实 Windows 平台以获得与运行时一致的字体渲染
if os.environ.get("VR_SHOT_OFFSCREEN") == "1":
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from vrshutdown.app import Controller  # noqa: E402
from vrshutdown.reminder_dialog import ReminderDialog  # noqa: E402
from vrshutdown.settings_dialog import SettingsDialog  # noqa: E402


def _shot(widget, path: Path) -> None:
    QApplication.processEvents()
    pixmap = widget.grab()
    pixmap.save(str(path), "PNG")
    print("saved", path, pixmap.width(), "x", pixmap.height())


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "screenshots"
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv[:1])
    ctrl = Controller(app, enable_tray=False)
    window = ctrl.window
    window.show()
    QApplication.processEvents()

    theme = ctrl.config.theme

    # 1) 空闲态
    _shot(window, out / f"main-idle-{theme}.png")

    # 2) 倒计时模式（运行中）
    ctrl.start_task(target=time.time() + 3725, mode="countdown", duration=3725)
    QApplication.processEvents()
    _shot(window, out / f"main-running-{theme}.png")

    # 3) 指定时间模式
    ctrl.cancel_task()
    window.set_mode("clock")
    window.spin_clock_hour.setValue(23)
    window.spin_clock_minute.setValue(30)
    QApplication.processEvents()
    _shot(window, out / f"main-clock-{theme}.png")

    # 4) 设置窗口
    dialog = SettingsDialog(ctrl.config, window)
    dialog.show()
    QApplication.processEvents()
    _shot(dialog, out / f"settings-{theme}.png")
    dialog.close()

    # 5) 提醒弹窗
    task = ctrl.scheduler.task()
    fake = type("T", (), {})()
    fake.target = time.time() + 58
    fake.mode = "countdown"
    fake.duration = 3600.0
    fake.started_at = time.time()
    reminder = ReminderDialog(ctrl, fake)
    reminder.show()
    QApplication.processEvents()
    _shot(reminder, out / f"reminder-{theme}.png")
    reminder.close()

    # 6) 浅色主题
    ctrl.config.theme = "light"
    ctrl.apply_theme()
    QApplication.processEvents()
    window.set_mode("countdown")
    window.spin_hours.setValue(1)
    window.spin_minutes.setValue(30)
    QApplication.processEvents()
    _shot(window, out / "main-idle-light.png")

    dialog = SettingsDialog(ctrl.config, window)
    dialog.show()
    QApplication.processEvents()
    _shot(dialog, out / "settings-light.png")
    dialog.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
