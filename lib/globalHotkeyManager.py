"""全局快捷发言。"""

import json
from pathlib import Path

from pynput import keyboard

from lib.ttsEngine import text_to_speech


def display_hotkey(raw):
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "cmd": "Win"}
    parts = []
    for piece in str(raw).split("+"):
        piece = piece.strip()
        if piece.startswith("<") and piece.endswith(">"):
            name = piece[1:-1]
            parts.append(names.get(name.lower(), name.upper() if len(name) == 1 else name.capitalize()))
        elif len(piece) == 1:
            parts.append(piece.upper())
        else:
            parts.append(piece.capitalize())
    return " + ".join(parts)


def build_hotkey(modifiers, key):
    ordered = [name for name in ("ctrl", "alt", "shift") if name in modifiers]
    key = key.strip().lower()
    parts = [f"<{name}>" for name in ordered]
    if len(key) == 1 or key.isdigit():
        parts.append(key)
    else:
        parts.append(f"<{key}>")
    return "+".join(parts)


class GlobalHotkeyManager:
    def __init__(self, config, shortcut_file="shortcut_key.json"):
        """
        Args:
            config: TTS 配置对象
            shortcut_file: 快捷键配置文件路径
        """
        self.config = config
        self.shortcut_file = Path(shortcut_file)
        self.hotkeys = {}
        self.shortcuts = []
        self.listener = None
        self._load_shortcuts()

    def _load_shortcuts(self):
        """从 JSON 文件加载快捷键配置。"""
        try:
            if not self.shortcut_file.exists():
                print(f"Shortcut file not found: {self.shortcut_file}")
                self._create_example_file()
            with open(self.shortcut_file, "r", encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, list):
                raise ValueError("Shortcut file must contain a JSON array of objects.")
            self.hotkeys = {}
            self.shortcuts = []
            for item in data:
                if not isinstance(item, dict) or "key" not in item or "text" not in item:
                    print(f"Invalid shortcut item: {item}. Skipping.")
                    continue
                key_str = item["key"]
                text = item["text"]
                self.hotkeys[key_str] = text
                self.shortcuts.append({"key": key_str, "text": text})
                print(f"Loaded shortcut: {key_str} -> '{text}'")
        except Exception as exc:
            print(f"Error loading shortcut file {self.shortcut_file}: {exc}")

    def _create_example_file(self):
        """创建一个示例快捷键文件。"""
        example_data = [
            {"key": "<ctrl>+<alt>+1", "text": "你好，世界！"},
            {"key": "<ctrl>+<alt>+2", "text": "这是一条测试语音。"},
            {"key": "<ctrl>+<alt>+3", "text": "快捷键功能正常。"},
        ]
        try:
            self.shortcut_file.parent.mkdir(parents=True, exist_ok=True)
            _write_json(self.shortcut_file, example_data)
            print(f"Example shortcut file created at: {self.shortcut_file}")
        except Exception as exc:
            print(f"Failed to create example file: {exc}")

    def _on_hotkey_triggered(self, key_str):
        """某个全局快捷键被按下时调用。"""
        if key_str in self.hotkeys:
            text_to_speak = self.hotkeys[key_str]
            print(f"Global Hotkey Triggered: {key_str} -> '{text_to_speak}'")
            text_to_speech(text_to_speak, self.config)
        else:
            print(f"Unexpected hotkey triggered: {key_str}")

    def start(self):
        """启动全局快捷键监听。"""
        if self.listener:
            print("Hotkey listener is already running.")
            return
        if not self.hotkeys:
            print("No valid hotkeys loaded. Listener not started.")
            return
        try:
            callbacks = {
                key_str: (lambda k=key_str: self._on_hotkey_triggered(k))
                for key_str in self.hotkeys
            }
            self.listener = keyboard.GlobalHotKeys(callbacks)
            self.listener.start()
            print("Global hotkey listener started.")
        except Exception as exc:
            print(f"Failed to start global hotkey listener: {exc}")
            self.listener = None

    def stop(self):
        """停止全局快捷键监听。"""
        if self.listener:
            self.listener.stop()
            self.listener = None
            print("Global hotkey listener stopped.")

    def reload_shortcuts(self):
        """重新加载快捷键配置文件。"""
        old_hotkeys = self.hotkeys.copy()
        self._load_shortcuts()
        if self.listener and old_hotkeys != self.hotkeys:
            print("Shortcut configuration changed. Restarting listener...")
            self.stop()
            self.start()

    def replace_all(self, items):
        data = [{"key": item["key"], "text": item["text"]} for item in items]
        _write_json(self.shortcut_file, data)
        self.reload_shortcuts()


def _write_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(path)
