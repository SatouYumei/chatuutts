"""在本机注册 VB-Audio 虚拟麦克风。

驱动包不放进这个程序。这里只在麦克风不存在时创建设备，并藏起多出来的 16 声道播放端。
录音端的显示名写成 chatuu-tts。没有驱动时打开官方下载页，不代为安装。
"""

import ctypes
import json
import sys
import time
import winreg
from ctypes import wintypes
from pathlib import Path

from lib.paths import app_dir

HARDWARE_ID = "VBAudioVACWDM"
MIC_NAME = "chatuu-tts"
DRIVER_PAGE = "https://vb-audio.com/Cable/"
MISSING_DRIVER = "missing-driver"
FRIENDLY = "{b3f8fa53-0004-438e-9003-51a46e139bfc},6"
DESCRIPTION = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
MEDIA_CLASS = "{4d36e96c-e325-11ce-bfc1-08002be10318}"
RENDER = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
CAPTURE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
MEDIA_ENUM = r"SYSTEM\CurrentControlSet\Enum\ROOT\MEDIA"


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _guid(text):
    value = GUID()
    if ctypes.windll.ole32.CLSIDFromString(text, ctypes.byref(value)) != 0:
        raise RuntimeError(text)
    return value


def _registry_text(value):
    if isinstance(value, bytes):
        for encoding in ("utf-16-le", "utf-8"):
            try:
                text = value.decode(encoding)
            except Exception:
                continue
            if text:
                return text
        return ""
    return str(value or "")


def _is_cable_label(value):
    folded = _registry_text(value).casefold()
    if "16 ch" in folded or "16ch" in folded:
        return False
    return "vb-audio virtual cable" in folded or "vb-audio point" in folded or "vbaudiovacwdm" in folded


def _endpoints(kind):
    found = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, kind)
    except OSError:
        return found
    index = 0
    while True:
        try:
            guid = winreg.EnumKey(root, index)
        except OSError:
            break
        index += 1
        try:
            props = winreg.OpenKey(root, guid + r"\Properties")
            friendly, _typ = winreg.QueryValueEx(props, FRIENDLY)
        except OSError:
            continue
        if not _is_cable_label(friendly):
            continue
        try:
            description, _typ = winreg.QueryValueEx(props, DESCRIPTION)
        except OSError:
            description = ""
        found.append((guid, _registry_text(description)))
    return found


def _our_capture(description):
    folded = _registry_text(description).casefold()
    return "16 ch" not in folded and "16ch" not in folded


def microphone_installed():
    """录音端已经在系统里。"""
    for _guid_text, description in _endpoints(CAPTURE):
        if _our_capture(description):
            return True
    return False


def rename_microphone():
    """把录音端显示名写成 chatuu-tts。只改这一端，播放端保持原名。"""
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CAPTURE)
    except OSError:
        return
    index = 0
    while True:
        try:
            guid = winreg.EnumKey(root, index)
        except OSError:
            break
        index += 1
        try:
            props = winreg.OpenKey(
                root,
                guid + r"\Properties",
                0,
                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
            )
            friendly, _typ = winreg.QueryValueEx(props, FRIENDLY)
            description, _typ = winreg.QueryValueEx(props, DESCRIPTION)
        except OSError:
            continue
        if not _is_cable_label(friendly):
            continue
        if not _our_capture(description) or str(description) == MIC_NAME:
            continue
        try:
            winreg.SetValueEx(props, DESCRIPTION, 0, winreg.REG_SZ, MIC_NAME)
        except OSError:
            pass


def open_driver_download():
    """打开 VB-CABLE 官方下载页。驱动不随本程序安装。"""
    ctypes.windll.shell32.ShellExecuteW(None, "open", DRIVER_PAGE, None, None, 1)


def device_node_exists():
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, MEDIA_ENUM)
    except OSError:
        return False
    index = 0
    while True:
        try:
            name = winreg.EnumKey(root, index)
        except OSError:
            break
        index += 1
        try:
            key = winreg.OpenKey(root, name)
            hardware, _typ = winreg.QueryValueEx(key, "HardwareID")
        except OSError:
            continue
        values = hardware if isinstance(hardware, (list, tuple)) else [hardware]
        if any(str(item).casefold() == HARDWARE_ID.casefold() for item in values):
            return True
    return False


def driver_present():
    """驱动已经装进系统。普通用户也能判断，不必先弹管理员窗口。"""
    if microphone_installed() or device_node_exists():
        return True
    for name in (
        r"C:\Windows\System32\drivers\vbaudio_cable64_win10.sys",
        r"C:\Windows\System32\drivers\vbaudio_cable64arm_win10.sys",
    ):
        if Path(name).is_file():
            return True
    try:
        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\VBAudioVACMME")
        return True
    except OSError:
        return False


def find_driver_inf():
    local = Path.home() / "AppData" / "Local" / "CHATUUTTS" / "vb-cable" / "vbMmeCable64_win10.inf"
    if local.is_file():
        return str(local)
    root = Path(r"C:\Windows\System32\DriverStore\FileRepository")
    matches = sorted(root.glob("vbmmecable64_win10.inf_*\\vbMmeCable64_win10.inf"))
    if matches:
        return str(matches[-1])
    return ""


def _method(ptr, index, *argtypes):
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[index])


def _release(ptr):
    if ptr is None or not getattr(ptr, "value", None):
        return
    _method(ptr, 2)(ptr)


def _policy():
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    policy = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(_guid("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")),
        None,
        1,
        ctypes.byref(_guid("{f8679f50-850a-41cf-9c72-430f290290c8}")),
        ctypes.byref(policy),
    )
    if hr != 0 or not policy.value:
        return None
    return _method(policy, 13, ctypes.c_wchar_p, ctypes.c_int), _method(policy, 14, ctypes.c_wchar_p, ctypes.c_int), policy


def _enumerator():
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    enumerator = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(_guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")),
        None,
        1,
        ctypes.byref(_guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")),
        ctypes.byref(enumerator),
    )
    if hr != 0 or not enumerator.value:
        return None
    return enumerator


def _device_text(device):
    raw = ctypes.c_void_p()
    if _method(device, 5, ctypes.POINTER(ctypes.c_void_p))(device, ctypes.byref(raw)) != 0 or not raw.value:
        return ""
    text = ctypes.wstring_at(raw.value)
    ctypes.windll.ole32.CoTaskMemFree(raw)
    return text or ""


def _default_device_id(enumerator, flow, role):
    device = ctypes.c_void_p()
    result = _method(enumerator, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
        enumerator, flow, role, ctypes.byref(device)
    )
    if result != 0 or not device.value:
        return ""
    text = _device_text(device)
    _release(device)
    return text


def _active_device_ids(enumerator, flow):
    collection = ctypes.c_void_p()
    result = _method(enumerator, 3, ctypes.c_int, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(
        enumerator, flow, 1, ctypes.byref(collection)
    )
    if result != 0 or not collection.value:
        return []
    count = wintypes.UINT()
    _method(collection, 3, ctypes.POINTER(wintypes.UINT))(collection, ctypes.byref(count))
    found = []
    item = _method(collection, 4, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
    for index in range(count.value):
        device = ctypes.c_void_p()
        if item(collection, index, ctypes.byref(device)) != 0 or not device.value:
            continue
        text = _device_text(device)
        _release(device)
        if text:
            found.append(text)
    _release(collection)
    return found


def _endpoint_names(device_id):
    text = str(device_id or "")
    guid_start = text.rfind("{")
    if guid_start < 0:
        return "", ""
    kind = CAPTURE if "{0.0.1." in text else RENDER
    try:
        props = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, kind + "\\" + text[guid_start:] + r"\Properties")
        description, _typ = winreg.QueryValueEx(props, DESCRIPTION)
        friendly, _typ = winreg.QueryValueEx(props, FRIENDLY)
    except OSError:
        return "", ""
    return str(description), str(friendly)


def _is_cable_device(device_id):
    _description, friendly = _endpoint_names(device_id)
    return "vb-audio virtual cable" in friendly.casefold()


def _saved_speaker():
    path = app_dir() / "config" / "ui_state.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    speaker = str(data.get("speaker") or "")
    if speaker in ("", "none"):
        return ""
    return speaker


def _preferred_device(enumerator, flow, saved_label):
    saved = str(saved_label or "").casefold()
    fallback = ""
    for device_id in _active_device_ids(enumerator, flow):
        if _is_cable_device(device_id):
            continue
        description, friendly = _endpoint_names(device_id)
        label = f"{description} ({friendly})".casefold()
        if saved and (saved == label or saved in label or label in saved):
            return device_id
        if not fallback:
            fallback = device_id
    return fallback


def keep_real_defaults(retries=1):
    """虚拟声卡可以出声，但不能抢走系统默认设备。"""
    for attempt in range(max(1, retries)):
        try:
            _restore_defaults_once()
        except Exception:
            pass
        if attempt + 1 < retries:
            time.sleep(0.4)


def _restore_defaults_once():
    enumerator = _enumerator()
    opened = _policy()
    if enumerator is None or opened is None:
        _release(enumerator)
        return
    set_default, _set_visibility, policy = opened
    speaker = _saved_speaker()
    try:
        for flow, saved in ((0, speaker), (1, "")):
            preferred = ""
            for role in (0, 1, 2):
                current = _default_device_id(enumerator, flow, role)
                if not current or not _is_cable_device(current):
                    continue
                if not preferred:
                    preferred = _preferred_device(enumerator, flow, saved)
                if preferred and preferred.casefold() != current.casefold():
                    set_default(policy, preferred, role)
    finally:
        _release(policy)
        _release(enumerator)


def hide_extra_speakers(feed_microphone=False, keep_default=True):
    """16 声道播放端始终藏起。立体声那端保持可见。"""
    del feed_microphone
    stereo = []
    extra = []
    for guid, description in _endpoints(RENDER):
        device_id = "{0.0.0.00000000}." + guid.lower()
        if "16" in description:
            extra.append(device_id)
        else:
            stereo.append(device_id)
    if stereo or extra:
        opened = _policy()
        if opened is not None:
            _set_default, set_visibility, policy = opened
            for device_id in extra:
                set_visibility(policy, device_id, 0)
            for device_id in stereo:
                set_visibility(policy, device_id, 1)
            _release(policy)
    if keep_default:
        keep_real_defaults(retries=4)


def _create_device():
    setupapi = ctypes.windll.setupapi
    class_guid = _guid(MEDIA_CLASS)
    device_set = setupapi.SetupDiCreateDeviceInfoList(ctypes.byref(class_guid), None)
    if not device_set or device_set == ctypes.c_void_p(-1).value:
        raise OSError(f"无法创建设备列表 ({ctypes.get_last_error()})")
    info = SP_DEVINFO_DATA()
    info.cbSize = ctypes.sizeof(info)
    created = setupapi.SetupDiCreateDeviceInfoW(
        device_set,
        "ROOT\\MEDIA",
        ctypes.byref(class_guid),
        "VB-Audio Virtual Cable",
        None,
        1,
        ctypes.byref(info),
    )
    if not created:
        setupapi.SetupDiDestroyDeviceInfoList(device_set)
        raise OSError(f"无法新建麦克风设备 ({ctypes.get_last_error()})")
    hardware = ctypes.create_unicode_buffer(HARDWARE_ID + "\0")
    stored = setupapi.SetupDiSetDeviceRegistryPropertyW(
        device_set,
        ctypes.byref(info),
        1,
        ctypes.cast(hardware, ctypes.c_void_p),
        ctypes.sizeof(hardware),
    )
    if not stored:
        setupapi.SetupDiDestroyDeviceInfoList(device_set)
        raise OSError(f"无法写入设备标识 ({ctypes.get_last_error()})")
    registered = setupapi.SetupDiCallClassInstaller(0x19, device_set, ctypes.byref(info))
    error = ctypes.get_last_error()
    setupapi.SetupDiDestroyDeviceInfoList(device_set)
    if not registered:
        raise OSError(f"无法注册麦克风设备 ({error})")


def _bind_driver(inf_path):
    reboot = wintypes.BOOL(False)
    newdev = ctypes.windll.newdev
    ok = newdev.UpdateDriverForPlugAndPlayDevicesW(None, HARDWARE_ID, inf_path, 0, ctypes.byref(reboot))
    if not ok:
        raise OSError(f"驱动没有绑到麦克风上 ({ctypes.get_last_error()})")


def _prepare_api():
    setupapi = ctypes.windll.setupapi
    setupapi.SetupDiCreateDeviceInfoList.argtypes = [ctypes.POINTER(GUID), wintypes.HWND]
    setupapi.SetupDiCreateDeviceInfoList.restype = ctypes.c_void_p
    setupapi.SetupDiCreateDeviceInfoW.argtypes = [
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(GUID),
        wintypes.LPCWSTR,
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.POINTER(SP_DEVINFO_DATA),
    ]
    setupapi.SetupDiCreateDeviceInfoW.restype = wintypes.BOOL
    setupapi.SetupDiSetDeviceRegistryPropertyW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(SP_DEVINFO_DATA),
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    setupapi.SetupDiSetDeviceRegistryPropertyW.restype = wintypes.BOOL
    setupapi.SetupDiCallClassInstaller.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA)]
    setupapi.SetupDiCallClassInstaller.restype = wintypes.BOOL
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
    newdev = ctypes.windll.newdev
    newdev.UpdateDriverForPlugAndPlayDevicesW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.BOOL),
    ]
    newdev.UpdateDriverForPlugAndPlayDevicesW.restype = wintypes.BOOL


def _finish_installed():
    rename_microphone()
    hide_extra_speakers(feed_microphone=True)


def _cable_ready():
    """驱动节点或录音端已经在，就不要再创建一遍。"""
    return microphone_installed() or device_node_exists() or driver_present()


def register_microphone():
    """给已经提权的进程用。成功返回空字符串。"""
    if _cable_ready():
        _finish_installed()
        return ""
    inf_path = find_driver_inf()
    if not inf_path:
        return MISSING_DRIVER
    _prepare_api()
    try:
        if not device_node_exists():
            _create_device()
        if not microphone_installed():
            _bind_driver(inf_path)
    except OSError as exc:
        return str(exc)
    for _ in range(40):
        if microphone_installed():
            _finish_installed()
            return ""
        time.sleep(0.25)
    return "麦克风注册了，但系统还没有把它列出来。"


def _run_elevated():
    result_path = Path.home() / "AppData" / "Local" / "Temp" / "chatuutts-mic-register.txt"
    try:
        result_path.unlink()
    except OSError:
        pass
    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFO)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    info = SHELLEXECUTEINFO()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040
    info.lpVerb = "runas"
    if getattr(sys, "frozen", False):
        info.lpFile = sys.executable
        info.lpParameters = f'--register-microphone "{result_path}"'
        info.lpDirectory = str(app_dir())
    else:
        info.lpFile = sys.executable
        info.lpParameters = f'"{Path(__file__).resolve()}" "{result_path}"'
        info.lpDirectory = str(Path(__file__).resolve().parents[1])
    info.nShow = 1
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        code = ctypes.get_last_error()
        if code == 1223:
            return "没有同意管理员权限，麦克风没有注册。"
        return f"无法开始注册麦克风 ({code})。"
    kernel32 = ctypes.windll.kernel32
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject(info.hProcess, 120000)
    kernel32.CloseHandle(info.hProcess)
    try:
        text = result_path.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    return "" if text == "ok" else (text or "麦克风注册没有完成。")


def ensure_microphone(on_status=None, elevate=False):
    """打开虚拟麦克风。驱动已安装时不弹管理员窗口。"""
    del on_status
    ready = driver_present()
    if ready:
        try:
            rename_microphone()
            hide_extra_speakers(feed_microphone=True, keep_default=False)
        except Exception:
            pass
        return ""
    if not elevate or not find_driver_inf():
        return MISSING_DRIVER
    return _run_elevated()


def main():
    message = register_microphone() or "ok"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(message, encoding="utf-8")
    return 0 if message == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
