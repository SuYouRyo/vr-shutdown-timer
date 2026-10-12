"""应用控制器：把配置、调度器、主窗口、托盘、提醒弹窗串起来。"""

from __future__ import annotations

import time

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import platform_win
from .config import APP_DISPLAY_NAME, Config
from .icon import app_icon
from .reminder_dialog import ReminderDialog
from .scheduler import Scheduler
from .settings_dialog import SettingsDialog
from .theme import build_qss
from .util import format_hms, format_moment

UI_REFRESH_MS = 200
TOOLTIP_REFRESH_SECONDS = 1


class _PowerEventFilter(QAbstractNativeEventFilter):
    """监听系统电源广播，唤醒后立即重新评估定时任务。

    现代待机（S0）下 QTimer 可能被挂起：机器进入 S0 再唤醒，若 QTimer 没
    及时恢复节拍，6 点该触发的关机会被拖到下一个 tick 才补上，甚至更糟。
    这里在收到 PBT_APMRESUME* 后主动 poke 调度器，用绝对时间戳立即比对一次。
    """

    def __init__(self, controller) -> None:
        super().__init__()
        self._controller = controller

    def nativeEventFilter(self, event_type, message):  # noqa: ANN001
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            event = platform_win.power_event_from_native(message)
            if event is not None:
                self._controller._on_system_power_event(event)
        return False, 0


class Controller(QObject):
    def __init__(self, qapp: QApplication, enable_tray: bool = True) -> None:
        super().__init__()
        self.qapp = qapp
        self.config = Config.load()
        self.scheduler = Scheduler(self.config, self)
        self._show_message_id = platform_win.notification_message_id()

        # 定时器先于窗口创建，避免窗口构造期间的调用落空
        self._config_save_timer = QTimer(self)
        self._config_save_timer.setSingleShot(True)
        self._config_save_timer.setInterval(600)
        self._config_save_timer.timeout.connect(self.save_session_config)

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(UI_REFRESH_MS)
        self._ui_timer.timeout.connect(self._on_ui_tick)
        self._ui_timer.start()

        from .main_window import MainWindow  # 延迟导入，避免无谓的循环引用

        self.window = MainWindow(self)
        self.reminder_dialog: ReminderDialog | None = None
        self.tray: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
        self._force_quit = False
        self._tray_hint_shown = False
        self._shutdown_issued = False
        self._skip_final_save = False
        self._last_tooltip = ""
        self._last_tooltip_at = 0.0

        self.scheduler.reminder_due.connect(self._on_reminder)
        self.scheduler.fired.connect(self._on_fired)

        # 监听系统电源广播，唤醒后立即重新评估任务（S0 下 QTimer 可能被挂起）
        self._power_filter = _PowerEventFilter(self)
        self.qapp.installNativeEventFilter(self._power_filter)

        self.apply_theme()
        self._setup_tray(enable_tray)
        self._sync_autostart_setting()

        self._restore_task()
        self.window.refresh()

    # -------------------------------------------------------------- 主题/托盘
    def apply_theme(self) -> None:
        self.qapp.setStyleSheet(build_qss(self.config.theme))

    def _setup_tray(self, enable_tray: bool) -> None:
        if not enable_tray or not QSystemTrayIcon.isSystemTrayAvailable():
            return

        menu = QMenu()
        self.act_show = QAction("显示主界面", menu)
        self.act_cancel = QAction("取消定时关机", menu)
        self.act_quit = QAction("退出程序", menu)
        self.act_show.triggered.connect(self.show_window)
        self.act_cancel.triggered.connect(self.cancel_task)
        self.act_quit.triggered.connect(self.quit_app)
        menu.addAction(self.act_show)
        menu.addAction(self.act_cancel)
        menu.addSeparator()
        menu.addAction(self.act_quit)

        tray = QSystemTrayIcon(app_icon(), self)
        tray.setToolTip(APP_DISPLAY_NAME)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()

        self.tray = tray
        self._tray_menu = menu
        self._update_tray_menu()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.show_window()

    def _update_tray_menu(self) -> None:
        if self._tray_menu is not None:
            # 关机指令已经发出、但系统还在倒计时时，托盘里的「取消」依然要可用，
            # 否则用户在最后几秒里就失去了唯一的挽救入口。
            self.act_cancel.setEnabled(self.scheduler.is_active() or self._shutdown_issued)

    def _notify(self, message: str, title: str = APP_DISPLAY_NAME, critical: bool = False) -> None:
        if self.tray is not None:
            icon = QSystemTrayIcon.Critical if critical else QSystemTrayIcon.Information
            self.tray.showMessage(title, message, icon, 6000)

    # ------------------------------------------------------------------ 窗口
    def show_window_message_id(self) -> int:
        return self._show_message_id

    def show_window(self) -> None:
        self.window.present()

    def should_quit_on_close(self) -> bool:
        return self._force_quit or self.tray is None

    def on_window_hidden(self) -> None:
        if self.tray is None:
            return
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self._notify("程序已最小化到系统托盘，定时任务会继续计时。")

    # ------------------------------------------------------------------ 任务
    def start_task(self, target: float, mode: str, duration: float) -> None:
        task = self.scheduler.start(target, mode, duration)
        if self.config.block_sleep:
            # 在倒计时期间阻止系统进入现代待机（S0），否则 VR 头显会黑屏。
            platform_win.prevent_sleep()
        self.window.refresh()
        self._update_tray_menu()
        self.window.set_status("定时关机已开始", "info")
        self._notify("将在 %s 关机" % format_moment(_dt(task.target)))

    def cancel_task(self) -> None:
        # 若关机指令已经发出，尝试撤回 Windows 关机队列
        aborted = False
        if self._shutdown_issued:
            aborted = platform_win.abort_shutdown()
            self._shutdown_issued = False
            # 撤回后本次会话不再“已发出”，允许用户重新设定
            self._skip_final_save = False
        had_task = self.scheduler.cancel()
        platform_win.allow_sleep()  # 取消任务后恢复系统默认电源策略
        self._close_reminder()
        self.window.refresh()
        self._update_tray_menu()
        if aborted:
            self.window.set_status("已撤回系统关机倒计时", "warn")
            self._notify("已撤回系统关机倒计时")
        elif had_task:
            self.window.set_status("已取消定时关机", "warn")
            self._notify("定时关机已取消")
        else:
            self.window.set_status("当前没有进行中的定时任务", "info")

    def _on_system_power_event(self, event: int) -> None:
        """系统电源事件回调：从休眠/现代待机恢复后立即重新评估任务。

        注意：本回调是在 QAbstractNativeEventFilter 里被调用的，也就是**正在处理
        原生消息**。scheduler.poke() 可能立刻走到「到点执行」，而在那里会同步等待
        shutdown.exe（最长数秒）、失败时还会弹出模态对话框——在原生事件过滤器里
        做这些事是危险的（重入事件循环、界面卡死）。
        所以这里只安排一个 0 延时定时器，把真正的评估推迟到事件循环的下一次迭代。
        """
        if event in (platform_win.PBT_APMRESUMESUSPEND, platform_win.PBT_APMRESUMEAUTOMATIC):
            platform_win.diag.log("系统已从睡眠/现代待机恢复，立即重新评估任务")
            QTimer.singleShot(0, self.scheduler.poke)

    def _restore_task(self) -> None:
        result = self.scheduler.restore()
        self._update_tray_menu()
        if result == "restored":
            if self.config.block_sleep:
                platform_win.prevent_sleep()
            self.window.refresh()
            remaining = self.scheduler.remaining() or 0
            self.window.set_status("已恢复上次的定时任务", "warn")
            self._notify("已恢复定时任务，还剩 %s" % format_hms(remaining))
        elif result == "expired":
            self.window.set_status("上次的定时任务已过期，已自动清除", "warn")

    # ------------------------------------------------------------------ 提醒
    def _on_reminder(self, task, seconds: int) -> None:
        self.show_window()
        self._close_reminder()
        dialog = ReminderDialog(self, task)
        dialog.finished.connect(self._on_reminder_closed)
        self.reminder_dialog = dialog
        dialog.present()
        if self.config.sound_enabled:
            platform_win.play_alert_sound(self.config.sound_file)
        self._notify("距离关机还有 %d 秒，点击托盘图标可取消" % seconds, critical=True)

    def _on_reminder_closed(self, _result: int) -> None:
        self.reminder_dialog = None

    def _close_reminder(self) -> None:
        dialog = self.reminder_dialog
        if dialog is not None:
            self.reminder_dialog = None
            dialog.close()
            dialog.deleteLater()

    # ------------------------------------------------------------------ 关机
    def _on_fired(self, task) -> None:
        self._close_reminder()
        # 任务已到点：不再需要阻止系统睡眠（而且系统马上就要关机了）
        platform_win.allow_sleep()
        force = bool(self.config.force_shutdown)
        grace = max(1, int(self.config.grace_seconds))
        outcome = platform_win.run_shutdown(force=force, grace=grace)
        ok = outcome.ok

        # 无论成功与否，都先把「已触发」状态落盘：
        # 若后续被系统挡住，重启后也不会莫名其妙又执行一次。
        self.config.pending_task = None
        if self.config.auto_delete_task:
            self.config.reset_task_defaults()
        self.config.save()
        # 配置已在此处落盘，退出时不要再被界面上的旧值覆盖
        self._skip_final_save = True

        self.window.refresh()
        self._update_tray_menu()

        if not ok:
            # 关机指令没能排入队列：把窗口拉到最前并明确告知，
            # 而不是像旧版那样既弹「已发出」又什么都不发生。
            self.window.set_status("关机指令发送失败，请检查系统权限或安全软件拦截", "error")
            self.show_window()
            self._notify("关机指令发送失败，请检查系统权限或安全软件拦截", critical=True)
            QMessageBox.warning(
                self.window,
                "关机失败",
                "系统拒绝了关机指令，定时关机未执行。\n\n"
                "可能原因：\n"
                "· 安全软件 / 受控文件夹访问拦截了关机命令\n"
                "· 当前用户权限不足（缺少 SeShutdownPrivilege）\n\n"
                "可在设置中改用「强制关机」后重试。",
            )
            return

        self._shutdown_issued = True

        if outcome.escalated:
            # 用户选的是「正常关机」，是被程序阻止后才升级为强制的：
            # 必须明确告知，不能悄悄强杀别的程序里未保存的内容。
            message = "正常关机被其他程序阻止，已改为强制关机，系统将在 %d 秒后关机" % grace
            self.window.set_status(message, "warn")
            self._notify(message, critical=True)
        else:
            message = "关机指令已发出，系统将在 %d 秒后关机" % grace
            self.window.set_status(message, "warn")
            self._notify(message)

        # 不做 app.quit()：留在托盘里，用户仍可用「取消定时关机」撤回
        # （底层就是 shutdown /a）。系统真正关机时进程会被一起结束。
        self.show_window()

    # ------------------------------------------------------------------ 设置
    def show_settings(self) -> None:
        dialog = SettingsDialog(self.config, self.window)
        if dialog.exec() != SettingsDialog.Accepted:
            return

        values = dialog.values()
        theme_changed = values["theme"] != self.config.theme
        for key, value in values.items():
            setattr(self.config, key, value)

        applied = platform_win.set_autostart(self.config.autostart)
        if self.config.autostart and not applied:
            self.config.autostart = platform_win.is_autostart_enabled()
            QMessageBox.warning(
                self.window,
                "开机自启",
                "无法写入开机自启项，请检查系统安全软件设置。",
            )

        self.config.save()
        # 若任务进行中，立即按新设置同步阻止睡眠状态（开关可能被刚改过）
        if self.scheduler.is_active():
            if self.config.block_sleep:
                platform_win.prevent_sleep()
            else:
                platform_win.allow_sleep()
        if theme_changed:
            self.apply_theme()
        self.window.apply_theme_refresh()
        self.window.set_status("设置已保存", "info")

    def _sync_autostart_setting(self) -> None:
        """让 config.autostart 与注册表保持一致，并自愈过期的自启路径。"""
        stored = platform_win.autostart_command()
        if not stored:
            if self.config.autostart:
                self.config.autostart = False
                self.config.save()
            return

        enabled = platform_win.is_autostart_enabled()
        if not enabled:
            # 注册表里留着旧路径（换了安装目录 / 从桌面绿色版改成安装版）：
            # 按当前路径重写一次，否则用户会以为自启开着、开机却什么都没发生。
            platform_win.set_autostart(True)
            platform_win.diag.log("已把过期的开机自启项更新为当前路径")
        if not self.config.autostart:
            self.config.autostart = True
            self.config.save()

    # ------------------------------------------------------------------ 时钟
    def schedule_config_save(self) -> None:
        self._config_save_timer.start()

    def save_session_config(self) -> None:
        """保存界面上当前的设定（延迟保存 / 主动退出时使用）。"""
        self.config.last_mode = self.window.mode()
        if self.window.mode() == "countdown":
            total = self.window.countdown_seconds()
            if total > 0:
                self.config.last_countdown_minutes = max(1, total // 60)
        else:
            self.config.last_clock_hour = self.window.spin_clock_hour.value()
            self.config.last_clock_minute = self.window.spin_clock_minute.value()
        self.config.save()

    def save_on_quit(self) -> None:
        """应用退出前调用。

        若关机指令刚刚发出（配置已按最终状态落盘），不要再拿界面上的旧
        输入值覆盖它；其余情况正常保存当前设定。
        """
        if self._skip_final_save:
            return
        self.save_session_config()

    def _on_ui_tick(self) -> None:
        self.window.refresh()
        if self.tray is not None:
            now = time.time()
            if now - self._last_tooltip_at >= TOOLTIP_REFRESH_SECONDS:
                self._last_tooltip_at = now
                self._refresh_tooltip()

    def _refresh_tooltip(self) -> None:
        task = self.scheduler.task()
        if task is None:
            text = "%s · 未设置定时关机" % APP_DISPLAY_NAME
        else:
            remaining = max(0.0, task.target - time.time())
            text = "%s · 还剩 %s" % (APP_DISPLAY_NAME, format_hms(remaining))
        if text != self._last_tooltip:
            self._last_tooltip = text
            self.tray.setToolTip(text)

    # ------------------------------------------------------------------ 退出
    def quit_app(self) -> None:
        if self.scheduler.is_active():
            answer = QMessageBox.question(
                self.window,
                "退出程序",
                "当前有正在进行的定时关机任务，退出将取消该任务。\n确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            self.scheduler.cancel()

        self._force_quit = True
        # 主动退出时希望保存当前设定，临时解除跳过标志
        self._skip_final_save = False
        self.save_session_config()
        self.config.pending_task = None
        self.config.save()
        platform_win.allow_sleep()  # 退出前恢复系统默认电源策略
        if self.tray is not None:
            self.tray.hide()
        self.qapp.quit()


def _dt(timestamp: float):
    from datetime import datetime

    return datetime.fromtimestamp(timestamp)
