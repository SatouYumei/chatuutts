"""CHATUUTTS 入口。"""

import ctypes
import shutil
import sys
import traceback
from pathlib import Path

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ChatuuTTS.App")
except Exception:
    pass

from lib.paths import app_dir, resource_dir
from lib.singleInstance import claim_single_instance


def _register_from_flag():
    if "--register-microphone" not in sys.argv:
        return False
    from lib.virtualCable import main as register_main

    index = sys.argv.index("--register-microphone")
    result = sys.argv[index + 1] if index + 1 < len(sys.argv) else ""
    sys.argv = [sys.argv[0], result]
    sys.exit(register_main())


def ensure_config(root):
    """安装目录里还没有配置时，从安装包里的模板复制一份。不覆盖已经有的。"""
    template = resource_dir() / "config"
    target = root / "config"
    if not template.is_dir() or template.resolve() == target.resolve():
        target.mkdir(parents=True, exist_ok=True)
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in template.iterdir():
        if not item.is_file() or item.name.endswith(".example.json"):
            continue
        dest = target / item.name
        if dest.exists():
            continue
        shutil.copy2(item, dest)


def build():
    from lib.globalHotkeyManager import GlobalHotkeyManager
    from lib.mainWindow import ChatUUTTSApp
    from lib.profiles import load_profiles, load_ui, reconcile_active, save_profiles
    from lib.ttsEngine import Config, start_playback, text_to_speech

    root = app_dir()
    ensure_config(root)
    config = Config(
        root / "config" / "sound_model.json",
        root / "config" / "fixed_collocation.json",
        root / "config" / "word_replacement.json",
    )
    stored = Path(config.STORED_FILEPATH)
    if not stored.is_absolute():
        config.STORED_FILEPATH = str((root / stored).resolve())
    profile_path = root / "config" / "voice_profiles.json"
    profiles = load_profiles(profile_path, config)
    if reconcile_active(profiles, config):
        save_profiles(profile_path, profiles)
    ui = load_ui(root / "config" / "ui_state.json")
    hotkeys = GlobalHotkeyManager(config, root / "config" / "shortcut_key.json")
    start_playback()
    from lib.localTts import is_local_voice, warm_up

    if is_local_voice(config.VOICE):
        warm_up()
    return ChatUUTTSApp(
        config=config,
        hotkey_manager=hotkeys,
        text_to_speech=text_to_speech,
        root_dir=root,
        profiles=profiles,
        ui=ui,
    )


def main():
    if _register_from_flag():
        return
    if not claim_single_instance():
        return
    from lib.singleInstance import watch_activation
    from lib.ttsEngine import cleanup_tts_engine

    app = None
    try:
        app = build()
        watch_activation(app)
        app.mainloop()
    finally:
        if app is not None:
            try:
                app.hotkey_manager.stop()
            except Exception:
                pass
        cleanup_tts_engine()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        traceback.print_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("CHATUUTTS", f"启动失败：{exc}")
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
