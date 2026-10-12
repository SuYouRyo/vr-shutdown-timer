"""核心逻辑自测（不涉及真实关机）。

    python tests/test_core.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="vrtest-")

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from vrshutdown import platform_win  # noqa: E402
from vrshutdown.config import Config, config_path  # noqa: E402
from vrshutdown.scheduler import Scheduler  # noqa: E402
from vrshutdown import diag  # noqa: E402
from vrshutdown.util import (  # noqa: E402
    format_hms,
    format_moment,
    humanize,
    next_occurrence,
)

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


def test_util() -> None:
    print("[util]")
    check("format_hms", format_hms(3725) == "01:02:05", format_hms(3725))
    check("format_hms zero", format_hms(-5) == "00:00:00")
    check("humanize", humanize(3725) == "1 小时 2 分 5 秒", humanize(3725))
    check("humanize short", humanize(45) == "45 秒", humanize(45))

    from datetime import datetime, timedelta

    now = datetime(2026, 5, 1, 22, 0, 0)
    check("next_occurrence later today",
          next_occurrence(23, 30, now) == datetime(2026, 5, 1, 23, 30))
    check("next_occurrence tomorrow",
          next_occurrence(21, 0, now) == datetime(2026, 5, 2, 21, 0))
    check("next_occurrence exact now -> tomorrow",
          next_occurrence(22, 0, now) == datetime(2026, 5, 2, 22, 0))
    check("format_moment today",
          format_moment(datetime(2026, 5, 1, 23, 30), now) == "今天 23:30")
    check("format_moment tomorrow",
          format_moment(datetime(2026, 5, 2, 1, 0), now) == "明天 01:00")
    check("format_moment weekday",
          format_moment(datetime(2026, 5, 4, 9, 5), now) == "05-04 09:05")


def test_config() -> None:
    print("[config]")
    cfg = Config()
    check("default keeps last task", cfg.auto_delete_task is False, str(cfg.auto_delete_task))
    check("default blocks sleep", cfg.block_sleep is True, str(cfg.block_sleep))
    check("default no custom sound", cfg.sound_file == "", repr(cfg.sound_file))
    cfg.theme = "light"
    cfg.reminder_seconds = 99999
    cfg.last_countdown_minutes = -3
    cfg.force_shutdown = True
    cfg.autostart = 1
    cfg.save()

    check("config file created", config_path().exists(), str(config_path()))
    loaded = Config.load()
    check("theme persisted", loaded.theme == "light", loaded.theme)
    check("reminder clamped", loaded.reminder_seconds == 600, str(loaded.reminder_seconds))
    check("minutes clamped", loaded.last_countdown_minutes == 1, str(loaded.last_countdown_minutes))
    check("bool coerced", loaded.force_shutdown is True and loaded.autostart is True)
    check("pending_task none", loaded.pending_task is None)

    # 宽限时间必须和设置窗口的 Stepper(1, 60) 一致，
    # 否则用户设的 60 秒会被静默压回 30。
    loaded.grace_seconds = 60
    loaded.normalize()
    check("grace_seconds keeps 60", loaded.grace_seconds == 60, str(loaded.grace_seconds))
    loaded.grace_seconds = 999
    loaded.normalize()
    check("grace_seconds clamped high", loaded.grace_seconds == 60, str(loaded.grace_seconds))
    loaded.grace_seconds = 0
    loaded.normalize()
    check("grace_seconds clamped low", loaded.grace_seconds == 1, str(loaded.grace_seconds))

    loaded.pending_task = {"target": time.time() + 60, "mode": "countdown",
                           "duration": 60.0, "started_at": time.time()}
    loaded.save()
    again = Config.load()
    check("pending_task persisted", isinstance(again.pending_task, dict))

    again.pending_task = {"bad": "data"}
    again.normalize()
    check("bad pending_task dropped", again.pending_task is None)

    again.reset_task_defaults()
    check("reset defaults", again.last_mode == "countdown" and again.last_countdown_minutes == 30)


def test_autostart() -> None:
    print("[autostart]")
    if os.name != "nt":
        print("  skip (not windows)")
        return
    original = platform_win.autostart_command()
    command = platform_win.launch_command()
    check("launch command has --minimized", "--minimized" in command, command)

    try:
        enabled = platform_win.set_autostart(True)
    except OSError as exc:  # 不应向外抛异常
        check("set_autostart never raises", False, repr(exc))
        return

    if not enabled:
        # 沙箱/受限环境下注册表写入会被拒绝，此时只要求优雅降级
        print("  skip 注册表写入被当前环境拒绝（程序会提示用户并回滚设置）")
        check("denied write leaves state unchanged",
              platform_win.autostart_command() == original)
        return

    try:
        check("enabled detected", platform_win.is_autostart_enabled())
        check("stored command matches current",
              platform_win._normalize_command(platform_win.autostart_command())
              == platform_win._normalize_command(command))
        check("disable", platform_win.set_autostart(False))
        check("disabled detected", not platform_win.is_autostart_enabled())
    finally:
        # 逐字节还原成运行前的样子：不能简单地 set_autostart(原始布尔值)，
        # 否则机器上一条指向旧路径的残留项会被这个测试顺手删掉。
        _restore_run_value(original)
        check("restored original state",
              platform_win.autostart_command() == original)


def _restore_run_value(value: str) -> None:
    import winreg

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, platform_win.RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if value:
            winreg.SetValueEx(key, platform_win.RUN_VALUE, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, platform_win.RUN_VALUE)
            except FileNotFoundError:
                pass


def test_shutdown_branches() -> None:
    """run_shutdown 的返回码/兜底分支。

    全程用桩替换 _run 与 initiate_shutdown_api，**绝不会真的关机**。
    """
    print("[shutdown]")
    os.environ.pop("VRSHUTDOWN_DRY_RUN", None)

    codes: list[int | None] = []
    calls: list[list[str]] = []
    original_run = platform_win._run
    original_api = platform_win.initiate_shutdown_api

    def fake_run(args, timeout=10.0):  # noqa: ANN001
        calls.append(list(args))
        return codes.pop(0) if codes else None

    try:
        platform_win._run = fake_run

        codes[:] = [0]
        outcome = platform_win.run_shutdown(force=False, grace=5)
        check("success path", outcome.ok and not outcome.escalated, str(outcome))
        check("uses absolute shutdown path",
              calls[0][0].lower().endswith("shutdown.exe"), calls[0][0])

        codes[:] = [1190]
        calls.clear()
        outcome = platform_win.run_shutdown(force=False, grace=5)
        check("already-scheduled counts as success",
              outcome.ok and not outcome.escalated, str(outcome))
        check("no escalation retry after 1190", len(calls) == 1, str(calls))

        codes[:] = [5, 0]
        calls.clear()
        outcome = platform_win.run_shutdown(force=False, grace=5)
        check("escalation is reported", outcome.ok and outcome.escalated, str(outcome))
        check("escalation retried with /f", "/f" in calls[1], str(calls))

        codes[:] = [5, 5]
        calls.clear()
        platform_win.initiate_shutdown_api = lambda force=False, grace=3: True
        outcome = platform_win.run_shutdown(force=False, grace=5)
        check("api fallback is used", outcome.ok, str(outcome))

        codes[:] = [5, 5]
        platform_win.initiate_shutdown_api = lambda force=False, grace=3: False
        outcome = platform_win.run_shutdown(force=False, grace=5)
        check("failure is reported", not outcome.ok and not outcome.escalated, str(outcome))

        codes[:] = [0]
        outcome = platform_win.run_shutdown(force=True, grace=1)
        check("forced path skips retry", outcome.ok and not outcome.escalated, str(outcome))
    finally:
        platform_win._run = original_run
        platform_win.initiate_shutdown_api = original_api
        check("stubs removed", platform_win._run is original_run)


def test_scheduler() -> None:
    print("[scheduler]")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    cfg = Config()
    cfg.reminder_enabled = True
    cfg.reminder_seconds = 5
    sched = Scheduler(cfg)

    events: list[str] = []
    sched.reminder_due.connect(lambda task, secs: events.append("reminder:%d" % secs))
    sched.fired.connect(lambda task: events.append("fired"))

    # 1) 正常触发
    sched.start(target=time.time() + 1.0, mode="countdown", duration=1.0)
    check("task active", sched.is_active())
    check("pending persisted", cfg.pending_task is not None)

    deadline = time.time() + 4.0
    while time.time() < deadline and "fired" not in events:
        app.processEvents()
        time.sleep(0.02)
    check("fired on time", "fired" in events, str(events))
    check("reminder before fire",
          any(e.startswith("reminder") for e in events), str(events))
    check("task cleared after fire", not sched.is_active())

    # 2) 取消
    events.clear()
    sched.start(target=time.time() + 30, mode="clock", duration=30.0)
    check("cancel returns True", sched.cancel() is True)
    check("cancel clears pending", cfg.pending_task is None)
    check("cancel twice returns False", sched.cancel() is False)
    deadline = time.time() + 0.6
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    check("no fire after cancel", events == [], str(events))

    # 3) 重启恢复
    cfg.pending_task = {
        "target": time.time() + 120,
        "mode": "countdown",
        "duration": 600.0,
        "started_at": time.time(),
    }
    check("restore future task", sched.restore() == "restored")
    check("restored is active", sched.is_active())

    sched.cancel()
    cfg.pending_task = {
        "target": time.time() - 60,
        "mode": "countdown",
        "duration": 600.0,
        "started_at": time.time() - 660,
    }
    check("restore expired task", sched.restore() == "expired")
    check("expired task cleared", not sched.is_active() and cfg.pending_task is None)

    check("restore with nothing", sched.restore() == "none")


def test_recovery_boundaries() -> None:
    """异常恢复的边界情况：剩余时间刚好 3 秒、配置损坏。"""
    print("[recovery-boundaries]")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    cfg = Config()
    sched = Scheduler(cfg)

    # 剩余刚好 3 秒（等于 MIN_REMAINING_TO_RESTORE 阈值）应判为「已过期」，
    # 不能恢复——否则恢复后 200ms 内就触发，用户连取消的机会都没有。
    cfg.pending_task = {
        "target": time.time() + 3.0,
        "mode": "countdown",
        "duration": 600.0,
        "started_at": time.time() - 597.0,
    }
    check("exactly 3s counts as expired", sched.restore() == "expired")
    check("expired clears pending", cfg.pending_task is None)

    # 剩余略大于阈值则正常恢复
    cfg.pending_task = {
        "target": time.time() + 3.5,
        "mode": "countdown",
        "duration": 600.0,
        "started_at": time.time(),
    }
    check("just above 3s restores", sched.restore() == "restored")
    sched.cancel()

    # 配置损坏：写入非法 JSON，加载应回退到默认值且不抛异常
    config_path().write_text("{ 这不是合法的 JSON !!!", encoding="utf-8")
    recovered = Config.load()
    check("corrupt config falls back to defaults",
          recovered.theme == "dark" and recovered.pending_task is None)
    check("corrupt config auto_delete default False", recovered.auto_delete_task is False)


def test_log_rotation() -> None:
    """日志写满后应轮转为 .1 备份，而不是无限增长或抛异常。"""
    print("[log-rotation]")
    original_max = diag.MAX_BYTES
    diag.MAX_BYTES = 128  # 用很小的阈值触发轮转，避免写几百 KB
    try:
        path = diag.log_path()
        try:
            path.unlink(missing_ok=True)
            path.with_name(path.name + ".1").unlink(missing_ok=True)
        except OSError:
            pass
        for _ in range(10):
            diag.log("x" * 64)  # 每条约 85 字节，10 条约 850 字节 > 128
        check("log rotated to .1", path.with_name(path.name + ".1").exists(),
              str(path.with_name(path.name + ".1")))
        check("log file still exists", path.exists())
    finally:
        diag.MAX_BYTES = original_max


def test_sleep_block_safe() -> None:
    """阻止/恢复睡眠在任何平台上都不应抛异常（非 Windows 是空操作）。"""
    print("[sleep-block]")
    try:
        platform_win.prevent_sleep()
        platform_win.allow_sleep()
        check("prevent/allow sleep never raise", True)
    except Exception as exc:  # noqa: BLE001
        check("prevent/allow sleep never raise", False, repr(exc))


def main() -> int:
    test_util()
    test_config()
    test_autostart()
    test_shutdown_branches()
    test_scheduler()
    test_recovery_boundaries()
    test_log_rotation()
    test_sleep_block_safe()
    print()
    print("通过 %d 项，失败 %d 项" % (PASSED, len(FAILED)))
    if FAILED:
        for name in FAILED:
            print(" - " + name)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
