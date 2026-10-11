"""配置持久化：%APPDATA%\\VRShutdownTimer\\config.json"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

APP_NAME = "VRShutdownTimer"
APP_DISPLAY_NAME = "VR 定时关机"
APP_VERSION = "1.2.0"

THEMES = ("dark", "light")
MODES = ("countdown", "clock")

BOOL_FIELDS = (
    "always_on_top",
    "autostart",
    "reminder_enabled",
    "sound_enabled",
    "auto_delete_task",
    "force_shutdown",
)


def data_dir() -> Path:
    """用户目录下的数据目录（Windows 上优先 %APPDATA%）。绝不抛异常。"""
    import tempfile

    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / APP_NAME)
    candidates.append(Path(os.path.expanduser("~")) / ("." + APP_NAME))
    candidates.append(Path(tempfile.gettempdir()) / APP_NAME)

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    # 全部失败时返回首选路径，后续读写会自行忽略错误
    return candidates[0]


def assets_dir() -> Path | None:
    """返回可写的资源目录；不可写时返回 None。"""
    try:
        path = data_dir() / "assets"
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        return None


def config_path() -> Path:
    return data_dir() / "config.json"


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


@dataclass
class Config:
    # 外观
    theme: str = "dark"
    always_on_top: bool = True
    # 启动
    autostart: bool = False
    # 提醒
    reminder_enabled: bool = True
    reminder_seconds: int = 60
    sound_enabled: bool = True
    # 关机行为
    force_shutdown: bool = False
    auto_delete_task: bool = True
    grace_seconds: int = 3
    # 上次使用的设定
    last_mode: str = "countdown"
    last_countdown_minutes: int = 30
    last_clock_hour: int = 23
    last_clock_minute: int = 0
    # 进行中的任务（用于异常退出后恢复）
    pending_task: dict[str, Any] | None = None

    # ------------------------------------------------------------------ 序列化
    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            raw = json.loads(config_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        if not isinstance(raw, dict):
            return cfg

        known = {f.name for f in fields(cls)}

        # 兼容更早版本的嵌套结构：{"settings": {...}, "last_task": {...}}
        # 旧版字段名可能与当前不同（例如 quick_shutdown_*），
        # 这里只迁移能对上号的用户偏好，其余丢弃。
        nested = raw.get("settings")
        source = nested if isinstance(nested, dict) else raw

        for key, value in source.items():
            if key in known:
                setattr(cfg, key, value)

        cfg.normalize()
        # 若文件里存在历史遗留字段（如 quick_shutdown_*、last_task），
        # 或缺少当前版本字段，立即回写一份干净的配置，
        # 避免旧键长期残留、也避免下次启动重复走兼容分支。
        stale = (set(raw) - known) | (set(source) - known)
        if stale or known - set(raw):
            cfg.save()
        return cfg

    def normalize(self) -> None:
        if self.theme not in THEMES:
            self.theme = "dark"
        if self.last_mode not in MODES:
            self.last_mode = "countdown"
        # 上限与设置窗口的 Stepper(5, 600) 对齐：夹到 3600 会让手改过的值
        # 在界面上被压回 600，再保存就永久丢失。
        self.reminder_seconds = _clamp_int(self.reminder_seconds, 5, 600, 60)
        # 与设置窗口的 Stepper(1, 60) 保持一致：这里若收紧到 30，
        # 用户设的 31–60 秒会被静默截断，看起来"设置没生效"。
        self.grace_seconds = _clamp_int(self.grace_seconds, 1, 60, 3)
        self.last_countdown_minutes = _clamp_int(self.last_countdown_minutes, 1, 1439, 30)
        self.last_clock_hour = _clamp_int(self.last_clock_hour, 0, 23, 23)
        self.last_clock_minute = _clamp_int(self.last_clock_minute, 0, 59, 0)
        for name in BOOL_FIELDS:
            setattr(self, name, bool(getattr(self, name)))

        pending = self.pending_task
        if not isinstance(pending, dict):
            self.pending_task = None
            return
        try:
            float(pending["target"])
        except (KeyError, TypeError, ValueError):
            self.pending_task = None

    def reset_task_defaults(self) -> None:
        """“任务执行后自动删除”开启时，清除残留的任务设定。"""
        self.pending_task = None
        self.last_mode = "countdown"
        self.last_countdown_minutes = 30
        self.last_clock_hour = 23
        self.last_clock_minute = 0

    def save(self) -> None:
        self.normalize()
        path = config_path()
        text = json.dumps(asdict(self), ensure_ascii=False, indent=2)
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            try:
                path.write_text(text, encoding="utf-8")
            except OSError as exc:
                # 不能静默吞掉：配置写不进去，用户的设置会在重启后消失，
                # 而界面上完全看不出任何异常。
                from . import diag

                diag.log("保存配置失败 %s: %r" % (path, exc))
