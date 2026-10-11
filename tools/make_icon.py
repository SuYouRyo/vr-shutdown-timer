"""生成 assets/app.ico（仅依赖 PySide6，无需 Pillow）。

    python tools/make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from vrshutdown.icon import power_image  # noqa: E402

ASSETS = ROOT / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _png_bytes(size: int) -> bytes:
    image = power_image(size)
    # QByteArray 必须保持存活，否则 QBuffer 会持有悬空指针导致崩溃
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    ok = image.save(buffer, "PNG")
    buffer.close()
    if not ok:
        raise RuntimeError("无法生成 %dx%d PNG" % (size, size))
    return bytes(data)


def write_ico(target: Path, sizes=SIZES) -> None:
    """按 ICO 规范写入多尺寸图标（PNG 压缩条目，Windows Vista+ 支持）。"""
    payloads = [_png_bytes(size) for size in sizes]

    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = bytearray()
    offset = len(header) + 16 * len(sizes)
    for size, payload in zip(sizes, payloads):
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            dimension,  # 宽（0 表示 256）
            dimension,  # 高
            0,  # 调色板数量
            0,  # 保留
            1,  # 颜色平面
            32,  # 位深
            len(payload),
            offset,
        )
        offset += len(payload)

    target.write_bytes(header + bytes(entries) + b"".join(payloads))


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841

    ico = ASSETS / "app.ico"
    write_ico(ico)
    print("wrote", ico, ico.stat().st_size, "bytes")

    preview = ASSETS / "app_preview.png"
    preview.write_bytes(_png_bytes(256))
    print("wrote", preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
