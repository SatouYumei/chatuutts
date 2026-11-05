"""命名声音配置和界面状态。"""

import json
import uuid
from pathlib import Path


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(path)


def _fallback_from_config(config):
    volume = getattr(config, "VOLUME", 100)
    degree = getattr(config, "STYLE_DEGREE", 100)
    return {
        "VOICE": getattr(config, "VOICE", "zh-CN-XiaomoNeural"),
        "VOICE_STYLE": getattr(config, "VOICE_STYLE", "calm"),
        "VOICE_ROLE": str(getattr(config, "VOICE_ROLE", "Default") or "Default"),
        "SPEED": int(getattr(config, "SPEED", 0) or 0),
        "PITCH": int(getattr(config, "PITCH", 0) or 0),
        "VOLUME": 100 if volume is None else int(volume),
        "STYLE_DEGREE": 100 if degree is None else int(degree),
    }


def normalize_profile(profile, fallback):
    source = profile or {}
    volume = source.get("VOLUME", fallback["VOLUME"])
    degree = source.get("STYLE_DEGREE", fallback["STYLE_DEGREE"])
    return {
        "id": str(source.get("id") or uuid.uuid4().hex[:12]),
        "name": str(source.get("name") or "未命名").strip() or "未命名",
        "VOICE": source.get("VOICE") or fallback["VOICE"],
        "VOICE_STYLE": source.get("VOICE_STYLE") or fallback["VOICE_STYLE"],
        "VOICE_ROLE": str(source.get("VOICE_ROLE") or fallback.get("VOICE_ROLE") or "Default"),
        "SPEED": int(source.get("SPEED", fallback["SPEED"])),
        "PITCH": int(source.get("PITCH", fallback["PITCH"])),
        "VOLUME": int(fallback["VOLUME"] if volume is None else volume),
        "STYLE_DEGREE": int(fallback["STYLE_DEGREE"] if degree is None else degree),
    }


def _default_profiles(config):
    fallback = _fallback_from_config(config)
    profile = normalize_profile({"name": "默认", **fallback}, fallback)
    return {"active_id": profile["id"], "profiles": [profile]}


def load_profiles(path, config):
    path = Path(path)
    fallback = _fallback_from_config(config)
    if not path.exists():
        data = _default_profiles(config)
        _write_json(path, data)
        return data
    with open(path, "r", encoding="utf-8") as file:
        raw = json.load(file)
    profiles = [normalize_profile(item, fallback) for item in raw.get("profiles", []) if isinstance(item, dict)]
    if not profiles:
        data = _default_profiles(config)
        _write_json(path, data)
        return data
    active_id = raw.get("active_id")
    if active_id not in {item["id"] for item in profiles}:
        active_id = profiles[0]["id"]
    return {"active_id": active_id, "profiles": profiles}


def save_profiles(path, data):
    _write_json(path, data)


def active_profile(data):
    for profile in data["profiles"]:
        if profile["id"] == data["active_id"]:
            return profile
    data["active_id"] = data["profiles"][0]["id"]
    return data["profiles"][0]


def apply_profile_to_config(config, profile):
    config.VOICE = profile["VOICE"]
    config.VOICE_STYLE = profile["VOICE_STYLE"]
    config.VOICE_ROLE = profile.get("VOICE_ROLE") or "Default"
    config.SPEED = int(profile["SPEED"])
    config.PITCH = int(profile["PITCH"])
    config.VOLUME = int(profile.get("VOLUME", 100))
    config.STYLE_DEGREE = int(profile.get("STYLE_DEGREE", 100))


def reconcile_active(data, config):
    """声音文件里的当前参数优先，用来接住直接改 json 的情况。"""
    profile = active_profile(data)
    current = _fallback_from_config(config)
    changed = any(profile[key] != current[key] for key in current)
    if changed:
        profile.update(current)
    apply_profile_to_config(config, profile)
    return changed


def sync_sound_model(path, profile):
    path = Path(path)
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    data["VOICE"] = profile["VOICE"]
    data["VOICE_STYLE"] = profile["VOICE_STYLE"]
    data["VOICE_ROLE"] = profile.get("VOICE_ROLE") or "Default"
    data["SPEED"] = int(profile["SPEED"])
    data["PITCH"] = int(profile["PITCH"])
    data["VOLUME"] = int(profile.get("VOLUME", 100))
    data["STYLE_DEGREE"] = int(profile.get("STYLE_DEGREE", 100))
    _write_json(path, data)


DEFAULT_UI = {
    "theme": "dark",
    "topmost": False,
    "hotkeys_enabled": False,
    "mode": "compact",
    "x": None,
    "y": None,
    "speaker": "",
    "virtual_mic": False,
    "virtual_mic_device": "",
    "check_updates": True,
    "skipped_version": "",
}


def load_ui(path):
    path = Path(path)
    if not path.exists():
        data = dict(DEFAULT_UI)
        _write_json(path, data)
        return data
    with open(path, "r", encoding="utf-8") as file:
        raw = json.load(file)
    data = dict(DEFAULT_UI)
    if isinstance(raw, dict):
        data.update({key: raw.get(key, value) for key, value in DEFAULT_UI.items()})
    if data["mode"] not in ("compact", "expanded"):
        data["mode"] = "compact"
    data["speaker"] = str(data.get("speaker") or "")
    data["virtual_mic_device"] = str(data.get("virtual_mic_device") or "")
    data["virtual_mic"] = bool(data.get("virtual_mic"))
    data["check_updates"] = bool(data.get("check_updates"))
    data["skipped_version"] = str(data.get("skipped_version") or "")
    return data


def save_ui(path, data):
    payload = dict(DEFAULT_UI)
    payload.update(data)
    _write_json(path, payload)
