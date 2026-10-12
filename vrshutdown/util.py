"""时间显示相关的小工具。"""

from __future__ import annotations

from datetime import datetime, timedelta

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def format_hms(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return "%02d:%02d:%02d" % (hours, minutes, secs)


def format_mmss(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    return "%02d:%02d" % (minutes, secs)


def humanize(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    parts: list[str] = []
    if hours:
        parts.append("%d 小时" % hours)
    if minutes:
        parts.append("%d 分" % minutes)
    if secs or not parts:
        parts.append("%d 秒" % secs)
    return " ".join(parts)


def day_prefix(moment: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now()
    delta_days = (moment.date() - now.date()).days
    if delta_days == 0:
        return "今天"
    if delta_days == 1:
        return "明天"
    if delta_days == 2:
        return "后天"
    return moment.strftime("%m-%d")


def format_moment(moment: datetime, now: datetime | None = None) -> str:
    return "%s %s" % (day_prefix(moment, now), moment.strftime("%H:%M"))


def format_full(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def next_occurrence(hour: int, minute: int, now: datetime | None = None) -> datetime:
    """返回下一次到达 hour:minute 的时刻（已过则顺延到明天）。"""
    now = now or datetime.now()
    target = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    if target <= now + timedelta(seconds=1):
        target += timedelta(days=1)
    return target


def clamp_window_size(widget, width: int, height: int) -> tuple[int, int]:
    """把固定尺寸夹到当前屏幕的可用范围内。

    Qt6 已经按 devicePixelRatio 用逻辑像素渲染，正常高 DPI 下窗口尺寸是
    正确的；但在「高 DPI + 小物理分辨率」（例如 1366×768 笔记本开到 200%，
    逻辑分辨率只剩 683×384）时，固定的 620×700 会直接溢出屏幕、底部被裁掉。
    这里兜底把尺寸夹到可用几何范围内，宁可变小也不裁切。
    """
    from PySide6.QtGui import QGuiApplication

    screen = widget.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        return width, height
    area = screen.availableGeometry()
    return min(width, area.width()), min(height, area.height())
