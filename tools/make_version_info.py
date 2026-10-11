"""由 APP_VERSION 生成主程序的 PyInstaller 版本资源文件。

    python tools/make_version_info.py

生成（并覆盖）``version_info.txt``，供 ``*.spec`` 里的 ``version=`` 使用。
该文件也提交进仓库：这样即使有人跳过本脚本、直接跑
``pyinstaller VRShutdownTimer.spec`` 也不会因为缺文件而失败。

安装包（NSIS）的版本信息不在这里管——它由 ``installer/*.nsi`` 里的
``VIProductVersion`` / ``VIAddVersionKey`` 直接生成。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vrshutdown.config import APP_VERSION  # noqa: E402

PUBLISHER = "VR Shutdown Timer"
PRODUCT = "VR 定时关机"

TEMPLATE = """# 由 tools/make_version_info.py 生成，请勿手工修改。
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tuple4},
    prodvers={tuple4},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', {publisher!r}),
         StringStruct('FileDescription', {description!r}),
         StringStruct('FileVersion', {version!r}),
         StringStruct('InternalName', {internal!r}),
         StringStruct('LegalCopyright', 'MIT License'),
         StringStruct('OriginalFilename', {filename!r}),
         StringStruct('ProductName', {product!r}),
         StringStruct('ProductVersion', {version!r})])
    ]),
    VarFileInfo([VarStruct('Translation', [0x0804, 1200])])
  ]
)
"""

TARGETS = [
    # 输出文件, 内部名, 原始文件名, 描述
    ("version_info.txt", "VRShutdownTimer", "VRShutdownTimer.exe", PRODUCT),
]


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = []
    for chunk in version.split(".")[:4]:
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)  # type: ignore[return-value]


def main() -> int:
    tuple4 = version_tuple(APP_VERSION)
    for relative, internal, filename, description in TARGETS:
        text = TEMPLATE.format(
            tuple4=tuple4,
            publisher=PUBLISHER,
            description=description,
            version=APP_VERSION,
            internal=internal,
            filename=filename,
            product=PRODUCT,
        )
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print("wrote", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
