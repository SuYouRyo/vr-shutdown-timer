"""轻量诊断日志。

写入 ``%APPDATA%\\VRShutdownTimer\\startup.log``（目录不可写时自动回退）。
windowed（--noconsole）打包下 stdout/stderr 为 None，任何错误都是无声的，
所以关键路径的失败都要在这里留痕，而不是只 except 掉。

设置环境变量 ``VRSHUTDOWN_NO_LOG=1`` 可关闭。
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

# 超过该大小就轮转一份 .1 备份，避免日志无限增长。
MAX_BYTES = 256 * 1024

_DISABLED = os.environ.get("VRSHUTDOWN_NO_LOG", "").strip() == "1"


def log_path() -> Path:
    from .config import data_dir

    return data_dir() / "startup.log"


def log(message: str) -> None:
    """追加一行诊断日志。永远不抛异常——日志本身不能拖垮程序。"""
    if _DISABLED:
        return
    try:
        path = log_path()
        try:
            if path.exists() and path.stat().st_size > MAX_BYTES:
                path.replace(path.with_name(path.name + ".1"))
        except OSError:
            pass
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("%s  %s\n" % (stamp, message))
    except Exception:
        pass
