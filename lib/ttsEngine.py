"""文字转语音：替换、缓存、接口和播放。"""

import copy
import hashlib
import json
import os
import queue
import re
import threading
import time
from pathlib import Path

from lib.localTts import is_local_voice


_playback_queue = queue.Queue()
_stop_playback = threading.Event()
_playback_thread = None
_session = None
_session_lock = threading.Lock()


class _Pending:
    """先占住播放队列里的位置，合成完再填上文件。这样多句话按输入顺序播放。"""

    def __init__(self):
        self.path = None
        self.ready = threading.Event()

    def resolve(self, path):
        self.path = path
        self.ready.set()

    def wait(self):
        while not self.ready.wait(0.1):
            if _stop_playback.is_set():
                return None
        return self.path


def _import_pygame():
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    return pygame


class Config:
    """读取声音、固定搭配和词语替换三个配置。"""

    def __init__(self, *config_path):
        self.WORD_REPLACEMENT = None
        self.FIXED_COLLOCATION = None
        self.API_ENDPOINT = None
        self.BASE_URL = None
        self.FULL_API_URL = None
        self.load(*config_path)

    def load(self, *config_path):
        if len(config_path) < 3:
            raise ValueError("需要声音、固定搭配、词语替换三个配置文件")
        with open(config_path[0], "r", encoding="utf-8") as file:
            data = json.load(file)
        self.__dict__.update(data)
        self.FULL_API_URL = self.BASE_URL + self.API_ENDPOINT
        with open(config_path[1], "r", encoding="utf-8") as file:
            self.FIXED_COLLOCATION = json.loads(file.read())
        with open(config_path[2], "r", encoding="utf-8") as file:
            self.WORD_REPLACEMENT = json.loads(file.read())


def search_fixed_collocation(text, config):
    for collocation in config.FIXED_COLLOCATION:
        if collocation["before"] == text:
            return collocation["after"]
    return text


def re_search_word_replacement(text, replacement):
    try:
        return re.sub(replacement["before"], replacement["after"], text)
    except re.error as exc:
        print(f"Invalid replacement pattern {replacement['before']!r}: {exc}")
        return text


def search_word_replacement(text, config):
    for replacement in config.WORD_REPLACEMENT:
        if replacement.get("re"):
            text = re_search_word_replacement(text, replacement)
        else:
            text = text.replace(replacement["before"], replacement["after"])
    return text


def cache_key(text, config):
    raw = (
        f"{config.VOICE}{config.VOICE_STYLE}{getattr(config, 'VOICE_ROLE', 'Default')}"
        f"{config.SPEED}{config.PITCH}{getattr(config, 'VOLUME', 100)}"
        f"{getattr(config, 'STYLE_DEGREE', 100)}{text}"
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def cache_directory(config):
    return Path(config.STORED_FILEPATH)


def _cached_files(root):
    """在线合成存 mp3，本地合成存 wav。"""
    yield from root.glob("*.mp3")
    yield from root.glob("*.wav")


def cache_size(config):
    """缓存目录里音频的总字节数。"""
    root = cache_directory(config)
    total = 0
    if not root.is_dir():
        return 0
    for path in _cached_files(root):
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total


def format_cache_size(size):
    if size < 1024:
        return f"{int(size)} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024 / 1024 / 1024:.2f} GB"


def clear_cache(config):
    """删掉缓存里的音频。正在播放、删不掉的文件会留下来。"""
    root = cache_directory(config)
    if not root.is_dir():
        return 0
    removed = 0
    for path in list(_cached_files(root)):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def build_ssml(text, config):
    style = str(getattr(config, "VOICE_STYLE", "general") or "general")
    role = str(getattr(config, "VOICE_ROLE", "Default") or "Default")
    degree = int(getattr(config, "STYLE_DEGREE", 100) or 100)
    volume = int(getattr(config, "VOLUME", 100) if getattr(config, "VOLUME", 100) is not None else 100)
    express_open = ""
    express_close = ""
    if style.lower() != "general" or role != "Default":
        attributes = []
        if style.lower() != "general":
            attributes.append(f'style="{style}"')
            attributes.append(f'styledegree="{max(degree, 1) / 100:.2f}"')
        if role != "Default":
            attributes.append(f'role="{role}"')
        express_open = "<mstts:express-as " + " ".join(attributes) + ">"
        express_close = "</mstts:express-as>"
    return (
        '<speak xmlns="http://www.w3.org/2001/10/synthesis" \n'
        '                  xmlns:mstts="http://www.w3.org/2001/mstts" \n'
        '                  xmlns:emo="http://www.w3.org/2009/10/emotionml" \n'
        '                  version="1.0" \n'
        '                  xml:lang="zh-CN">\n'
        '                <voice name="'
        f"{config.VOICE}"
        '">\n                  '
        f"{express_open}"
        '\n                  <prosody rate="'
        f"{config.SPEED}"
        '%" pitch="'
        f"{config.PITCH}"
        '%" volume="'
        f"{volume}"
        '">'
        f"{text}"
        "</prosody>\n                  "
        f"{express_close}"
        "\n                </voice>\n              </speak>"
    )


def build_headers(config):
    return {
        "Output-Format": config.OUTPUT_FORMAT,
        "Content-Type": "application/ssml+xml",
        "FFCafe-Access-Token": config.API_KEY,
        "Voice-Variant": str(config.VOICE).lower(),
    }


def _playback_worker():
    """播放队列中的音频文件。"""
    try:
        pygame = _import_pygame()
    except Exception as exc:
        print(f"Failed to import pygame: {exc}")
        return

    while not _stop_playback.is_set():
        try:
            mp3_file_path = _playback_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        except Exception as exc:
            print(f"Unexpected error in playback worker loop: {exc}")
            time.sleep(0.1)
            continue

        if mp3_file_path is None or _stop_playback.is_set():
            _playback_queue.task_done()
            return

        try:
            if isinstance(mp3_file_path, _Pending):
                mp3_file_path = mp3_file_path.wait()
                if mp3_file_path is None:
                    continue
            file_path = Path(mp3_file_path)
            if not file_path.exists() or not file_path.is_file():
                print(f"Playback Error: File not found or invalid: {file_path}")
                continue
            from lib.audioOutput import ensure_speaker, release_speaker, speaker_outputs_locally, start_virtual

            try:
                if speaker_outputs_locally():
                    if not ensure_speaker(pygame):
                        print("Failed to initialize pygame mixer.")
                        continue
                    print(f"Playing: {file_path}")
                    pygame.mixer.music.load(str(file_path))
                    pygame.mixer.music.play()
                    start_virtual(file_path)
                    while not _stop_playback.is_set():
                        try:
                            busy = pygame.mixer.music.get_busy()
                        except pygame.error:
                            break
                        if not busy:
                            break
                        time.sleep(0.1)
                    if _stop_playback.is_set():
                        pygame.mixer.music.stop()
                        print("Playback stopped by shutdown signal.")
                else:
                    release_speaker(pygame)
                    print(f"Output only: {file_path}")
                    start_virtual(file_path, wait=True)
                print(f"Finished playing: {file_path}")
            except pygame.error as exc:
                print(f"Pygame error playing {file_path}: {exc}")
            except Exception as exc:
                print(f"Unexpected error in playback worker: {exc}")
        finally:
            _playback_queue.task_done()


def start_playback():
    global _playback_thread
    if _playback_thread and _playback_thread.is_alive():
        return
    _stop_playback.clear()
    _playback_thread = threading.Thread(target=_playback_worker, name="tts-playback", daemon=True)
    _playback_thread.start()


def _http_session():
    """复用同一个连接，连续发言时省掉每次重新握手的时间。"""
    global _session
    import requests

    with _session_lock:
        if _session is None:
            _session = requests.Session()
        return _session


def text_to_speech_web_api(text, config):
    """把文本发给 TTS 接口，成功时返回音频字节。"""
    import requests

    ssml = build_ssml(text, config)
    headers = build_headers(config)
    try:
        response = _http_session().post(
            config.FULL_API_URL,
            headers=headers,
            data=ssml.encode("utf-8"),
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        print(f"Request failed: {exc}")
        return None
    if response.status_code == 200:
        return response.content
    detail = (response.text or "")[:500]
    print(f"TTS API Error: {response.status_code} - {detail}")
    return None


def save_audio_to_file(audio_bytes, config, filename):
    """把音频字节保存为 mp3。"""
    if not audio_bytes:
        print("No audio data to save.")
        return None
    path = Path(config.STORED_FILEPATH) / f"{filename}.mp3"
    path.parent.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再改名，中途退出不会留下半截的缓存。
    temporary = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    with open(temporary, "wb") as file:
        file.write(audio_bytes)
    try:
        temporary.replace(path)
    except OSError:
        # 同一句话正在播放、文件被占用时，留着已有的那份。
        try:
            temporary.unlink()
        except OSError:
            pass
    print(f"Audio saved to {path}")
    return path


def play_mp3_file(mp3_file_path):
    """播放指定的 MP3 文件。成功返回 True。"""
    pygame = _import_pygame()
    file_path = Path(mp3_file_path)
    if not file_path.exists() or not file_path.is_file():
        print(f"Error: Path is not a file: {file_path}")
        return False
    from lib.audioOutput import ensure_speaker, release_speaker, speaker_outputs_locally, start_virtual

    try:
        if not speaker_outputs_locally():
            release_speaker(pygame)
            start_virtual(file_path, wait=True)
            return True
        if not ensure_speaker(pygame):
            print("Failed to initialize pygame mixer.")
            return False
        pygame.mixer.music.load(str(file_path))
        pygame.mixer.music.play()
        start_virtual(file_path)
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        print(f"Playback finished: {file_path}")
        return True
    except pygame.error as exc:
        print(f"Pygame error playing {file_path}: {exc}")
        return False
    except Exception as exc:
        print(f"Unexpected error playing {file_path}: {exc}")
        return False


def play_in_background_queued(mp3_path):
    """把音频加入播放队列。"""
    _playback_queue.put(mp3_path)
    print(f"Queued for playback: {mp3_path}")


def cleanup_pygame():
    """关闭 pygame 混音器。"""
    try:
        pygame = _import_pygame()
    except Exception:
        return
    if pygame.mixer.get_init():
        pygame.mixer.quit()


def text_to_speech(text, config, on_status=None):
    # 按下发送时的声音参数为准，合成途中切换档案不影响这一句。
    config = copy.copy(config)
    slot = _Pending()
    play_in_background_queued(slot)

    def target(text, config):
        try:
            text = search_fixed_collocation(text, config)
            text = search_word_replacement(text, config)
            if not text.strip():
                slot.resolve(None)
                return
            hashed = cache_key(text, config)
            local = is_local_voice(config.VOICE)
            cache_file = Path(config.STORED_FILEPATH) / f"{hashed}.{'wav' if local else 'mp3'}"
            if cache_file.is_file() and cache_file.stat().st_size > 0:
                slot.resolve(cache_file)
                return
            if local:
                from lib.localTts import synthesize

                slot.resolve(synthesize(text, config, cache_file))
                if not slot.path and on_status:
                    on_status("本地合成失败")
                return
            audio_data = text_to_speech_web_api(text, config)
            if not audio_data:
                slot.resolve(None)
                if on_status:
                    on_status("合成失败")
                return
            save_audio_to_file(audio_data, config, hashed)
            slot.resolve(cache_file)
        except Exception as exc:
            slot.resolve(None)
            print(f"TTS error: {exc}")
            if on_status:
                on_status(f"合成失败：{exc}")

    threading.Thread(target=target, args=(text, config), daemon=True).start()


def cleanup_tts_engine():
    """停止播放线程并关闭混音器。"""
    from lib.audioOutput import shutdown_output

    _stop_playback.set()
    shutdown_output()
    try:
        _playback_queue.put_nowait(None)
    except Exception:
        pass
    cleanup_pygame()
    if _playback_thread and _playback_thread.is_alive():
        _playback_thread.join(timeout=0.4)
