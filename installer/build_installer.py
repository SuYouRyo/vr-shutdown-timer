"""构建 Windows 安装包（NSIS）。

    python installer/build_installer.py

产物::

    dist_installer/VRShutdownTimer-Setup-<版本>.exe

需要 NSIS 的 makensis。查找顺序：

1. 环境变量 ``MAKENSIS``（makensis.exe 的完整路径）；
2. ``PATH`` 里的 makensis.exe；
3. 常见安装位置 ``%ProgramFiles(x86)%\\NSIS\\makensis.exe`` 等。

同时会把 ``NSISDIR`` 指向 makensis 所在目录，这样便携解压版也能直接编译。

**为什么是 NSIS？** Steam 的安装器就是 NSIS 做的，它正是用户熟悉的
「许可页 → 选目录 → 进度条 → 完成页」那套向导，并自带卸载器。
NSIS 用 LZMA 固实压缩把整个程序目录塞进一个 exe，比 zip 方案小很多，
而且安装器本身只有几百 KB，启动几乎是瞬时的。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vrshutdown.config import APP_VERSION  # noqa: E402

INSTALLER_DIR = ROOT / "installer"
PORTABLE_DIR = ROOT / "dist_portable" / "VRShutdownTimer"
PORTABLE_EXE = PORTABLE_DIR / "VRShutdownTimer.exe"
DIST = ROOT / "dist_installer"
OUT_FILE = DIST / f"VRShutdownTimer-Setup-{APP_VERSION}.exe"
UNINSTALLER_OUT = DIST / "VRShutdownTimer-Uninstall.exe"
SCRIPT = INSTALLER_DIR / "VRShutdownTimer.nsi"
UNINSTALLER_SCRIPT = INSTALLER_DIR / "VRShutdownTimer-Uninstall.nsi"
ICON = ROOT / "assets" / "app.ico"
LICENSE = ROOT / "LICENSE"


def find_makensis() -> Path:
    candidates: list[Path] = []
    explicit = os.environ.get("MAKENSIS")
    if explicit:
        candidates.append(Path(explicit))

    found = shutil.which("makensis")
    if found:
        candidates.append(Path(found))
    found = shutil.which("makensis.exe")
    if found:
        candidates.append(Path(found))

    for base in (
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
        os.environ.get("LOCALAPPDATA"),
    ):
        if base:
            candidates.append(Path(base) / "NSIS" / "makensis.exe")

    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate

    raise SystemExit(
        "找不到 makensis.exe。\n"
        "  1) 安装 NSIS: https://nsis.sourceforge.io/Download\n"
        "  2) 或者设置环境变量 MAKENSIS 指向 makensis.exe\n"
        "  3) 或者把 makensis.exe 所在目录加入 PATH"
    )


def human(size: int) -> str:
    return "%.1f MB" % (size / 1024 / 1024)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def preflight() -> None:
    if not PORTABLE_EXE.exists():
        raise SystemExit(
            "找不到 %s\n请先执行:  powershell -ExecutionPolicy Bypass -File build.ps1 -Portable"
            % PORTABLE_EXE
        )
    for path in (SCRIPT, UNINSTALLER_SCRIPT, ICON, LICENSE):
        if not path.exists():
            raise SystemExit("缺少必要文件: %s" % path)


def makensis_env(makensis: Path) -> dict:
    env = dict(os.environ)
    env["NSISDIR"] = str(makensis.parent)
    # makensis 会在 %TEMP% 下建几十 MB 的内存映射文件；某些受限/被重定向的
    # 临时目录会让它直接报 "Internal compiler error: error creating mmap"。
    # 固定用一个构建期临时目录，既绕开这个问题，也让产物可复现。
    scratch = ROOT / "build_installer" / "nsis-tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(scratch)
    env["TMP"] = str(scratch)
    return env


def compile_nsis(makensis: Path, script: Path, defines: list[str], label: str) -> None:
    command = [str(makensis), "/V2", *defines, str(script)]
    print("$", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=str(ROOT), env=makensis_env(makensis))
    if result.returncode != 0:
        raise SystemExit("%s 失败（makensis 退出码 %d）" % (label, result.returncode))


def main() -> int:
    preflight()
    makensis = find_makensis()
    DIST.mkdir(parents=True, exist_ok=True)
    for stale in (OUT_FILE, UNINSTALLER_OUT):
        if stale.exists():
            stale.unlink()

    payload_bytes = sum(p.stat().st_size for p in PORTABLE_DIR.rglob("*") if p.is_file())
    print("==> NSIS: %s" % makensis, flush=True)
    print("==> 负载: %s (%s)" % (PORTABLE_DIR, human(payload_bytes)), flush=True)

    # 卸载器先编：安装器要把它作为 uninstall.exe 一起放进去
    print("==> 编译卸载器", flush=True)
    compile_nsis(
        makensis,
        UNINSTALLER_SCRIPT,
        [f"/DAPP_VERSION={APP_VERSION}", f"/DOUT_FILE={UNINSTALLER_OUT}",
         f"/DICON_FILE={ICON}"],
        "卸载器",
    )
    if not UNINSTALLER_OUT.exists():
        raise SystemExit("构建结束但没有卸载器：%s" % UNINSTALLER_OUT)

    print("==> 编译安装器", flush=True)
    compile_nsis(
        makensis,
        SCRIPT,
        [f"/DAPP_VERSION={APP_VERSION}", f"/DSOURCE_DIR={PORTABLE_DIR}",
         f"/DOUT_FILE={OUT_FILE}", f"/DUNINSTALLER_EXE={UNINSTALLER_OUT}",
         f"/DICON_FILE={ICON}", f"/DLICENSE_FILE={LICENSE}"],
        "安装器",
    )
    if not OUT_FILE.exists():
        raise SystemExit("构建结束但没有产物：%s" % OUT_FILE)

    size = OUT_FILE.stat().st_size
    print()
    print("完成:")
    print("  %s  %s  （负载 %s，压缩率 %.0f%%）"
          % (OUT_FILE, human(size), human(payload_bytes), size * 100.0 / max(1, payload_bytes)))
    print("  SHA256  %s" % sha256(OUT_FILE))
    print("  %s  %s（独立卸载器，安装器会把它放进安装目录）"
          % (UNINSTALLER_OUT, human(UNINSTALLER_OUT.stat().st_size)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
