"""VR 定时关机 —— 程序入口。

用法:
    python main.py              # 正常启动
    python main.py --minimized  # 启动后直接最小化到系统托盘（开机自启用）
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from vrshutdown import platform_win  # noqa: E402
from vrshutdown.app import Controller  # noqa: E402
from vrshutdown.config import APP_DISPLAY_NAME, APP_NAME, APP_VERSION  # noqa: E402
from vrshutdown.diag import log as _log  # noqa: E402
from vrshutdown.icon import app_icon  # noqa: E402


def _install_excepthook() -> None:
    """windowed 模式下把未捕获异常写进日志，避免程序静默消失。"""

    def _hook(exc_type, exc_value, exc_tb):  # noqa: ANN001
        import traceback

        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _log("UNCAUGHT EXCEPTION:\n" + text)

    sys.excepthook = _hook


def _activate_existing_instance() -> bool:
    """已有实例在运行时，请求它显示主界面并返回 True。"""
    message_id = platform_win.notification_message_id()
    return platform_win.notify_existing_window(APP_DISPLAY_NAME, message_id)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    start_minimized = "--minimized" in argv

    _install_excepthook()
    _log("--- 启动 (frozen=%s, minimized=%s) ---" % (getattr(sys, "frozen", False), start_minimized))

    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_DISPLAY_NAME)
    QApplication.setApplicationVersion(APP_VERSION)
    QApplication.setOrganizationName(APP_NAME)
    QApplication.setQuitOnLastWindowClosed(False)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 单实例：命名互斥体检测 + 自定义窗口消息唤醒已有窗口
    is_first, mutex_handle = platform_win.acquire_single_instance()
    _log("单实例检测: is_first=%s" % is_first)
    if not is_first:
        ok = _activate_existing_instance()
        _log("非首实例，唤醒已存在窗口: %s，退出" % ok)
        return 0

    app = QApplication(argv)
    try:
        app.setWindowIcon(app_icon())
        app._mutex_handle = mutex_handle  # 保持句柄存活，进程退出自动释放
        _log("QApplication 已创建")

        controller = Controller(app, enable_tray=True)
        app.aboutToQuit.connect(controller.save_on_quit)
        _log("Controller 已就绪，托盘=%s" % (controller.tray is not None))

        if start_minimized and controller.tray is not None:
            controller.window.hide()
        else:
            controller.window.present()

        _log("进入事件循环")
        return app.exec()
    finally:
        # 构造 Controller 失败时也要释放互斥体，否则用户必须重启系统
        # 才能再次启动程序（"打开没反应"）。
        platform_win.release_single_instance(mutex_handle)


if __name__ == "__main__":
    sys.exit(main())
