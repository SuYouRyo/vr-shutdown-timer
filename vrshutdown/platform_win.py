"""Windows 平台相关操作：关机、取消关机、开机自启、提示音。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import NamedTuple

from . import diag

IS_WINDOWS = os.name == "nt"

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "VRShutdownTimer"

SHUTDOWN_COMMENT = "VR Shutdown Timer"

# 阻止系统睡眠 / 现代待机（S0）用的线程执行状态标志。
# 注意：只设置 ES_SYSTEM_REQUIRED，不设置 ES_DISPLAY_REQUIRED——我们不希望
# 倒计时期间屏幕常亮（那会打扰 VR 之外的使用场景），只要系统别进 S0 就行。
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

# ---------------------------------------------------------------- 单实例 --
# 使用命名互斥体判断是否已有实例（比命名管道更稳），
# 通过注册的自定义窗口消息让已有实例把主界面显示到前台。

MUTEX_NAME = "Local\\VRShutdownTimer.SingleInstance"
SHOW_WINDOW_MESSAGE = "VRShutdownTimer.ShowWindow"
ERROR_ALREADY_EXISTS = 183


def acquire_single_instance(name: str = MUTEX_NAME) -> tuple[bool, object]:
    """返回 (是否第一个实例, 互斥体句柄)。互斥体句柄需保持存活。"""
    if not IS_WINDOWS:
        return True, None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
    except OSError:
        return True, None

    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return True, None
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS, handle


def release_single_instance(handle) -> None:
    """显式释放互斥体句柄。

    进程退出时系统本来也会释放，但如果 QApplication / Controller 构造失败，
    手上有句柄却不关，会让后续所有启动都被判定为"已有实例"而静默退出。
    """
    if not IS_WINDOWS or not handle:
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.CloseHandle(handle)
    except OSError:
        pass


def notification_message_id() -> int:
    """注册（或取得）跨进程一致的窗口消息 ID。"""
    if not IS_WINDOWS:
        return 0
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterWindowMessageW.argtypes = [ctypes.c_wchar_p]
        user32.RegisterWindowMessageW.restype = ctypes.c_uint
        return int(user32.RegisterWindowMessageW(SHOW_WINDOW_MESSAGE))
    except OSError:
        return 0


def notify_existing_window(title: str, message_id: int) -> bool:
    """向已有实例的主窗口投递“显示界面”消息。

    旧实现只用 FindWindowW(None, title) 按标题匹配，一旦 Qt 因高 DPI、
    语言或窗口尚未创建完成而改写了标题就会失败，导致第二个实例起来后
    旧窗口不会被唤到前台。

    这里改为：先按自有标记属性窗口匹配，再退回标题匹配，最后退回
    FindWindow，命中即投递；并把窗口强拉到前台，确保用户能看到。
    """
    if not IS_WINDOWS or not message_id:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.PostMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        user32.PostMessageW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        user32.IsWindowVisible.restype = ctypes.c_int
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
    except OSError:
        return False

    title_buf = ctypes.create_unicode_buffer(512)
    found: list[int] = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

    def _visit(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            user32.GetWindowTextW(hwnd, title_buf, 512)
            # 标题完全一致，或以我们的标题开头（Qt 可能追加应用名后缀）。
            # 不再用 `title in value`：那会把任何标题里含这几个字的无关窗口
            # 也当成目标，把激活消息投给它。
            value = title_buf.value
            if value == title or value.startswith(title):
                found.append(int(hwnd))
                return 0
        return 1

    try:
        user32.EnumWindows(WNDENUMPROC(_visit), 0)
    except OSError:
        found = []

    if not found:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            found = [int(hwnd)]

    for handle in found:
        if user32.PostMessageW(handle, message_id, 0, 0):
            return True
    return False


def window_message_from_native(message) -> int:
    """从 Qt nativeEvent 的 MSG 指针里取出消息号（失败返回 0）。"""
    if not IS_WINDOWS:
        return 0
    try:
        address = message if isinstance(message, int) else int(message)
        if not address:
            return 0
        msg = ctypes.cast(address, ctypes.POINTER(ctypes.wintypes.MSG)).contents
        return int(msg.message)
    except Exception:
        return 0


WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012


def power_event_from_native(message) -> int | None:
    """从 Qt nativeEvent 的 MSG 指针里取出电源事件类型（wParam）。

    只关心 WM_POWERBROADCAST；其它消息返回 None。
    """
    if not IS_WINDOWS:
        return None
    try:
        address = message if isinstance(message, int) else int(message)
        if not address:
            return None
        msg = ctypes.cast(address, ctypes.POINTER(ctypes.wintypes.MSG)).contents
        if int(msg.message) != WM_POWERBROADCAST:
            return None
        return int(msg.wParam)
    except Exception:
        return None

# ---------------------------------------------------------------- 开机自启 --


def launch_command() -> str:
    """返回用于开机自启的完整命令行。"""
    if getattr(sys, "frozen", False):
        return '"%s" --minimized' % sys.executable
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    exe = windowless if windowless.exists() else python
    script = Path(__file__).resolve().parent.parent / "main.py"
    return '"%s" "%s" --minimized' % (exe, script)


def _normalize_command(command: str) -> str:
    """比较命令行时忽略大小写、引号与多余空白。"""
    return " ".join(str(command).replace('"', " ").lower().split())


def autostart_command() -> str:
    """读取注册表里当前记录的自启命令行；不存在时返回空串。"""
    if not IS_WINDOWS:
        return ""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
        return str(value).strip()
    except OSError:
        return ""


def is_autostart_enabled() -> bool:
    """判断自启项是否指向**当前这个**程序。

    旧实现只看"Run 值非空"，于是绿色版换了目录、或从桌面挪到 Program Files
    之后，注册表里仍留着旧路径：界面显示"已开启"，开机却什么都没启动。
    这里改为和当前 launch_command() 比对，路径变了就算未开启，
    由 _sync_autostart_setting() 负责按新路径重写。
    """
    stored = autostart_command()
    if not stored:
        return False
    return _normalize_command(stored) == _normalize_command(launch_command())


def set_autostart(enabled: bool) -> bool:
    """写入/删除注册表 Run 项，返回是否成功。"""
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        diag.log("写入开机自启项失败: %r" % (exc,))
        return False


# ------------------------------------------------------------------ 关机 --


def _run(args: list[str], timeout: float = 10.0) -> int | None:
    """同步执行命令并返回退出码；无法启动时返回 None。

    注意：这里不使用 DETACHED_PROCESS，而是同步等待 shutdown.exe 退出，
    这样才能拿到真实的返回码——原来的实现不管成败都返回 True，
    是「点了开始却没关机、界面却提示已发出」的直接原因。
    """
    try:
        proc = subprocess.Popen(
            args,
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        diag.log("无法启动命令 %s: %r" % (args[:1], exc))
        return None
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # 挂起的子进程既不返回码也不退出：杀掉它，否则会留下孤儿进程，
        # 而且我们永远等不到结果。
        diag.log("命令超时 %ss，已终止: %s" % (timeout, " ".join(args)))
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass
        return None


def shutdown_exe() -> str:
    """返回 shutdown.exe 的绝对路径。

    用 System32 下的绝对路径而不是裸的 "shutdown"，避免两种失败：
      1. PATH 被裁剪或损坏时找不到命令（此时只能退回 API 兜底）；
      2. PATH 里靠前的位置放了同名的恶意/异常程序被我们执行——
         本程序会以当前用户身份发起关机，值得做这一步加固。
    """
    if IS_WINDOWS:
        root = os.environ.get("SystemRoot") or r"C:\Windows"
        candidate = Path(root) / "System32" / "shutdown.exe"
        if candidate.exists():
            return str(candidate)
    return "shutdown"


# shutdown.exe 的返回码：0 = 指令已排入队列；
# 1190 = "已有排队的关机"，说明目标已经达成，同样应视为成功。
# 若把它当成失败，后面的 /f 重试与 ExitWindowsEx 兜底会立刻强制关机，
# 反而跳过用户设置的宽限时间。
SHUTDOWN_OK_CODES = (0, 1190)


def shutdown_args(force: bool = False, grace: int = 3) -> list[str]:
    """构造 shutdown.exe 参数。"""
    args = [shutdown_exe(), "/s"]
    if force:
        args.append("/f")
    args += ["/t", str(max(0, int(grace))), "/c", SHUTDOWN_COMMENT]
    return args


def _safe_print(text: str) -> None:
    """windowed（--noconsole）打包下 stdout 为 None，直接 print 会抛异常。"""
    try:
        if sys.stdout is not None:
            print(text)
    except Exception:
        pass


def dry_run() -> bool:
    """开发用安全开关：设置 VRSHUTDOWN_DRY_RUN=1 后不会真的关机。"""
    return os.environ.get("VRSHUTDOWN_DRY_RUN", "").strip() == "1"


def restart_args(force: bool = False, grace: int = 3) -> list[str]:
    """构造重启参数（备用能力）。"""
    args = [shutdown_exe(), "/r"]
    if force:
        args.append("/f")
    args += ["/t", str(max(0, int(grace))), "/c", SHUTDOWN_COMMENT]
    return args


class ShutdownOutcome(NamedTuple):
    """一次关机尝试的结果。

    ok        —— 关机是否确实已经排入系统队列
    escalated —— 用户选的是「正常关机」，但因被程序阻止而升级为强制
    detail    —— 便于展示与排查的一句话说明
    """

    ok: bool
    escalated: bool
    detail: str


def run_shutdown(force: bool = False, grace: int = 3) -> ShutdownOutcome:
    """发出关机指令。grace 为留给用户/程序自身的宽限秒数。

    实现要点：
      1. 优先使用系统自带 shutdown.exe，并检查**真实返回码**；
      2. 「正常关机」被程序阻止时，会带 /f 重试一次（这是 1.1.0 修的核心
         问题），但**结果会如实上报**——escalated=True，界面必须告诉用户
         已经变成强制关机，而不是悄悄强杀别人的未保存文档；
      3. shutdown.exe 完全不可用时，退回系统 API，并保留可取消的倒计时。
    """
    if not IS_WINDOWS:
        return ShutdownOutcome(False, False, "当前系统不支持关机操作")
    if dry_run():
        _safe_print("[dry-run] 跳过关机命令: %s" % " ".join(shutdown_args(force, grace)))
        return ShutdownOutcome(True, False, "dry-run：未真正执行关机")

    # 第一发：按用户设定执行
    code = _run(shutdown_args(force, grace))
    if code in SHUTDOWN_OK_CODES:
        return ShutdownOutcome(True, False, "已按设定排入关机队列")

    # 第二发：正常关机失败时，带 /f 再试一次（强制结束阻止关机的进程）。
    escalated = False
    effective_force = force
    if not force:
        escalated = True
        effective_force = True
        force_code = _run(shutdown_args(True, grace))
        if force_code in SHUTDOWN_OK_CODES:
            return ShutdownOutcome(True, True, "正常关机被阻止，已升级为强制关机")

    # 最后兜底：直接调用系统 API（带 timeout，仍可被 shutdown /a 取消）
    if initiate_shutdown_api(force=effective_force, grace=grace):
        detail = "shutdown.exe 不可用，已改用系统 API 关机"
        if effective_force:
            detail += "（强制）"
        return ShutdownOutcome(True, escalated, detail)

    diag.log("关机失败: shutdown.exe 返回 %r，API 兜底也失败" % (code,))
    return ShutdownOutcome(False, False, "系统拒绝了关机指令")


def abort_shutdown() -> bool:
    """取消一个已经排入 Windows 队列的关机。成功返回 True。"""
    if not IS_WINDOWS or dry_run():
        return False
    return _run([shutdown_exe(), "/a"]) == 0


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_ulong), ("HighPart", ctypes.c_long)]


class _LUIDAndAttributes(ctypes.Structure):
    _fields_ = [("Luid", _LUID), ("Attributes", ctypes.c_ulong)]


class _TokenPrivileges(ctypes.Structure):
    _fields_ = [("PrivilegeCount", ctypes.c_ulong), ("Privileges", _LUIDAndAttributes * 1)]


def _enable_shutdown_privilege() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return False

    TOKEN_ADJUST_PRIVILEGES = 0x0020
    TOKEN_QUERY = 0x0008
    SE_PRIVILEGE_ENABLED = 0x00000002
    ERROR_NOT_ALL_ASSIGNED = 1300

    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    advapi32.OpenProcessToken.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.OpenProcessToken.restype = ctypes.c_int
    advapi32.LookupPrivilegeValueW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p]
    advapi32.LookupPrivilegeValueW.restype = ctypes.c_int
    advapi32.AdjustTokenPrivileges.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    advapi32.AdjustTokenPrivileges.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    token = ctypes.c_void_p()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
        ctypes.byref(token),
    ):
        return False
    try:
        luid = _LUID()
        if not advapi32.LookupPrivilegeValueW(None, "SeShutdownPrivilege", ctypes.byref(luid)):
            return False
        privileges = _TokenPrivileges(
            1, (_LUIDAndAttributes * 1)(_LUIDAndAttributes(luid, SE_PRIVILEGE_ENABLED))
        )
        ctypes.set_last_error(0)
        if not advapi32.AdjustTokenPrivileges(
            token, False, ctypes.byref(privileges), 0, None, None
        ):
            return False
        return ctypes.get_last_error() != ERROR_NOT_ALL_ASSIGNED
    finally:
        if token:
            kernel32.CloseHandle(token)


def initiate_shutdown_api(force: bool = False, grace: int = 3) -> bool:
    """用 Windows API 关机（shutdown.exe 不可用时的兜底方案）。

    旧实现调用 ExitWindowsEx，会**立刻**关机：既不遵守用户设置的宽限时间，
    也没有任何可以反悔的窗口。这里改用 InitiateSystemShutdownExW，
    把 grace 作为系统倒计时传进去——即使走到兜底路径，用户依然能用
    「取消定时 / shutdown /a」救回来。
    """
    if not IS_WINDOWS:
        return False
    if not _enable_shutdown_privilege():
        diag.log("启用 SeShutdownPrivilege 失败，无法调用关机 API")
        return False
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    except OSError:
        return False

    advapi32.InitiateSystemShutdownExW.argtypes = [
        ctypes.c_wchar_p,  # 目标机器（None = 本机）
        ctypes.c_wchar_p,  # 关机提示文本
        ctypes.c_uint,  # 倒计时秒数
        ctypes.c_int,  # 是否强制关闭应用程序
        ctypes.c_int,  # 关机后是否重启
        ctypes.c_ulong,  # 关机原因代码
    ]
    advapi32.InitiateSystemShutdownExW.restype = ctypes.c_int

    timeout = max(0, int(grace))
    ok = advapi32.InitiateSystemShutdownExW(
        None,
        SHUTDOWN_COMMENT,
        timeout,
        1 if force else 0,
        0,
        0,
    )
    if not ok:
        diag.log(
            "InitiateSystemShutdownExW 失败 (force=%s, timeout=%s)" % (force, timeout)
        )
    return bool(ok)


# ---------------------------------------------------------------- 提示音 --


def _sound_worker(sound_file: str) -> None:
    """实际的发声逻辑，跑在后台线程里，不阻塞界面。"""
    try:
        import winsound
    except Exception:
        return

    # 优先播放用户自定义的 WAV；文件不存在 / 格式不对时回退到内置蜂鸣。
    if sound_file:
        try:
            winsound.PlaySound(
                sound_file,
                winsound.SND_FILENAME | winsound.SND_NODEFAULT,
            )
            return
        except Exception:
            pass

    try:
        for freq, dur in ((880, 240), (1175, 240), (880, 380)):
            winsound.Beep(freq, dur)
    except Exception:
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass


def play_alert_sound(sound_file: str = "") -> None:
    """后台线程播放提示音，不阻塞界面。"""
    threading.Thread(
        target=_sound_worker, args=(sound_file,), daemon=True, name="alert-sound"
    ).start()


# ------------------------------------------------------------ 阻止睡眠(S0) --


def prevent_sleep() -> None:
    """倒计时期间阻止系统进入睡眠 / 现代待机（S0）。

    SetThreadExecutionState 作用于**调用它的线程**，且 ES_CONTINUOUS 会一直
    生效到该线程再次以 ES_CONTINUOUS 单独调用为止。因此本函数必须在主线程
    里调用（app.py 的 start_task 由按钮点击触发，正好在主线程）。

    若机器仍被其他因素（电源计划、硬件、组策略）强制进入 S0，这层防护会失效，
    所以 README 同时建议用户把电源计划设为「从不睡眠」作为双重保障。
    """
    if not IS_WINDOWS:
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetThreadExecutionState.argtypes = [ctypes.c_ulong]
        kernel32.SetThreadExecutionState.restype = ctypes.c_ulong
        kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except OSError as exc:
        diag.log("阻止系统睡眠失败: %r" % (exc,))


def allow_sleep() -> None:
    """撤销阻止睡眠，恢复系统默认电源策略（同样必须在主线程调用）。"""
    if not IS_WINDOWS:
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetThreadExecutionState.argtypes = [ctypes.c_ulong]
        kernel32.SetThreadExecutionState.restype = ctypes.c_ulong
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except OSError:
        pass
