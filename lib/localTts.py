"""离线合成：用 sherpa-onnx 跑本地 Kokoro 模型，不联网。"""

import os
import threading
from pathlib import Path

from lib.paths import app_dir, resource_dir

MODEL_NAME = "kokoro-int8-multi-lang-v1_1"
LOCAL_PREFIX = "local:"

_engine = None
_engine_lock = threading.Lock()
_generate_lock = threading.Lock()


def is_local_voice(voice_id):
    return str(voice_id or "").startswith(LOCAL_PREFIX)


def speaker_id(voice_id):
    return int(str(voice_id)[len(LOCAL_PREFIX):])


def model_dir():
    """先找程序旁边的 models，再找安装包里带的。"""
    for root in (app_dir(), resource_dir()):
        path = root / "models" / MODEL_NAME
        if (path / "model.int8.onnx").is_file():
            return path
    return None


def model_ready():
    try:
        import sherpa_onnx  # noqa: F401
    except Exception:
        return False
    return model_dir() is not None


def _load():
    import sherpa_onnx

    model = model_dir()
    if model is None:
        raise RuntimeError("没有找到本地语音模型")
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=str(model / "model.int8.onnx"),
                voices=str(model / "voices.bin"),
                tokens=str(model / "tokens.txt"),
                data_dir=str(model / "espeak-ng-data"),
                dict_dir=str(model / "dict"),
                lexicon=f"{model / 'lexicon-us-en.txt'},{model / 'lexicon-zh.txt'}",
            ),
            num_threads=max(1, min(8, (os.cpu_count() or 4) // 2)),
        ),
        rule_fsts=f"{model / 'phone-zh.fst'},{model / 'date-zh.fst'},{model / 'number-zh.fst'}",
        max_num_sentences=1,
    )
    return sherpa_onnx.OfflineTts(config)


def engine():
    """第一次用时才加载模型，大约一两秒。"""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = _load()
        return _engine


def warm_up():
    """后台先把模型读进来，第一句话就不用等加载。"""

    def run():
        try:
            engine()
        except Exception as exc:
            print(f"Local TTS warm-up failed: {exc}")

    threading.Thread(target=run, name="tts-local-warmup", daemon=True).start()


def synthesize(text, config, path):
    """合成到 wav 文件。语速沿用 SPEED 百分比，音量按 VOLUME 缩放。音调和风格本地模型不支持。"""
    import numpy as np
    import sherpa_onnx

    tts = engine()
    speed = max(0.5, 1.0 + int(getattr(config, "SPEED", 0) or 0) / 100)
    volume = getattr(config, "VOLUME", 100)
    volume = 100 if volume is None else int(volume)
    with _generate_lock:
        audio = tts.generate(text, sid=speaker_id(config.VOICE), speed=speed)
    samples = np.asarray(audio.samples, dtype=np.float32)
    if not samples.size:
        return None
    if volume != 100:
        samples = np.clip(samples * (volume / 100), -1.0, 1.0)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    if not sherpa_onnx.write_wave(str(temporary), samples, audio.sample_rate):
        return None
    try:
        temporary.replace(path)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
    return path
