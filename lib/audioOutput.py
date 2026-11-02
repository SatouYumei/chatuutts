"""扬声器播放，以及把同一段语音送到虚拟麦克风。"""

import os
import threading


_state_lock = threading.Lock()
_mixer_lock = threading.Lock()
_stream_lock = threading.Lock()
_speaker = ""
_virtual_enabled = False
_virtual_device = ""
_reopen = False
_virtual_generation = 0
_active_stream = None
SILENT_SPEAKER = "none"


def _is_cable_name(name):
    """VB-CABLE 的播放端或录音端。16 声道那端不算。"""
    folded = str(name or "").casefold()
    if "16 ch" in folded or "16ch" in folded:
        return False
    return (
        "vb-audio virtual cable" in folded
        or "vb-audio point" in folded
        or "chatuu-tts" in folded
        or "cable output" in folded
        or "cable input" in folded
    )


def _is_new_cable_render(name):
    """虚拟麦克风要写入的那一端播放设备。"""
    folded = str(name or "").casefold()
    if not _is_cable_name(name):
        return False
    return "routist" not in folded


def _is_new_cable_capture(name):
    """其他软件里要选的新麦克风。"""
    return _is_cable_name(name)


def _import_pygame():
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    return pygame


def _wasapi_names(want_output):
    import sounddevice as sd

    hostapis = sd.query_hostapis()
    names = []
    seen = set()
    for device in sd.query_devices():
        channels = device["max_output_channels"] if want_output else device["max_input_channels"]
        if int(channels) < 1:
            continue
        host = str(hostapis[int(device["hostapi"])]["name"]).upper()
        if "WASAPI" not in host:
            continue
        name = str(device["name"])
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def list_output_names():
    """播放设备。不碰 pygame，避免卡住界面。"""
    return _wasapi_names(True)


def list_capture_names():
    """麦克风设备。"""
    return _wasapi_names(False)


def refresh_audio_devices():
    """声卡刚显示或刚注册时，PortAudio 会留着旧列表。先关掉再打开。"""
    import sounddevice as sd

    try:
        sd._terminate()
    except Exception:
        pass
    sd._initialize()


def find_new_microphone(outputs=None, captures=None):
    """返回新麦克风的播放端和录音端。没有注册时两个都是空字符串。"""
    if outputs is None:
        outputs = list_output_names()
    if captures is None:
        captures = list_capture_names()
    render = next((name for name in outputs if _is_new_cable_render(name)), "")
    capture = next((name for name in captures if _is_new_cable_capture(name)), "")
    return render, capture


def virtual_backend_ready():
    try:
        import miniaudio  # noqa: F401
        import sounddevice  # noqa: F401
    except Exception:
        return False
    return True


def speaker_outputs_locally():
    with _state_lock:
        return _speaker != SILENT_SPEAKER


def configure_output(speaker, virtual_enabled, virtual_device):
    """记住扬声器和虚拟麦克风。下一次播放时换扬声器。"""
    global _speaker, _virtual_enabled, _virtual_device, _reopen, _virtual_generation
    speaker = speaker or ""
    virtual_device = virtual_device or ""
    if not _is_new_cable_render(virtual_device):
        virtual_enabled = False
        virtual_device = ""
    with _state_lock:
        if speaker != _speaker:
            _reopen = True
        _speaker = speaker
        _virtual_enabled = bool(virtual_enabled)
        _virtual_device = virtual_device
        _virtual_generation += 1


def ensure_speaker(pygame):
    """按当前选择打开扬声器。打不开选定设备时退回系统默认。"""
    global _reopen
    with _state_lock:
        reopen = _reopen
        name = _speaker
        if reopen:
            _reopen = False
    if name == SILENT_SPEAKER:
        return True
    with _mixer_lock:
        if pygame.mixer.get_init() is not None and not reopen:
            return True
        if pygame.mixer.get_init() is not None:
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                pass
            pygame.mixer.quit()
        return _open_mixer(pygame, name)


def start_virtual(path, wait=False):
    """把正在播放的文件再送一份到虚拟麦克风。"""
    global _virtual_generation
    with _state_lock:
        if not _virtual_enabled or not _virtual_device:
            return
        device = _virtual_device
        speaker = _speaker
        _virtual_generation += 1
        generation = _virtual_generation
    if not _is_new_cable_render(device) or _same_output(speaker, device):
        return
    finished = threading.Event()
    threading.Thread(
        target=_stream_file,
        args=(str(path), device, generation, finished),
        name="tts-virtual-mic",
        daemon=True,
    ).start()
    if wait:
        finished.wait()


def release_speaker(pygame):
    """停掉本机扬声器，避免切到「不播放」后还占着设备。"""
    with _mixer_lock:
        if pygame.mixer.get_init() is None:
            return
        try:
            pygame.mixer.music.stop()
        except pygame.error:
            pass
        pygame.mixer.quit()


def shutdown_output():
    global _virtual_generation
    with _state_lock:
        _virtual_generation += 1
    _abort_virtual_stream()


def _open_mixer(pygame, name):
    kwargs = {"frequency": 22050, "size": -16, "channels": 2, "buffer": 512}
    if name:
        kwargs["devicename"] = name
    try:
        pygame.mixer.init(**kwargs)
        return True
    except pygame.error as exc:
        print(f"Speaker init failed ({name or 'default'}): {exc}")
        if not name:
            return False
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        return True
    except pygame.error as exc:
        print(f"Speaker init failed (default): {exc}")
        return False


def _same_output(speaker, virtual):
    if speaker == SILENT_SPEAKER:
        return False
    if not speaker:
        speaker = _default_output_name()
    if not speaker or not virtual:
        return False
    left = speaker.casefold()
    right = virtual.casefold()
    return left == right or left in right or right in left


def _default_output_name():
    try:
        import sounddevice as sd

        device = sd.query_devices(kind="output")
    except Exception:
        return ""
    if isinstance(device, dict):
        return str(device.get("name") or "")
    return ""


def _output_index(name):
    import sounddevice as sd

    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    target = str(name).casefold()
    matches = []
    for index, device in enumerate(devices):
        if int(device["max_output_channels"]) < 1:
            continue
        label = str(device["name"])
        folded = label.casefold()
        if folded == target or target in folded or folded in target:
            host = str(hostapis[int(device["hostapi"])]["name"]).upper()
            matches.append((0 if "WASAPI" in host else 1, index))
    if not matches:
        return None
    matches.sort()
    return matches[0][1]


def _abort_virtual_stream():
    with _stream_lock:
        stream = _active_stream
    if stream is None:
        return
    try:
        stream.abort()
    except Exception:
        pass


def _keep_real_defaults():
    try:
        from lib.virtualCable import keep_real_defaults

        keep_real_defaults(retries=4)
    except Exception:
        pass


def _stream_file(path, device_name, generation, finished=None):
    global _active_stream
    mine = None
    try:
        import miniaudio
        import sounddevice as sd

        index = _output_index(device_name)
        if index is None:
            print(f"Virtual mic device not found: {device_name}")
            return
        info = sd.query_devices(index)
        sample_rate = int(info.get("default_samplerate") or 44100)
        decoded = miniaudio.decode_file(
            path,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=2,
            sample_rate=sample_rate,
        )
        pcm = decoded.samples.tobytes()
        frame_bytes = decoded.nchannels * 2
        chunk_bytes = max(frame_bytes, int(decoded.sample_rate * 0.1) * frame_bytes)
        mine = sd.RawOutputStream(
            samplerate=decoded.sample_rate,
            channels=decoded.nchannels,
            dtype="int16",
            device=index,
            latency="low",
        )
        with _state_lock:
            still_current = generation == _virtual_generation
        if not still_current:
            return
        with _stream_lock:
            _active_stream = mine
        mine.start()
        threading.Thread(target=_keep_real_defaults, name="tts-keep-default", daemon=True).start()
        print(f"Virtual mic: {device_name}")
        offset = 0
        while offset < len(pcm):
            with _state_lock:
                if generation != _virtual_generation:
                    break
            end = min(len(pcm), offset + chunk_bytes)
            mine.write(pcm[offset:end])
            offset = end
    except Exception as exc:
        print(f"Virtual mic playback failed: {exc}")
    finally:
        with _stream_lock:
            if _active_stream is mine:
                _active_stream = None
        if mine is not None:
            try:
                mine.stop()
                mine.close()
            except Exception:
                pass
        if finished is not None:
            finished.set()
