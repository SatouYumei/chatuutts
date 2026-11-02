"""同时只运行一个窗口。再次启动时把已有窗口拉到前面。"""

import ctypes
import ctypes.wintypes
import time

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)

_MUTEX_NAME = "Local\\ChatuuTTS.SingleInstance"
_EVENT_NAME = "Local\\ChatuuTTS.Activate"
_WINDOW_TITLE = "CHATUUTTS"
_ERROR_ALREADY_EXISTS = 183
_WAIT_OBJECT_0 = 0
_SW_SHOW = 5
_SW_RESTORE = 9
_HWND_TOPMOST = ctypes.c_void_p(-1)
_HWND_NOTOPMOST = ctypes.c_void_p(-2)
_SWP_FLAGS = 0x0001 | 0x0002 | 0x0040
_WS_EX_TOPMOST = 0x00000008

_mutex = None
_event = None

_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
_kernel32.CreateMutexW.restype = ctypes.c_void_p
_kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]
_kernel32.CreateEventW.restype = ctypes.c_void_p
_kernel32.OpenEventW.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_wchar_p]
_kernel32.OpenEventW.restype = ctypes.c_void_p
_kernel32.SetEvent.argtypes = [ctypes.c_void_p]
_kernel32.SetEvent.restype = ctypes.c_bool
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_kernel32.CloseHandle.restype = ctypes.c_bool
_kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
_kernel32.WaitForSingleObject.restype = ctypes.c_uint
_kernel32.GetCurrentThreadId.restype = ctypes.c_uint

_user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_user32.EnumWindows.restype = ctypes.c_bool
_user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
_user32.IsWindowVisible.restype = ctypes.c_bool
_user32.IsIconic.argtypes = [ctypes.c_void_p]
_user32.IsIconic.restype = ctypes.c_bool
_user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.ShowWindow.restype = ctypes.c_bool
_user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_user32.GetWindowThreadProcessId.restype = ctypes.c_uint
_user32.AllowSetForegroundWindow.argtypes = [ctypes.c_uint]
_user32.AllowSetForegroundWindow.restype = ctypes.c_bool
_user32.GetForegroundWindow.restype = ctypes.c_void_p
_user32.AttachThreadInput.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_bool]
_user32.AttachThreadInput.restype = ctypes.c_bool
_user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
_user32.SetForegroundWindow.restype = ctypes.c_bool
_user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
_user32.BringWindowToTop.restype = ctypes.c_bool
_user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowPos.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
_user32.SetWindowPos.restype = ctypes.c_bool
_user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_user32.GetWindowRect.restype = ctypes.c_bool


def claim_single_instance():
    """拿到单实例锁才继续启动。拿不到就唤醒已有窗口并返回 False。"""
    global _mutex, _event
    ctypes.set_last_error(0)
    _mutex = _kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    already_running = ctypes.get_last_error() == _ERROR_ALREADY_EXISTS
    if already_running:
        try:
            _wake_existing()
        except Exception:
            pass
        if _mutex:
            _kernel32.CloseHandle(_mutex)
            _mutex = None
        return False
    _event = _kernel32.CreateEventW(None, False, False, _EVENT_NAME)
    return True


def watch_activation(window):
    """已有实例收到再次启动的信号后，把自己拉到前面。"""
    if not _event:
        return

    def poll():
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return
        if _kernel32.WaitForSingleObject(_event, 0) == _WAIT_OBJECT_0:
            _focus_window(window)
        window.after(150, poll)

    window.after(150, poll)


def _wake_existing():
    event = _kernel32.OpenEventW(0x00100000 | 0x0002, False, _EVENT_NAME)
    hwnd = _wait_for_window()
    if hwnd:
        pid = ctypes.c_uint()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            _user32.AllowSetForegroundWindow(pid.value)
    if event:
        _kernel32.SetEvent(event)
        _kernel32.CloseHandle(event)
    if hwnd:
        bring_to_front(hwnd)


def _wait_for_window():
    for _ in range(30):
        hwnd = _find_main_window()
        if hwnd:
            return hwnd
        time.sleep(0.1)
    return None


def _find_main_window():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visit(hwnd, _lparam):
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value != _WINDOW_TITLE or not _user32.IsWindowVisible(hwnd):
            return True
        rect = ctypes.wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        found.append((area, hwnd))
        return True

    _user32.EnumWindows(visit, 0)
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return found[-1][1]


def _focus_window(window):
    try:
        if window.state() == "withdrawn":
            window.deiconify()
        window.lift()
        window.focus_force()
    except Exception:
        pass
    try:
        from lib.widgets import top_hwnd

        bring_to_front(top_hwnd(window))
        for dialog in list(getattr(window, "_dialogs", [])):
            try:
                dialog.lift()
                bring_to_front(top_hwnd(dialog))
            except Exception:
                pass
    except Exception:
        pass


def bring_to_front(hwnd):
    if not hwnd:
        return
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, _SW_RESTORE)
    else:
        _user32.ShowWindow(hwnd, _SW_SHOW)

    foreground = _user32.GetForegroundWindow()
    current_thread = _kernel32.GetCurrentThreadId()
    foreground_thread = _user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    target_thread = _user32.GetWindowThreadProcessId(hwnd, None)
    attached_foreground = False
    attached_target = False
    if foreground_thread and foreground_thread != current_thread:
        attached_foreground = bool(_user32.AttachThreadInput(foreground_thread, current_thread, True))
    if target_thread and target_thread != current_thread:
        attached_target = bool(_user32.AttachThreadInput(current_thread, target_thread, True))

    style = _user32.GetWindowLongPtrW(hwnd, -20) or 0
    was_topmost = bool(int(style) & _WS_EX_TOPMOST)
    _user32.SetForegroundWindow(hwnd)
    _user32.BringWindowToTop(hwnd)
    _user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_FLAGS)
    if not was_topmost:
        _user32.SetWindowPos(hwnd, _HWND_NOTOPMOST, 0, 0, 0, 0, _SWP_FLAGS)

    if attached_target:
        _user32.AttachThreadInput(current_thread, target_thread, False)
    if attached_foreground:
        _user32.AttachThreadInput(foreground_thread, current_thread, False)
