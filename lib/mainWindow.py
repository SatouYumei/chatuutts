"""CHATUUTTS 窗口。"""

import ctypes
import re
import threading
import time
import tkinter as tk
import webbrowser

from lib.paths import app_dir, resource_dir
from lib.audioOutput import (
    configure_output,
    find_new_microphone,
    list_capture_names,
    list_output_names,
    refresh_audio_devices,
)
from lib.localTts import is_local_voice, warm_up
from lib.ttsEngine import cache_size, clear_cache, format_cache_size
from lib.updater import UpdateCancelled, can_install, check_for_update, download, launch_installer
from lib.version import VERSION
from lib.virtualCable import (
    MISSING_DRIVER,
    device_node_exists,
    driver_present,
    ensure_microphone,
    hide_extra_speakers,
    keep_real_defaults,
    microphone_installed,
    open_driver_download,
    rename_microphone,
)
from lib.globalHotkeyManager import build_hotkey, display_hotkey
from lib.profiles import (
    active_profile,
    apply_profile_to_config,
    normalize_profile,
    save_profiles,
    save_ui,
    sync_sound_model,
)
from lib.themes import THEMES, theme_by_id
from lib.voices import profile_summary, role_choices, style_choices, voice_choices
from lib.widgets import (
    IconButton,
    PlaceholderEntry,
    PlayButton,
    Tooltip,
    ValueSlider,
    apply_app_icon,
    apply_round,
    apply_topmost,
    enable_drag,
    enable_taskbar,
    font,
    own_window,
    raise_window,
    smooth_disc,
    virtual_screen,
    wordmark_image,
)


COMPACT_SIZE = (360, 56)
EXPANDED_SIZE = (820, 560)
PLACEHOLDER = "输入文字"
TEXT_PLACEHOLDER = "输入要朗读的文字"


class ChatUUTTSApp(tk.Tk):
    def __init__(self, config, hotkey_manager, text_to_speech, root_dir, profiles, ui):
        super().__init__()
        self.config = config
        self.hotkey_manager = hotkey_manager
        self.text_to_speech = text_to_speech
        self.root_dir = root_dir
        self.profile_path = root_dir / "config" / "voice_profiles.json"
        self.ui_path = root_dir / "config" / "ui_state.json"
        self.sound_model_path = root_dir / "config" / "sound_model.json"
        self.profiles = profiles
        self.ui = ui
        if not any(item["id"] == self.ui.get("theme") for item in THEMES):
            self.ui["theme"] = "dark"
        self.theme = theme_by_id(self.ui["theme"])
        self.mode = self.ui.get("mode") or "compact"
        self._dialogs = []
        self._placed = False
        self._output_names = []
        self._capture_names = []
        self._mic_capture_name = ""
        self._virtual_busy = False
        self._ready = False
        self._update_info = None
        self._update_checking = False
        self._update_dialog = None
        self.update_btn = None
        try:
            configure_output(
                self.ui.get("speaker") or "",
                bool(self.ui.get("virtual_mic")),
                self.ui.get("virtual_mic_device") or "",
            )
        except Exception as exc:
            print(f"Audio output setup failed: {exc}")
        self._taskbar_done = False
        self._last_size = None
        self._ellipse = 56
        self.title("CHATUUTTS")
        apply_app_icon(self)
        self.overrideredirect(True)
        self.configure(bg=self.theme["border"])
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Alt-F4>", lambda _event: self.on_close())
        self.bind("<Button-3>", self._popup_menu)
        self.bind_all("<Button-1>", self._dismiss_option_popup, add="+")
        self._rebuild()
        self.after(30, self._install_taskbar)
        self.after(1200, self._ensure_visible)
        if self.ui.get("hotkeys_enabled"):
            self.hotkey_manager.start()
        threading.Thread(target=self._quiet_hide_speaker, name="tts-hide-speaker", daemon=True).start()
        if self.ui.get("check_updates"):
            self.after(4000, lambda: self.check_updates(manual=False))

    def _track(self, dialog):
        self._dialogs.append(dialog)

        def forget(event):
            if event.widget is dialog and dialog in self._dialogs:
                self._dialogs.remove(dialog)

        dialog.bind("<Destroy>", forget)

    def _close_dialogs(self):
        for dialog in list(self._dialogs):
            try:
                dialog.grab_release()
            except Exception:
                pass
            try:
                dialog.destroy()
            except Exception:
                pass
        self._dialogs.clear()

    def on_close(self):
        self._remember_geometry()
        save_ui(self.ui_path, self.ui)
        self._close_dialogs()
        self.destroy()

    def _remember_geometry(self):
        try:
            self.ui["x"] = self.winfo_x()
            self.ui["y"] = self.winfo_y()
            self.ui["mode"] = self.mode
        except tk.TclError:
            pass

    def _popup_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        if self.mode == "compact":
            menu.add_command(label="展开", command=lambda: self.set_mode("expanded"))
        else:
            menu.add_command(label="缩小", command=lambda: self.set_mode("compact"))
        menu.add_separator()
        if self._update_info:
            menu.add_command(label=f"更新到 {self._update_info['version']}", command=self.open_update)
        menu.add_command(label="检查更新", command=lambda: self.check_updates(manual=True))
        self._check_updates_var = tk.BooleanVar(self, value=bool(self.ui.get("check_updates")))
        menu.add_checkbutton(label="启动时检查更新", variable=self._check_updates_var, command=self.toggle_check_updates)
        menu.add_command(label=f"版本 {VERSION}", state="disabled")
        menu.add_separator()
        menu.add_command(label="退出", command=self.on_close)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _install_taskbar(self):
        if self._taskbar_done:
            return
        self._taskbar_done = True
        geo = None
        try:
            geo = self.geometry()
            self.withdraw()
            self.update_idletasks()
            enable_taskbar(self)
        except Exception:
            pass
        self.deiconify()
        self.update_idletasks()
        if geo:
            try:
                self.geometry(geo)
            except tk.TclError:
                pass
        self._apply_chrome()
        apply_app_icon(self)
        self._ready = True

    def _ensure_visible(self):
        try:
            if self.state() == "withdrawn":
                self.deiconify()
        except tk.TclError:
            return

    def _position(self, width, height):
        if self._placed:
            try:
                if self.winfo_viewable():
                    return self._clamp(int(self.winfo_x()), int(self.winfo_y()), width, height)
            except tk.TclError:
                pass
        x, y = self.ui.get("x"), self.ui.get("y")
        if x is None or y is None:
            x = (self.winfo_screenwidth() - width) // 2
            y = max(20, (self.winfo_screenheight() - height) // 3)
        return self._clamp(int(x), int(y), width, height)

    def _clamp(self, x, y, width, height):
        vx, vy, vw, vh = virtual_screen()
        if vw < 100 or vh < 100:
            vx, vy = 0, 0
            vw, vh = self.winfo_screenwidth(), self.winfo_screenheight()
        if x > vx + vw - 80 or y > vy + vh - 40 or x + width < vx + 80 or y < vy - 20:
            return vx + max(0, (vw - width) // 2), vy + max(0, (vh - height) // 3)
        return x, y

    def _rebuild(self):
        self._stop_mascot()
        draft = ""
        if getattr(self, "shell", None) is not None:
            draft = self._draft_text()
        for child in self.winfo_children():
            child.destroy()
        self.theme = theme_by_id(self.ui.get("theme"))
        self.configure(bg=self.theme["border"])
        self.shell = tk.Frame(self, bg=self.theme["bg"], highlightthickness=0, bd=0)
        self.shell.pack(fill="both", expand=True, padx=1, pady=1)
        self.shell.bind("<Button-3>", self._popup_menu)
        if self.mode == "expanded":
            width, height = EXPANDED_SIZE
            self._ellipse = 28
            self._build_expanded()
        else:
            self.mode = "compact"
            width, height = COMPACT_SIZE
            self._ellipse = height
            self._build_compact()
        x, y = self._position(width, height)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self._placed = True
        self.update_idletasks()
        self._apply_chrome()
        if draft:
            self._restore_text(draft)

    def _apply_chrome(self):
        try:
            apply_round(self, self._ellipse)
            apply_topmost(self, self.ui.get("topmost"))
        except Exception:
            pass

    def _draft_text(self):
        if self.mode == "compact" and getattr(self, "entry", None) is not None:
            try:
                return self.entry.value()
            except tk.TclError:
                return ""
        if self.mode == "expanded" and getattr(self, "text", None) is not None:
            try:
                return self.text.get("1.0", "end-1c").strip()
            except tk.TclError:
                return ""
        return ""

    def _restore_text(self, text):
        if self.mode == "compact" and getattr(self, "entry", None) is not None:
            self.entry.restore(text)
        elif self.mode == "expanded" and getattr(self, "text", None) is not None:
            self.text.delete("1.0", "end")
            if text:
                self.text.insert("1.0", text)
            self._sync_text_placeholder()

    def _clear_input(self):
        if self.mode == "compact" and getattr(self, "entry", None) is not None:
            self.entry.clear_value()
        elif self.mode == "expanded" and getattr(self, "text", None) is not None:
            self.text.delete("1.0", "end")
            self._sync_text_placeholder()

    def set_mode(self, mode):
        if mode not in ("compact", "expanded") or mode == self.mode:
            return
        self._remember_geometry()
        self.mode = mode
        self.ui["mode"] = mode
        save_ui(self.ui_path, self.ui)
        self._rebuild()

    def _brand_mark(self, parent, height):
        theme = self.theme
        try:
            photo = wordmark_image(theme["text"], height)
        except Exception:
            return tk.Label(parent, text="CHATUUTTS", bg=theme["bg"], fg=theme["text"], font=font(13, "bold"))
        brand = tk.Label(parent, image=photo, bg=theme["bg"], bd=0, highlightthickness=0)
        brand._wordmark = photo
        return brand

    def _icon(self, parent, kind, command, tip, toggle=False):
        theme = self.theme
        button = IconButton(
            parent,
            kind,
            command,
            bg=parent["bg"],
            color=theme["muted"],
            active_color=theme["accent"],
            hover_color=theme["text"],
        )
        if toggle:
            button.set_on(False)
        Tooltip(button, tip, theme["card"], theme["text"])
        return button

    def _build_compact(self):
        theme = self.theme
        row = tk.Frame(self.shell, bg=theme["bg"])
        row.pack(fill="both", expand=True, padx=12)
        enable_drag(self, row)
        row.bind("<ButtonRelease-1>", lambda _event: self._remember_and_save())
        row.bind("<Button-3>", self._popup_menu)

        holder = tk.Frame(row, bg=theme["input"], height=32)
        holder.pack(side="left", fill="x", expand=True, pady=8)
        holder.pack_propagate(False)
        self.entry = PlaceholderEntry(
            holder,
            PLACEHOLDER,
            theme["muted"],
            relief="flat",
            bd=0,
            bg=theme["input"],
            fg=theme["text"],
            insertbackground=theme["text"],
            font=font(12),
            highlightthickness=0,
        )
        self.entry.pack(fill="both", expand=True, padx=12, pady=6)
        self.entry.bind("<Return>", lambda _event: self.speak())

        self.play_btn = PlayButton(row, self.speak, theme["accent"], theme["accent_text"], theme["bg"])
        self.play_btn.pack(side="left", padx=(8, 4))
        self.pin_btn = self._icon(row, "pin", self.toggle_topmost, "窗口置顶", toggle=True)
        self.pin_btn.pack(side="left", padx=1)
        self.pin_btn.set_on(bool(self.ui.get("topmost")))
        self.key_btn = self._icon(row, "keyboard", self.toggle_hotkeys, "启用快捷键", toggle=True)
        self.key_btn.pack(side="left", padx=1)
        self.key_btn.set_on(bool(self.ui.get("hotkeys_enabled")))
        expand = self._icon(row, "expand", lambda: self.set_mode("expanded"), "展开")
        expand.pack(side="left", padx=(1, 0))

    def _build_expanded(self):
        theme = self.theme
        header = tk.Frame(self.shell, bg=theme["bg"], height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        brand = self._brand_mark(header, 34)
        brand.pack(side="left", padx=(14, 8))
        enable_drag(self, header)
        enable_drag(self, brand)
        header.bind("<ButtonRelease-1>", lambda _event: self._remember_and_save())
        brand.bind("<ButtonRelease-1>", lambda _event: self._remember_and_save())
        icons = tk.Frame(header, bg=theme["bg"])
        icons.pack(side="right", padx=8)
        self.pin_btn = self._icon(icons, "pin", self.toggle_topmost, "窗口置顶", toggle=True)
        self.pin_btn.pack(side="left", padx=1)
        self.pin_btn.set_on(bool(self.ui.get("topmost")))
        self.key_btn = self._icon(icons, "keyboard", self.toggle_hotkeys, "启用快捷键", toggle=True)
        self.key_btn.pack(side="left", padx=1)
        self.key_btn.set_on(bool(self.ui.get("hotkeys_enabled")))
        self._icon(icons, "palette", self.open_themes, "主题").pack(side="left", padx=1)
        self._icon(icons, "collapse", lambda: self.set_mode("compact"), "缩小").pack(side="left", padx=1)
        self._icon(icons, "close", self.on_close, "关闭").pack(side="left", padx=1)

        tk.Frame(self.shell, bg=theme["border"], height=1).pack(fill="x")
        body = tk.Frame(self.shell, bg=theme["bg"])
        body.pack(fill="both", expand=True)

        sidebar = tk.Frame(body, bg=theme["sidebar"], width=220, height=400)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        sidebar.grid_propagate(False)
        sidebar.configure(width=220)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)
        tk.Label(
            sidebar,
            text="我的配置",
            bg=theme["sidebar"],
            fg=theme["muted"],
            font=font(10),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        new_btn = tk.Label(
            sidebar,
            text="+  新建",
            bg=theme["sidebar"],
            fg=theme["muted"],
            font=font(12),
            anchor="w",
            padx=16,
            pady=12,
            cursor="hand2",
        )
        new_btn.grid(row=3, column=0, sticky="ew")
        new_btn.bind("<Button-1>", lambda _event: self.open_editor(is_new=True))
        new_btn.bind("<Enter>", lambda _event: new_btn.configure(fg=theme["text"]))
        new_btn.bind("<Leave>", lambda _event: new_btn.configure(fg=theme["muted"]))
        self.cache_btn = tk.Label(
            sidebar,
            text="一键清理缓存\n计算中…",
            bg=theme["sidebar"],
            fg=theme["muted"],
            font=font(11),
            anchor="w",
            justify="left",
            padx=16,
            pady=8,
            cursor="hand2",
        )
        self.cache_btn.grid(row=4, column=0, sticky="ew")
        self.cache_btn.bind("<Button-1>", lambda _event: self._clear_cache())
        self.cache_btn.bind("<Enter>", lambda _event: self.cache_btn.configure(fg=theme["text"]))
        self.cache_btn.bind("<Leave>", lambda _event: self.cache_btn.configure(fg=self.theme["muted"]))
        self._show_cache_size()

        self.mascot_canvas = tk.Canvas(sidebar, bg=theme["sidebar"], highlightthickness=0, bd=0, width=200, height=1)
        self.mascot_canvas.grid(row=2, column=0, sticky="nsew")
        self.mascot_canvas.bind("<Configure>", self._on_mascot_configure)

        self.profile_canvas = tk.Canvas(sidebar, bg=theme["sidebar"], highlightthickness=0, bd=0, width=200, height=44)
        self.profile_canvas.grid(row=1, column=0, sticky="ew")
        self.profile_list = tk.Frame(self.profile_canvas, bg=theme["sidebar"])
        self._profile_window = self.profile_canvas.create_window((0, 0), window=self.profile_list, anchor="nw")
        self.profile_canvas.bind("<Configure>", self._size_profile_list)
        self.profile_canvas.bind("<MouseWheel>", self._wheel_profiles)
        self._refresh_sidebar()

        tk.Frame(body, bg=theme["border"], width=1).pack(side="left", fill="y")
        main = tk.Frame(body, bg=theme["bg"])
        main.pack(side="left", fill="both", expand=True)
        profile = active_profile(self.profiles)
        tk.Label(main, text="当前配置", bg=theme["bg"], fg=theme["muted"], font=font(10), anchor="w").pack(
            fill="x", padx=24, pady=(16, 0)
        )
        self.heading_name = tk.Label(
            main,
            text=profile["name"],
            bg=theme["bg"],
            fg=theme["text"],
            font=font(22, "bold"),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self.heading_name.pack(fill="x", padx=24, pady=(2, 0))
        self.heading_meta = tk.Label(
            main,
            text=profile_summary(profile),
            bg=theme["bg"],
            fg=theme["muted"],
            font=font(11),
            anchor="w",
        )
        self.heading_meta.pack(fill="x", padx=24, pady=(2, 12))

        card = tk.Frame(main, bg=theme["input"])
        self.text = tk.Text(
            card,
            height=6,
            wrap="word",
            bd=0,
            bg=theme["input"],
            fg=theme["text"],
            insertbackground=theme["text"],
            font=font(13),
            highlightthickness=0,
            padx=12,
            pady=8,
            undo=True,
        )
        self.text.pack(fill="both", expand=True)
        self.text.bind("<Return>", self._text_return)
        self.text.bind("<FocusIn>", self._sync_text_placeholder)
        self.text.bind("<FocusOut>", self._sync_text_placeholder)
        self.text.bind("<KeyRelease>", self._sync_text_placeholder)
        self.text_placeholder = tk.Label(
            self.text,
            text=TEXT_PLACEHOLDER,
            fg=theme["muted"],
            bg=theme["input"],
            font=font(13),
        )
        self.text_placeholder.place(x=14, y=8)
        self.text_placeholder.bind("<Button-1>", lambda _event: self.text.focus_set())

        actions_in_card = tk.Frame(card, bg=theme["input"])
        actions_in_card.pack(fill="x")
        speak = tk.Label(
            actions_in_card,
            text="朗读",
            bg=theme["accent"],
            fg=theme["accent_text"],
            font=font(12, "bold"),
            padx=16,
            pady=6,
            cursor="hand2",
        )
        speak.pack(side="right", padx=10, pady=10)
        speak.bind("<Button-1>", lambda _event: self.speak())
        self.play_btn = None

        self.status = tk.Label(main, text="", bg=theme["bg"], fg=theme["danger"], font=font(10), anchor="w")
        self.status.pack(side="bottom", fill="x", padx=24, pady=(2, 10))
        self._build_audio(main)
        tools = tk.Frame(main, bg=theme["bg"])
        tools.pack(side="bottom", fill="x", padx=24, pady=(0, 4))
        self._outline(tools, "编辑声音", lambda: self.open_editor(is_new=False)).pack(side="left", padx=(0, 8))
        self._outline(tools, "快捷发言", self.open_shortcuts).pack(side="left")
        self._tools = tools
        self.update_btn = None
        if self._update_info:
            self._show_update_button()
        card.pack(fill="both", expand=True, padx=24, pady=(0, 12))

    def _outline(self, parent, text, command):
        theme = self.theme
        holder = tk.Frame(parent, bg=theme["border"], padx=1, pady=1, cursor="hand2")
        inner = tk.Label(
            holder,
            text=text,
            bg=theme["bg"],
            fg=theme["text"],
            font=font(12),
            padx=14,
            pady=6,
            cursor="hand2",
        )
        inner.pack()
        holder.bind("<Button-1>", lambda _event: command())
        inner.bind("<Button-1>", lambda _event: command())
        inner.bind("<Enter>", lambda _event: inner.configure(bg=theme["hover"]))
        inner.bind("<Leave>", lambda _event: inner.configure(bg=theme["bg"]))
        return holder

    def _text_return(self, event):
        if event.state & 0x0001:
            return None
        self.speak()
        return "break"

    def _sync_text_placeholder(self, _event=None):
        if getattr(self, "text", None) is None or getattr(self, "text_placeholder", None) is None:
            return
        content = self.text.get("1.0", "end-1c").strip()
        focused = self.focus_get() == self.text
        if content or focused:
            self.text_placeholder.place_forget()
        else:
            self.text_placeholder.place(x=14, y=8)

    def _size_profile_list(self, event):
        self.profile_canvas.itemconfigure(self._profile_window, width=event.width)
        self.profile_canvas.configure(scrollregion=self.profile_canvas.bbox("all"))

    def _wheel_profiles(self, event):
        self.profile_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _refresh_sidebar(self):
        if not getattr(self, "profile_list", None):
            return
        theme = self.theme
        for child in self.profile_list.winfo_children():
            child.destroy()
        current = active_profile(self.profiles)["id"]
        for profile in self.profiles["profiles"]:
            selected = profile["id"] == current
            row = tk.Frame(
                self.profile_list,
                bg=theme["selected"] if selected else theme["sidebar"],
                cursor="hand2",
            )
            if selected:
                tk.Frame(row, bg=theme["accent"], width=3).pack(side="left", fill="y")
            label = tk.Label(
                row,
                text=profile["name"],
                bg=row["bg"],
                fg=theme["text"],
                font=font(12, "bold" if selected else "normal"),
                anchor="w",
                padx=12,
                pady=9,
                wraplength=160,
                justify="left",
            )
            label.pack(side="left", fill="x", expand=True)
            row.pack(fill="x", padx=8, pady=2)
            for widget in (row, label):
                widget.bind("<Button-1>", lambda _event, pid=profile["id"]: self.select_profile(pid))
                widget.bind("<MouseWheel>", self._wheel_profiles)
        self.profile_list.update_idletasks()
        self.profile_canvas.configure(scrollregion=self.profile_canvas.bbox("all"))
        self._fit_profile_canvas()

    def _fit_profile_canvas(self):
        if not getattr(self, "profile_canvas", None) or not getattr(self, "profile_list", None):
            return
        self.profile_list.update_idletasks()
        needed = max(1, self.profile_list.winfo_reqheight())
        self.profile_canvas.configure(height=min(needed, 240))

    def _stop_mascot(self):
        for name in ("_mascot_job", "_mascot_layout_job"):
            job = getattr(self, name, None)
            if not job:
                continue
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            setattr(self, name, None)
        self._mascot_frames = []
        self._mascot_side = 0
        self._mascot_item = None

    def _show_cache_size(self):
        button = getattr(self, "cache_btn", None)
        if button is None:
            return

        def work():
            try:
                size = cache_size(self.config)
            except Exception:
                size = 0

            def apply():
                widget = getattr(self, "cache_btn", None)
                if widget is None:
                    return
                try:
                    if widget.winfo_exists():
                        widget.configure(text=f"一键清理缓存\n{format_cache_size(size)}")
                except tk.TclError:
                    pass

            try:
                self.after(0, apply)
            except tk.TclError:
                pass

        threading.Thread(target=work, name="tts-cache-size", daemon=True).start()

    def _clear_cache(self):
        if getattr(self, "_cache_clearing", False):
            return
        self._cache_clearing = True
        try:
            self.cache_btn.configure(text="正在清理…")
        except tk.TclError:
            self._cache_clearing = False
            return

        def work():
            try:
                clear_cache(self.config)
            except Exception:
                pass

            def apply():
                self._cache_clearing = False
                self._show_cache_size()

            try:
                self.after(0, apply)
            except tk.TclError:
                self._cache_clearing = False

        threading.Thread(target=work, name="tts-cache-clear", daemon=True).start()

    def _on_mascot_configure(self, event):
        if event.width < 40 or event.height < 40:
            return
        job = getattr(self, "_mascot_layout_job", None)
        if job:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._mascot_layout_job = self.after(80, self._layout_mascot)

    def _layout_mascot(self):
        self._mascot_layout_job = None
        canvas = getattr(self, "mascot_canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
            width = canvas.winfo_width()
            height = canvas.winfo_height()
        except tk.TclError:
            return
        if width < 40 or height < 40:
            return
        side = max(48, min(width, height, 230))
        if abs(side - getattr(self, "_mascot_side", 0)) > 6 or not getattr(self, "_mascot_frames", None):
            self._load_mascot_frames(side)
            self._mascot_side = side
            if getattr(self, "_mascot_job", None):
                try:
                    self.after_cancel(self._mascot_job)
                except tk.TclError:
                    pass
                self._mascot_job = None
            self._animate_mascot(0)
        self._place_mascot()

    def _place_mascot(self, frame=None):
        canvas = self.mascot_canvas
        height = max(1, canvas.winfo_height())
        item = getattr(self, "_mascot_item", None)
        if item is None:
            if frame is None:
                return
            self._mascot_item = canvas.create_image(0, height, image=frame, anchor="sw")
            return
        if frame is not None:
            canvas.itemconfigure(item, image=frame)
        canvas.itemconfigure(item, anchor="sw")
        canvas.coords(item, 0, height)

    def _show_mascot_frame(self, frame):
        self._place_mascot(frame)

    def _load_mascot_frames(self, side):
        from PIL import Image, ImageTk

        path = resource_dir() / "assets" / "mascot.gif"
        image = Image.open(path)
        color = self.theme["sidebar"].lstrip("#")
        plate_color = tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))
        frames = []
        delays = []
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            frame = image.convert("RGBA").resize((side, side), Image.Resampling.LANCZOS)
            frame = frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            frame.putalpha(frame.getchannel("A").point(lambda value: value // 2))
            plate = Image.new("RGBA", frame.size, plate_color + (255,))
            plate.alpha_composite(frame)
            frames.append(ImageTk.PhotoImage(plate))
            delays.append(max(40, int(image.info.get("duration") or 80)))
        self._mascot_frames = frames
        self._mascot_delays = delays

    def _animate_mascot(self, index):
        frames = getattr(self, "_mascot_frames", None)
        canvas = getattr(self, "mascot_canvas", None)
        if not frames or canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
            self._show_mascot_frame(frames[index])
        except tk.TclError:
            return
        delay = self._mascot_delays[index]
        self._mascot_job = self.after(delay, lambda: self._animate_mascot((index + 1) % len(frames)))

    def _refresh_heading(self):
        if self.mode != "expanded" or not getattr(self, "heading_name", None):
            return
        profile = active_profile(self.profiles)
        self.heading_name.configure(text=profile["name"])
        self.heading_meta.configure(text=profile_summary(profile))

    def select_profile(self, profile_id):
        found = next((item for item in self.profiles["profiles"] if item["id"] == profile_id), None)
        if found is None:
            return
        self.profiles["active_id"] = found["id"]
        save_profiles(self.profile_path, self.profiles)
        self._use_profile(found, persist=True)
        self._refresh_sidebar()
        self._refresh_heading()
        self._refresh_audio()

    def _use_profile(self, profile, persist):
        apply_profile_to_config(self.config, profile)
        if is_local_voice(profile["VOICE"]):
            warm_up()
        if persist:
            sync_sound_model(self.sound_model_path, profile)

    def preview_voice(self, draft, on_status=None):
        import copy

        config = copy.copy(self.config)
        config.VOICE = draft["VOICE"]
        config.VOICE_STYLE = draft["VOICE_STYLE"]
        config.VOICE_ROLE = draft.get("VOICE_ROLE") or "Default"
        config.SPEED = int(draft["SPEED"])
        config.PITCH = int(draft["PITCH"])
        config.VOLUME = int(draft.get("VOLUME", 100))
        config.STYLE_DEGREE = int(draft.get("STYLE_DEGREE", 100))
        self.text_to_speech("今天天气真不错.", config, on_status=on_status)

    def _remember_and_save(self):
        self._remember_geometry()
        save_ui(self.ui_path, self.ui)

    def toggle_topmost(self):
        self.ui["topmost"] = not bool(self.ui.get("topmost"))
        save_ui(self.ui_path, self.ui)
        self._apply_chrome()
        if getattr(self, "pin_btn", None) is not None:
            self.pin_btn.set_on(bool(self.ui["topmost"]))

    def toggle_hotkeys(self):
        self.ui["hotkeys_enabled"] = not bool(self.ui.get("hotkeys_enabled"))
        save_ui(self.ui_path, self.ui)
        self._apply_hotkey_state()
        if getattr(self, "key_btn", None) is not None:
            self.key_btn.set_on(bool(self.ui["hotkeys_enabled"]))

    def _shortcut_editor_open(self):
        return any(isinstance(dialog, ShortcutEditor) for dialog in self._dialogs)

    def _apply_hotkey_state(self):
        if self.ui.get("hotkeys_enabled") and not self._shortcut_editor_open():
            self.hotkey_manager.start()
        else:
            self.hotkey_manager.stop()

    def speak(self):
        text = self._draft_text()
        if not text:
            return
        self._clear_input()
        self._report_error("")
        self.text_to_speech(text, self.config, on_status=self._on_tts_status)

    def _on_tts_status(self, message):
        if not message:
            return

        def show():
            if self.winfo_exists():
                self._report_error(message)

        try:
            self.after(0, show)
        except tk.TclError:
            print(message)

    def _report_error(self, message):
        if getattr(self, "play_btn", None) is not None and message:
            self.play_btn.set_fill(self.theme["danger"])
            self.after(700, self._restore_play)
        if getattr(self, "status", None) is not None:
            try:
                self.status.configure(text=message)
            except tk.TclError:
                return
            if message:
                self.after(4000, lambda: self.status.configure(text="") if self.winfo_exists() else None)

    def _restore_play(self):
        if getattr(self, "play_btn", None) is not None and self.play_btn.winfo_exists():
            self.play_btn.set_fill(self.theme["accent"])

    def open_editor(self, is_new):
        if is_new:
            current = active_profile(self.profiles)
            draft = normalize_profile(
                {
                    "name": "",
                    "VOICE": current["VOICE"],
                    "VOICE_STYLE": current["VOICE_STYLE"],
                    "VOICE_ROLE": current.get("VOICE_ROLE") or "Default",
                    "SPEED": current["SPEED"],
                    "PITCH": current["PITCH"],
                    "VOLUME": current.get("VOLUME", 100),
                    "STYLE_DEGREE": current.get("STYLE_DEGREE", 100),
                },
                current,
            )
            draft["name"] = ""
        else:
            draft = dict(active_profile(self.profiles))
        VoiceEditor(self, draft, is_new)

    def save_editor(self, draft, is_new):
        name = draft["name"].strip()
        if not name:
            return "请填写名称"
        duplicate = any(
            item["name"] == name and item["id"] != draft["id"] for item in self.profiles["profiles"]
        )
        if duplicate:
            return "已经有同名配置"
        draft["name"] = name
        draft["SPEED"] = int(draft["SPEED"])
        draft["PITCH"] = int(draft["PITCH"])
        draft["VOLUME"] = int(draft.get("VOLUME", 100))
        draft["STYLE_DEGREE"] = int(draft.get("STYLE_DEGREE", 100))
        draft["VOICE_ROLE"] = draft.get("VOICE_ROLE") or "Default"
        if is_new:
            self.profiles["profiles"].append(draft)
        else:
            for index, item in enumerate(self.profiles["profiles"]):
                if item["id"] == draft["id"]:
                    self.profiles["profiles"][index] = draft
                    break
            else:
                self.profiles["profiles"].append(draft)
        self.profiles["active_id"] = draft["id"]
        save_profiles(self.profile_path, self.profiles)
        self._use_profile(draft, persist=True)
        self._refresh_sidebar()
        self._refresh_heading()
        self._refresh_audio()
        return ""

    def delete_profile(self, profile_id):
        if len(self.profiles["profiles"]) <= 1:
            return "至少保留一个配置"
        self.profiles["profiles"] = [item for item in self.profiles["profiles"] if item["id"] != profile_id]
        self.profiles["active_id"] = self.profiles["profiles"][0]["id"]
        save_profiles(self.profile_path, self.profiles)
        self._use_profile(active_profile(self.profiles), persist=True)
        self._refresh_sidebar()
        self._refresh_heading()
        self._refresh_audio()
        return ""

    def open_shortcuts(self):
        self.hotkey_manager.stop()
        ShortcutEditor(self)

    def _build_audio(self, main):
        theme = self.theme
        box = tk.Frame(main, bg=theme["bg"])
        box.pack(side="bottom", fill="x", padx=24, pady=(4, 0))

        speaker_row = tk.Frame(box, bg=theme["bg"])
        speaker_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            speaker_row,
            text="扬声器",
            width=10,
            anchor="w",
            bg=theme["bg"],
            fg=theme["muted"],
            font=font(11),
        ).pack(side="left")
        self.speaker_var = tk.StringVar(value=self._speaker_caption())
        self._choice(speaker_row, self.speaker_var, self._open_speaker_menu).pack(side="left", fill="x", expand=True)

        mic_row = tk.Frame(box, bg=theme["bg"])
        mic_row.pack(fill="x")
        tk.Label(
            mic_row,
            text="虚拟麦克风",
            width=10,
            anchor="w",
            bg=theme["bg"],
            fg=theme["muted"],
            font=font(11),
        ).pack(side="left")
        self.mic_switch = tk.Label(
            mic_row,
            text="关",
            bg=theme["card"],
            fg=theme["text"],
            font=font(11),
            padx=10,
            pady=4,
            cursor="hand2",
        )
        self.mic_switch.pack(side="left", padx=(0, 8))
        self.mic_switch.bind("<Button-1>", lambda _event: self._toggle_virtual())
        self.mic_name = tk.Label(
            mic_row,
            text="未注册",
            bg=theme["bg"],
            fg=theme["text"],
            font=font(10),
            anchor="w",
        )
        self.mic_name.pack(side="left", fill="x", expand=True)

        self.audio_hint = tk.Label(
            box,
            text="",
            bg=theme["bg"],
            fg=theme["muted"],
            font=font(9),
            anchor="w",
            justify="left",
            wraplength=420,
        )
        self.audio_hint.pack(fill="x", pady=(4, 0))
        self._refresh_audio()
        self._reload_devices()

    def _choice(self, parent, variable, command):
        theme = self.theme
        holder = tk.Frame(parent, bg=theme["border"], padx=1, pady=1, cursor="hand2")
        inner = tk.Frame(holder, bg=theme["input"], cursor="hand2")
        inner.pack(fill="both", expand=True)
        label = tk.Label(
            inner,
            textvariable=variable,
            bg=theme["input"],
            fg=theme["text"],
            font=font(10),
            anchor="w",
            padx=10,
            pady=4,
            cursor="hand2",
        )
        label.pack(side="left", fill="x", expand=True)
        mark = tk.Label(inner, text="▾", bg=theme["input"], fg=theme["muted"], font=font(10), padx=8, cursor="hand2")
        mark.pack(side="right")

        def fire(_event, target=holder):
            command(target)

        for widget in (holder, inner, label, mark):
            widget.bind("<Button-1>", fire)
        return holder

    def _reload_devices(self):
        def work():
            try:
                outputs = list_output_names()
                captures = list_capture_names()
            except Exception as exc:
                print(f"Audio device list failed: {exc}")
                return

            def apply():
                if not self.winfo_exists():
                    return
                self._output_names = outputs
                self._capture_names = captures
                render, capture = find_new_microphone(outputs, captures)
                self._mic_capture_name = capture
                if self.ui.get("virtual_mic"):
                    if render and self.ui.get("virtual_mic_device") != render:
                        self.ui["virtual_mic_device"] = render
                        configure_output(self.ui.get("speaker") or "", True, render)
                        save_ui(self.ui_path, self.ui)
                    elif not render:
                        self.ui["virtual_mic"] = False
                        self.ui["virtual_mic_device"] = ""
                self._refresh_audio()

            try:
                self.after(0, apply)
            except tk.TclError:
                pass

        threading.Thread(target=work, name="tts-device-list", daemon=True).start()

    def _speaker_caption(self):
        name = self.ui.get("speaker") or ""
        if name == "none":
            return "只输出"
        if not name:
            return "系统默认"
        if self._output_names and name not in self._output_names:
            return f"{name}（未连接）"
        return name

    def _virtual_caption(self):
        capture = getattr(self, "_mic_capture_name", "") or ""
        if capture:
            return capture
        return "未注册"

    def _mic_hint(self):
        capture = getattr(self, "_mic_capture_name", "") or ""
        if self.ui.get("speaker") == "none" and capture:
            return f"本机不播放，只送到麦克风。其他软件选「{capture}」。"
        if self.ui.get("virtual_mic") and capture:
            return f"其他软件把麦克风选成「{capture}」。"
        if capture:
            return "语音基于肥肥咖啡 TTS 生成。"
        return "打开后会在本机注册一个新麦克风，不会使用现有声卡。"

    def _refresh_audio(self):
        if getattr(self, "speaker_var", None) is None:
            return
        try:
            self.speaker_var.set(self._speaker_caption())
            if getattr(self, "mic_name", None) is not None:
                self.mic_name.configure(text=self._virtual_caption())
            on = bool(self.ui.get("virtual_mic"))
            self.mic_switch.configure(
                text="开" if on else "关",
                bg=self.theme["accent"] if on else self.theme["card"],
                fg=self.theme["accent_text"] if on else self.theme["text"],
            )
            self.audio_hint.configure(text=self._mic_hint())
        except tk.TclError:
            pass

    def _save_audio(self):
        configure_output(
            self.ui.get("speaker") or "",
            bool(self.ui.get("virtual_mic")),
            self.ui.get("virtual_mic_device") or "",
        )
        save_ui(self.ui_path, self.ui)
        self._refresh_audio()

    def _dismiss_option_popup(self, event):
        for dialog in list(self._dialogs):
            if not isinstance(dialog, _OptionPopup):
                continue
            try:
                alive = dialog.winfo_exists()
            except tk.TclError:
                continue
            if not alive or not dialog.armed:
                continue
            if dialog.contains_widget(event.widget):
                continue
            dialog.close()

    def _open_menu(self, anchor, options, current, on_pick):
        for dialog in list(self._dialogs):
            if not isinstance(dialog, _OptionPopup):
                continue
            same = dialog.anchor is anchor
            dialog.close()
            if same:
                return
        _OptionPopup(self, anchor, options, current, on_pick)

    def _open_speaker_menu(self, anchor):
        options = [("none", "只输出"), ("", "系统默认")] + [
            (name, name)
            for name in self._output_names
            if not any(token in name.casefold() for token in ("vb-audio", "cable input", "cable output", "chatuu-tts"))
        ]
        self._open_menu(anchor, options, self.ui.get("speaker") or "", self._set_speaker)
        self._reload_devices()

    def _quiet_hide_speaker(self):
        try:
            rename_microphone()
        except Exception:
            pass
        try:
            hide_extra_speakers(feed_microphone=bool(self.ui.get("virtual_mic")))
        except Exception:
            pass
        while True:
            time.sleep(2)
            try:
                keep_real_defaults()
            except Exception:
                pass

    def _set_speaker(self, name):
        if name == "none":
            self._require_microphone(self._apply_output_only)
            return
        self.ui["speaker"] = name or ""
        self._save_audio()

    def _apply_output_only(self, render, capture):
        self.ui["speaker"] = "none"
        self.ui["virtual_mic"] = True
        self.ui["virtual_mic_device"] = render
        self._mic_capture_name = capture
        self._save_audio()

    def _apply_virtual_on(self, render, capture):
        self.ui["virtual_mic"] = True
        self.ui["virtual_mic_device"] = render
        self._mic_capture_name = capture
        self._save_audio()

    def _toggle_virtual(self):
        if self._virtual_busy:
            return
        if self.ui.get("virtual_mic"):
            self.ui["virtual_mic"] = False
            self.ui["virtual_mic_device"] = ""
            self._save_audio()
            threading.Thread(
                target=lambda: hide_extra_speakers(False),
                name="tts-hide-speaker",
                daemon=True,
            ).start()
            return
        self._require_microphone(self._apply_virtual_on)

    def _require_microphone(self, on_ready):
        render, capture = find_new_microphone(self._output_names, self._capture_names)
        if render and capture:
            on_ready(render, capture)
            return
        if self._virtual_busy:
            return
        self._virtual_busy = True
        log_path = app_dir() / "mic-check.txt"
        try:
            log_path.write_text("正在确认麦克风\n", encoding="utf-8")
        except OSError:
            pass
        try:
            self.mic_switch.configure(text="…", bg=self.theme["card"], fg=self.theme["text"])
            self.audio_hint.configure(
                text=f"结果在这个文件，不在 _internal 里：\n{log_path}",
                wraplength=420,
                justify="left",
            )
        except tk.TclError:
            self._virtual_busy = False
            return

        def work():
            self._register_and_continue(on_ready)

        threading.Thread(target=work, name="tts-register-mic", daemon=True).start()

    def _device_brief(self, outputs, captures):
        playback = "、".join(str(name) for name in (outputs or [])[:3]) or "无"
        recording = "、".join(str(name) for name in (captures or [])[:3]) or "无"
        return f"播放：{playback}\n录音：{recording}"

    def _seen_cable_names(self, outputs, captures):
        hits = []
        for name in list(outputs or []) + list(captures or []):
            folded = str(name).casefold()
            if any(token in folded for token in ("vb-audio", "cable", "chatuu")):
                hits.append(str(name))
        return hits

    def _write_mic_log(self, outputs, captures, render, capture, error):
        path = app_dir() / "mic-check.txt"
        lines = [
            f"driver_node={device_node_exists()}",
            f"microphone_installed={microphone_installed()}",
            f"render={render}",
            f"capture={capture}",
            f"error={error}",
            "outputs:",
            *[str(name) for name in outputs or []],
            "captures:",
            *[str(name) for name in captures or []],
        ]
        try:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            return ""
        return str(path)

    def _yield_for_admin(self):
        """先取消置顶并藏起自己，管理员确认才不会被这个窗口挡住。"""
        done = threading.Event()

        def drop():
            try:
                apply_topmost(self, False)
                self.withdraw()
                self.update()
            except tk.TclError:
                pass
            done.set()

        try:
            self.after(0, drop)
        except tk.TclError:
            done.set()
        done.wait(2)

    def _restore_after_admin(self):
        def restore():
            try:
                self.deiconify()
                self.lift()
                if self.ui.get("topmost"):
                    apply_topmost(self, True)
            except tk.TclError:
                pass

        try:
            self.after(0, restore)
        except tk.TclError:
            pass

    def _register_and_continue(self, on_ready):
        error = ""
        outputs = []
        captures = []
        render = ""
        capture = ""

        def status(message):
            def show():
                if self.winfo_exists():
                    self.audio_hint.configure(text=message)

            try:
                self.after(0, show)
            except tk.TclError:
                pass

        def scan():
            box = {}

            def run():
                try:
                    refresh_audio_devices()
                    box["outputs"] = list_output_names()
                    box["captures"] = list_capture_names()
                except Exception as exc:
                    box["error"] = str(exc)

            worker = threading.Thread(target=run, name="tts-device-scan", daemon=True)
            worker.start()
            worker.join(5)
            if worker.is_alive():
                return [], [], "", "", "读取设备超时"
            if box.get("error"):
                return [], [], "", "", box["error"]
            found_outputs = box.get("outputs") or []
            found_captures = box.get("captures") or []
            found_render, found_capture = find_new_microphone(found_outputs, found_captures)
            return found_outputs, found_captures, found_render, found_capture, ""

        try:
            outputs, captures, render, capture, scan_error = scan()
            error = scan_error
            self._write_mic_log(outputs, captures, render, capture, error or "已读到设备")
            if not (render and capture):
                box = {}

                def prepare():
                    try:
                        box["error"] = ensure_microphone() or ""
                    except Exception as exc:
                        box["error"] = str(exc)

                worker = threading.Thread(target=prepare, name="tts-prepare-mic", daemon=True)
                worker.start()
                worker.join(3)
                if worker.is_alive():
                    error = error or "调整声卡超时"
                else:
                    error = box.get("error") or error
                    again = scan()
                    outputs, captures, render, capture, scan_error = again
                    if scan_error:
                        error = scan_error
                    elif render and capture:
                        error = ""
            self._write_mic_log(outputs, captures, render, capture, error or "完成")
        except Exception as exc:
            error = str(exc)
            self._write_mic_log(outputs, captures, render, capture, error)

        def apply():
            self._virtual_busy = False
            if not self.winfo_exists():
                return
            if outputs:
                self._output_names = outputs
            if captures:
                self._capture_names = captures
            self._mic_capture_name = capture
            if error == MISSING_DRIVER:
                open_driver_download()
                self._refresh_audio()
                try:
                    self.audio_hint.configure(
                        text="还没有 VB-CABLE。已打开官方下载页，装好并重启后再打开。"
                    )
                except tk.TclError:
                    pass
                self._report_error("请先安装 VB-CABLE")
                return
            if error or not render or not capture:
                self._refresh_audio()
                self._write_mic_log(outputs, captures, render, capture, error)
                if not error and driver_present():
                    error = "驱动已经在了，不再弹出管理员窗口。"
                try:
                    self.audio_hint.configure(
                        text=self._device_brief(outputs, captures),
                        wraplength=420,
                        justify="left",
                    )
                except tk.TclError:
                    pass
                self._report_error(error or "新麦克风还没有注册好")
                return
            on_ready(render, capture)

        try:
            self.after(0, apply)
        except tk.TclError:
            self._virtual_busy = False

    def check_updates(self, manual=False):
        """后台问一次 GitHub。手动检查时，没有更新或出错也要告诉用户。"""
        if self._update_checking:
            return
        self._update_checking = True

        def work():
            info, failed = None, False
            try:
                info = check_for_update()
            except Exception as exc:
                print(f"Update check failed: {exc}")
                failed = True
            try:
                self.after(0, lambda: self._on_update_checked(info, failed, manual))
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=work, name="tts-update-check", daemon=True).start()

    def _on_update_checked(self, info, failed, manual):
        self._update_checking = False
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if failed:
            if manual:
                self._open_update_dialog(None, "检查更新失败，请检查网络后再试。")
            return
        if info is None:
            if manual:
                self._open_update_dialog(None, f"已经是最新版本 {VERSION}。")
            return
        if not manual and info["version"] == self.ui.get("skipped_version"):
            return
        self._update_info = info
        self._show_update_button()
        self._open_update_dialog(info)

    def _show_update_button(self):
        if self.mode != "expanded" or self.update_btn is not None or not self._update_info:
            return
        tools = getattr(self, "_tools", None)
        if tools is None or not tools.winfo_exists():
            return
        self.update_btn = self._outline(tools, f"更新到 {self._update_info['version']}", self.open_update)
        self.update_btn.pack(side="left", padx=(8, 0))

    def open_update(self):
        if self._update_info:
            self._open_update_dialog(self._update_info)

    def _open_update_dialog(self, info, message=""):
        dialog = self._update_dialog
        if dialog is not None:
            try:
                if dialog.winfo_exists():
                    dialog._raise_above()
                    return
            except tk.TclError:
                pass
        try:
            self._update_dialog = UpdateDialog(self, info, message)
        except Exception as exc:
            print(f"Update dialog failed: {exc}")

    def skip_version(self, version):
        self.ui["skipped_version"] = version
        save_ui(self.ui_path, self.ui)
        self._update_info = None
        if self.update_btn is not None:
            try:
                self.update_btn.destroy()
            except tk.TclError:
                pass
            self.update_btn = None

    def toggle_check_updates(self):
        self.ui["check_updates"] = not bool(self.ui.get("check_updates"))
        save_ui(self.ui_path, self.ui)

    def open_themes(self):
        for dialog in self._dialogs:
            if isinstance(dialog, ThemePicker) and dialog.winfo_exists():
                dialog._raise_above()
                return
        try:
            ThemePicker(self)
        except Exception as exc:
            print(f"Theme picker failed: {exc}")
            self._report_error("主题窗口没有打开")

    def choose_theme(self, theme_id):
        self.after(1, lambda: self._apply_theme(theme_id))

    def _apply_theme(self, theme_id):
        draft = self._draft_text()
        self.ui["theme"] = theme_id
        save_ui(self.ui_path, self.ui)
        self.theme = theme_by_id(theme_id)
        self._close_dialogs()
        self._rebuild()
        self._restore_text(draft)


class _OptionPopup(tk.Toplevel):
    def __init__(self, app, anchor, options, current, on_pick):
        super().__init__(app)
        self.app = app
        self.anchor = anchor
        self.armed = False
        self._mouse_down = False
        theme = app.theme
        self.overrideredirect(True)
        self.configure(bg=theme["border"])
        self.attributes("-topmost", True)
        frame = tk.Frame(self, bg=theme["bg"])
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        for value, label in options:
            selected = value == current
            row = tk.Label(
                frame,
                text=label,
                bg=theme["selected"] if selected else theme["bg"],
                fg=theme["text"],
                font=font(10),
                anchor="w",
                padx=12,
                pady=6,
                cursor="hand2",
            )
            row.pack(fill="x")
            row.bind("<Enter>", lambda _event, widget=row, chosen=selected: widget.configure(bg=theme["hover"] if not chosen else theme["selected"]))
            row.bind("<Leave>", lambda _event, widget=row, chosen=selected: widget.configure(bg=theme["selected"] if chosen else theme["bg"]))
            row.bind("<Button-1>", lambda _event, picked=value: self._choose(on_pick, picked))
        self.update_idletasks()
        width = max(anchor.winfo_width(), 260)
        height = self.winfo_reqheight()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        vx, vy, vw, vh = virtual_screen()
        if vw > 0 and vh > 0 and y + height > vy + vh:
            y = anchor.winfo_rooty() - height - 4
        if vw > 0 and vh > 0:
            x = min(max(vx, x), max(vx, vx + vw - width))
            y = min(max(vy, y), max(vy, vy + vh - height))
        self.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")
        self._raise_above()
        self.bind("<Escape>", lambda _event: self.close())
        app._track(self)
        self.after(16, self._arm)

    def contains_widget(self, widget):
        current = widget
        while current is not None:
            if current == self:
                return True
            current = getattr(current, "master", None)
        return False

    def _pointer_inside(self):
        return self._pointer_over(self)

    def _pointer_on_anchor(self):
        return self._pointer_over(self.anchor)

    def _pointer_over(self, widget):
        try:
            if widget is None or not widget.winfo_exists():
                return False
            x, y = self.winfo_pointerxy()
            left, top = widget.winfo_rootx(), widget.winfo_rooty()
            width, height = widget.winfo_width(), widget.winfo_height()
        except tk.TclError:
            return False
        return left <= x < left + width and top <= y < top + height

    def _arm(self):
        if not self.winfo_exists():
            return
        if ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000:
            self.after(16, self._arm)
            return
        self.armed = True
        self._mouse_down = False
        self.after(16, self._watch_outside)

    def _watch_outside(self):
        if not self.winfo_exists() or not self.armed:
            return
        down = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        if down and not self._mouse_down and not self._pointer_inside() and not self._pointer_on_anchor():
            self.close()
            return
        self._mouse_down = down
        self.after(16, self._watch_outside)

    def close(self):
        self.armed = False
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.destroy()

    def _raise_above(self):
        if not self.winfo_exists():
            return
        try:
            own_window(self, self.app)
            self.lift()
            self.attributes("-topmost", True)
            raise_window(self)
        except tk.TclError:
            pass

    def _choose(self, on_pick, value):
        self.after(1, lambda: self._finish(on_pick, value))

    def _finish(self, on_pick, value):
        self.close()
        on_pick(value)


class _Dialog(tk.Toplevel):
    def __init__(self, app, title, width, height):
        super().__init__(app)
        self.app = app
        self.theme = app.theme
        self.overrideredirect(True)
        self.configure(bg=self.theme["border"])
        self.geometry(_center(app, width, height))
        self.attributes("-topmost", True)
        self.shell = tk.Frame(self, bg=self.theme["bg"], highlightthickness=0, bd=0)
        self.shell.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(self.shell, bg=self.theme["bg"], height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        label = tk.Label(header, text=title, bg=self.theme["bg"], fg=self.theme["text"], font=font(13, "bold"))
        label.pack(side="left", padx=16)
        enable_drag(self, header)
        enable_drag(self, label)
        close = IconButton(
            header,
            "close",
            self.close,
            bg=self.theme["bg"],
            color=self.theme["muted"],
            active_color=self.theme["accent"],
            hover_color=self.theme["text"],
        )
        close.pack(side="right", padx=8)
        Tooltip(close, "关闭", self.theme["card"], self.theme["text"])
        tk.Frame(self.shell, bg=self.theme["border"], height=1).pack(fill="x")
        self.body = tk.Frame(self.shell, bg=self.theme["bg"])
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda _event: self.close())
        self.update_idletasks()
        self._raise_above()
        self.focus_force()
        app._track(self)
        self.after(20, lambda: apply_round(self, 24))
        self.after(50, self._grab)
        self.after(150, self._raise_above)

    def _raise_above(self):
        if not self.winfo_exists():
            return
        try:
            self.deiconify()
            own_window(self, self.app)
            self.lift()
            self.attributes("-topmost", True)
            raise_window(self)
            self.focus_force()
        except tk.TclError:
            pass

    def _grab(self):
        if not self.winfo_exists():
            return
        self._raise_above()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def _center(app, width, height):
    vx, vy, vw, vh = virtual_screen()
    x = app.winfo_x() + max(0, (app.winfo_width() - width) // 2)
    y = app.winfo_y() + max(0, (app.winfo_height() - height) // 2)
    if vw > 0 and vh > 0:
        x = min(max(vx, x), max(vx, vx + vw - width))
        y = min(max(vy, y), max(vy, vy + vh - height))
    return f"{width}x{height}+{int(x)}+{int(y)}"


class VoiceEditor(_Dialog):
    def __init__(self, app, draft, is_new):
        super().__init__(app, "编辑配置" if not is_new else "新建配置", 460, 900)
        self.draft = draft
        self.draft.setdefault("VOLUME", 100)
        self.draft.setdefault("STYLE_DEGREE", 100)
        self.draft.setdefault("VOICE_ROLE", "Default")
        self.is_new = is_new
        theme = self.theme
        buttons = tk.Frame(self.body, bg=theme["bg"])
        buttons.pack(side="bottom", fill="x", padx=20, pady=12)
        self.error = tk.Label(self.body, text="", bg=theme["bg"], fg=theme["danger"], font=font(10), anchor="w")
        self.error.pack(side="bottom", fill="x", padx=20)
        left_text = "取消" if is_new else "删除"
        left = tk.Label(
            buttons,
            text=left_text,
            bg=theme["card"],
            fg=theme["danger"] if not is_new else theme["text"],
            font=font(12),
            padx=14,
            pady=6,
            cursor="hand2",
        )
        left.pack(side="left")
        left.bind("<Button-1>", lambda _event: self._left())
        save = tk.Label(
            buttons,
            text="保存",
            bg=theme["accent"],
            fg=theme["accent_text"],
            font=font(12, "bold"),
            padx=16,
            pady=6,
            cursor="hand2",
        )
        save.pack(side="right")
        save.bind("<Button-1>", lambda _event: self._save())
        preview = tk.Label(
            buttons,
            text="试听",
            bg=theme["card"],
            fg=theme["text"],
            font=font(12),
            padx=14,
            pady=6,
            cursor="hand2",
        )
        preview.pack(side="right", padx=(0, 8))
        preview.bind("<Button-1>", lambda _event: self._preview())

        self.form = tk.Canvas(self.body, bg=theme["bg"], highlightthickness=0, bd=0)
        self.form.pack(fill="both", expand=True)
        self.form_inner = tk.Frame(self.form, bg=theme["bg"])
        self._form_window = self.form.create_window((0, 0), window=self.form_inner, anchor="nw")
        self.form_inner.bind("<Configure>", lambda _event: self._sync_form_scroll())
        self.form.bind("<Configure>", lambda event: self.form.itemconfigure(self._form_window, width=event.width))
        self.form.bind("<MouseWheel>", self._form_wheel)

        tk.Label(self.form_inner, text="名称", bg=theme["bg"], fg=theme["muted"], font=font(10), anchor="w").pack(
            fill="x", padx=20, pady=(14, 4)
        )
        self.name_entry = tk.Entry(
            self.form_inner,
            relief="flat",
            bd=0,
            bg=theme["input"],
            fg=theme["text"],
            insertbackground=theme["text"],
            font=font(13),
            highlightthickness=0,
        )
        self.name_entry.pack(fill="x", padx=20, ipady=8, ipadx=8)
        if draft["name"]:
            self.name_entry.insert(0, draft["name"])
        self.name_entry.bind("<Return>", lambda _event: self._save())
        self.name_entry.focus_set()

        tk.Label(self.form_inner, text="音色", bg=theme["bg"], fg=theme["muted"], font=font(10), anchor="w").pack(
            fill="x", padx=20, pady=(14, 4)
        )
        self.voice_list = tk.Frame(self.form_inner, bg=theme["bg"])
        self.voice_list.pack(fill="x", padx=20)
        self._paint_voices()

        tk.Label(self.form_inner, text="风格", bg=theme["bg"], fg=theme["muted"], font=font(10), anchor="w").pack(
            fill="x", padx=20, pady=(12, 4)
        )
        self.style_row = tk.Frame(self.form_inner, bg=theme["bg"])
        self.style_row.pack(fill="x", padx=20)
        self._paint_styles()

        tk.Label(self.form_inner, text="角色", bg=theme["bg"], fg=theme["muted"], font=font(10), anchor="w").pack(
            fill="x", padx=20, pady=(12, 4)
        )
        self.role_row = tk.Frame(self.form_inner, bg=theme["bg"])
        self.role_row.pack(fill="x", padx=20)
        self._paint_roles()

        self._slider("语速", "SPEED", min(-50, int(self.draft["SPEED"])), max(50, int(self.draft["SPEED"])))
        self._slider("音调", "PITCH", min(-50, int(self.draft["PITCH"])), max(50, int(self.draft["PITCH"])))
        self._slider("音量", "VOLUME", 0, 100)
        self._slider("风格强度", "STYLE_DEGREE", 1, 200, lambda value: f"{value / 100:.1f}")
        self._bind_form_wheel(self.form_inner)
        self.after(1, self._sync_form_scroll)

    def _sync_form_scroll(self):
        self.form.update_idletasks()
        self.form.configure(scrollregion=self.form.bbox("all"))

    def _form_wheel(self, event):
        self.form.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _bind_form_wheel(self, widget):
        widget.bind("<MouseWheel>", self._form_wheel)
        for child in widget.winfo_children():
            self._bind_form_wheel(child)

    def _slider(self, title, key, minimum, maximum, format_value=None):
        theme = self.theme
        shown = format_value(int(self.draft[key])) if format_value else str(int(self.draft[key]))
        row = tk.Frame(self.form_inner, bg=theme["bg"])
        tk.Label(row, text=title, bg=theme["bg"], fg=theme["muted"], font=font(10)).pack(side="left")
        value_label = tk.Label(row, text=shown, bg=theme["bg"], fg=theme["text"], font=font(12))
        value_label.pack(side="right")
        slider = ValueSlider(
            self.form_inner,
            minimum,
            maximum,
            int(self.draft[key]),
            lambda value, field=key, label=value_label, formatter=format_value: self._set_slider(
                field, label, value, formatter
            ),
            theme["bg"],
            theme["accent"],
            theme["border"],
            width=400,
        )
        row.pack(fill="x", padx=20, pady=(10, 0))
        slider.pack(fill="x", padx=20, pady=(0, 4))

    def _set_slider(self, key, label, value, format_value=None):
        self.draft[key] = int(value)
        label.configure(text=format_value(int(value)) if format_value else str(int(value)))

    def _paint_voices(self):
        theme = self.theme
        for child in self.voice_list.winfo_children():
            child.destroy()
        choices = voice_choices(self.draft["VOICE"])
        for index, (voice_id, short, desc) in enumerate(choices):
            selected = voice_id == self.draft["VOICE"]
            cell = tk.Frame(self.voice_list, bg=theme["accent"] if selected else theme["border"], padx=1, pady=1, cursor="hand2")
            inner = tk.Frame(cell, bg=theme["selected"] if selected else theme["card"], cursor="hand2")
            inner.pack(fill="both", expand=True)
            name = tk.Label(inner, text=short, bg=inner["bg"], fg=theme["text"], font=font(11, "bold"), anchor="w")
            name.pack(fill="x", padx=8, pady=(6, 0))
            detail = tk.Label(inner, text=desc, bg=inner["bg"], fg=theme["muted"], font=font(9), anchor="w")
            detail.pack(fill="x", padx=8, pady=(0, 6))
            cell.grid(row=index // 2, column=index % 2, sticky="nsew", padx=4, pady=4)
            for widget in (cell, inner, name, detail):
                widget.bind("<Button-1>", lambda _event, vid=voice_id: self._select_voice(vid))
                widget.bind("<MouseWheel>", self._form_wheel)
        self.voice_list.grid_columnconfigure(0, weight=1)
        self.voice_list.grid_columnconfigure(1, weight=1)

    def _select_voice(self, voice_id):
        self.draft["VOICE"] = voice_id
        styles = {item[0] for item in style_choices(voice_id)}
        if self.draft.get("VOICE_STYLE") not in styles:
            self.draft["VOICE_STYLE"] = "general"
        roles = {item[0] for item in role_choices(voice_id)}
        if self.draft.get("VOICE_ROLE", "Default") not in roles:
            self.draft["VOICE_ROLE"] = "Default"
        self._paint_voices()
        self._paint_styles()
        self._paint_roles()
        self._bind_form_wheel(self.form_inner)
        self._sync_form_scroll()

    def _paint_chips(self, parent, choices, current, on_pick):
        theme = self.theme
        for child in parent.winfo_children():
            child.destroy()
        columns = 4
        for index, (item_id, label) in enumerate(choices):
            selected = item_id == current
            chip = tk.Label(
                parent,
                text=label,
                bg=theme["accent"] if selected else theme["card"],
                fg=theme["accent_text"] if selected else theme["text"],
                font=font(11),
                padx=8,
                pady=4,
                cursor="hand2",
            )
            chip.grid(row=index // columns, column=index % columns, sticky="ew", padx=(0, 6), pady=(0, 6))
            chip.bind("<Button-1>", lambda _event, picked=item_id: on_pick(picked))
            chip.bind("<MouseWheel>", self._form_wheel)
        for column in range(columns):
            parent.grid_columnconfigure(column, weight=1)

    def _paint_styles(self):
        self._paint_chips(
            self.style_row,
            style_choices(self.draft["VOICE"], self.draft.get("VOICE_STYLE")),
            self.draft.get("VOICE_STYLE"),
            self._select_style,
        )

    def _select_style(self, style_id):
        self.draft["VOICE_STYLE"] = style_id
        self._paint_styles()

    def _paint_roles(self):
        self._paint_chips(
            self.role_row,
            role_choices(self.draft["VOICE"], self.draft.get("VOICE_ROLE")),
            self.draft.get("VOICE_ROLE") or "Default",
            self._select_role,
        )

    def _select_role(self, role_id):
        self.draft["VOICE_ROLE"] = role_id
        self._paint_roles()

    def _left(self):
        if self.is_new:
            self.close()
            return
        message = self.app.delete_profile(self.draft["id"])
        if message:
            self.error.configure(text=message)
            return
        self.close()

    def _preview(self):
        self.error.configure(fg=self.theme["muted"], text="正在试听…")

        def status(message):
            self.after(0, lambda text=message: self._preview_failed(text))

        self.app.preview_voice(self.draft, on_status=status)

    def _preview_failed(self, message):
        try:
            if not self.winfo_exists():
                return
            self.error.configure(fg=self.theme["danger"], text=message)
        except tk.TclError:
            pass

    def _save(self):
        self.draft["name"] = self.name_entry.get().strip()
        message = self.app.save_editor(self.draft, self.is_new)
        if message:
            self.error.configure(fg=self.theme["danger"], text=message)
            return
        self.close()


class ShortcutEditor(_Dialog):
    def __init__(self, app):
        super().__init__(app, "快捷发言", 560, 480)
        self.items = [dict(item) for item in app.hotkey_manager.shortcuts]
        self.mods = {"ctrl": True, "alt": False, "shift": False}
        theme = self.theme
        list_wrap = tk.Frame(self.body, bg=theme["bg"])
        list_wrap.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        self.list_canvas = tk.Canvas(list_wrap, bg=theme["bg"], highlightthickness=0, bd=0, height=220)
        self.list_canvas.pack(fill="both", expand=True)
        self.list_inner = tk.Frame(self.list_canvas, bg=theme["bg"])
        self._list_window = self.list_canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        self.list_canvas.bind("<Configure>", lambda event: self.list_canvas.itemconfigure(self._list_window, width=event.width))
        self.list_canvas.bind("<MouseWheel>", lambda event: self.list_canvas.yview_scroll(int(-event.delta / 120), "units"))
        self._render()

        form = tk.Frame(self.body, bg=theme["bg"])
        form.pack(fill="x", padx=16, pady=12)
        add = tk.Label(
            form,
            text="添加",
            bg=theme["accent"],
            fg=theme["accent_text"],
            font=font(12, "bold"),
            padx=12,
            pady=6,
            cursor="hand2",
        )
        add.pack(side="right", padx=(8, 0))
        add.bind("<Button-1>", lambda _event: self._add())
        self.mod_labels = {}
        for name, text in (("ctrl", "Ctrl"), ("alt", "Alt"), ("shift", "Shift")):
            chip = tk.Label(form, font=font(11), padx=10, pady=4, cursor="hand2")
            chip.pack(side="left", padx=(0, 6))
            chip.bind("<Button-1>", lambda _event, key=name: self._toggle_mod(key))
            self.mod_labels[name] = chip
        self._paint_mods()
        self.key_entry = PlaceholderEntry(
            form,
            "按键",
            theme["muted"],
            width=6,
            relief="flat",
            bd=0,
            bg=theme["input"],
            fg=theme["text"],
            insertbackground=theme["text"],
            font=font(12),
            highlightthickness=0,
        )
        self.key_entry.pack(side="left", padx=(4, 8), ipady=6, ipadx=6)
        self.text_entry = PlaceholderEntry(
            form,
            "要朗读的文字",
            theme["muted"],
            relief="flat",
            bd=0,
            bg=theme["input"],
            fg=theme["text"],
            insertbackground=theme["text"],
            font=font(12),
            highlightthickness=0,
        )
        self.text_entry.pack(side="left", fill="x", expand=True, ipady=6, ipadx=8)
        self.text_entry.bind("<Return>", lambda _event: self._add())
        self.key_entry.bind("<Return>", lambda _event: self.text_entry.focus_set())
        self.error = tk.Label(self.body, text="", bg=theme["bg"], fg=theme["danger"], font=font(10), anchor="w")
        self.error.pack(fill="x", padx=16)
        tk.Label(
            self.body,
            text="键盘图标打开后才会生效",
            bg=theme["bg"],
            fg=theme["muted"],
            font=font(10),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 12))

    def close(self):
        super().close()
        self.app._apply_hotkey_state()

    def _paint_mods(self):
        theme = self.theme
        for name, chip in self.mod_labels.items():
            selected = self.mods[name]
            chip.configure(
                text={"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift"}[name],
                bg=theme["accent"] if selected else theme["card"],
                fg=theme["accent_text"] if selected else theme["text"],
            )

    def _toggle_mod(self, name):
        self.mods[name] = not self.mods[name]
        self._paint_mods()

    def _render(self):
        theme = self.theme
        for child in self.list_inner.winfo_children():
            child.destroy()
        if not self.items:
            tk.Label(self.list_inner, text="还没有快捷发言", bg=theme["bg"], fg=theme["muted"], font=font(11)).pack(
                anchor="w", pady=8
            )
        for index, item in enumerate(self.items):
            row = tk.Frame(self.list_inner, bg=theme["card"])
            row.pack(fill="x", pady=4)
            tk.Label(
                row,
                text=display_hotkey(item["key"]),
                bg=theme["input"],
                fg=theme["text"],
                font=font(11),
                padx=8,
                pady=4,
            ).pack(side="left", padx=8, pady=8)
            tk.Label(
                row,
                text=item["text"],
                bg=theme["card"],
                fg=theme["text"],
                font=font(11),
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=4)
            remove = tk.Label(row, text="删除", bg=theme["card"], fg=theme["danger"], font=font(10), cursor="hand2", padx=8)
            remove.pack(side="right")
            remove.bind("<Button-1>", lambda _event, item_index=index: self._delete(item_index))
        self.list_inner.update_idletasks()
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all"))

    def _commit(self):
        self.app.hotkey_manager.replace_all(self.items)
        self.items = [dict(item) for item in self.app.hotkey_manager.shortcuts]
        self._render()

    def _delete(self, index):
        if 0 <= index < len(self.items):
            del self.items[index]
            self._commit()

    def _add(self):
        key = self.key_entry.value().lower()
        text = self.text_entry.value()
        modifiers = [name for name in ("ctrl", "alt", "shift") if self.mods[name]]
        if not modifiers:
            self.error.configure(text="至少选择一个修饰键")
            return
        if not key:
            self.error.configure(text="请填写按键")
            return
        if not re.fullmatch(r"[a-z0-9]|f([1-9]|1[0-2])|space|enter|tab", key):
            self.error.configure(text="按键请填 a-z、0-9 或 f1-f12")
            return
        if not text:
            self.error.configure(text="请填写要朗读的文字")
            return
        raw = build_hotkey(modifiers, key)
        self.items = [item for item in self.items if item["key"].lower() != raw.lower()]
        self.items.append({"key": raw, "text": text})
        self.key_entry.clear_value()
        self.text_entry.clear_value()
        self.error.configure(text="")
        self._commit()


class ThemePicker(_Dialog):
    def __init__(self, app):
        super().__init__(app, "主题", 520, 560)
        theme = self.theme
        grid = tk.Frame(self.body, bg=theme["bg"])
        grid.pack(fill="both", expand=True, padx=12, pady=12)
        for index, item in enumerate(THEMES):
            selected = item["id"] == app.ui.get("theme")
            card = tk.Frame(grid, bg=theme["accent"] if selected else theme["border"], padx=2, pady=2, cursor="hand2")
            inner = tk.Frame(card, bg=item["bg"], cursor="hand2")
            inner.pack(fill="both", expand=True)
            swatch = tk.Canvas(inner, width=108, height=36, bg=item["bg"], highlightthickness=0, bd=0)
            swatch.pack(padx=6, pady=(6, 0))
            swatch.create_rectangle(0, 14, 72, 24, fill=item["input"], outline="")
            dot = smooth_disc(swatch, 18, item["accent"])
            swatch.disc = dot
            swatch.create_image(89, 19, image=dot)
            name = tk.Label(inner, text=item["name"], bg=item["bg"], fg=item["text"], font=font(9))
            name.pack(pady=(2, 6))
            card.grid(row=index // 4, column=index % 4, padx=5, pady=5, sticky="nsew")
            for widget in (card, inner, swatch, name):
                widget.bind(
                    "<Button-1>",
                    lambda _event, theme_id=item["id"]: app.after(1, lambda theme_id=theme_id: app.choose_theme(theme_id)),
                )
        for column in range(4):
            grid.grid_columnconfigure(column, weight=1)


def _plain_notes(markdown):
    """更新说明是 Markdown，去掉标记符号再放进文本框。"""
    lines = []
    for line in str(markdown or "").splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\|?[\s:|-]+\|?", stripped) and "-" in stripped:
            continue
        if stripped.startswith("|"):
            line = " · ".join(cell.strip() for cell in stripped.strip("|").split("|"))
        line = re.sub(r"^#+\s*", "", line)
        lines.append(line.replace("**", "").replace("`", ""))
    return "\n".join(lines).strip()


class UpdateDialog(_Dialog):
    """新版本提示。没有 info 时只显示一句结果。"""

    def __init__(self, app, info=None, message=""):
        super().__init__(app, "检查更新", 480, 520 if info else 200)
        self.info = info
        self.cancel = threading.Event()
        self.busy = False
        self._percent = -1
        theme = self.theme
        buttons = tk.Frame(self.body, bg=theme["bg"])
        buttons.pack(side="bottom", fill="x", padx=20, pady=12)
        if info is None:
            tk.Label(
                self.body,
                text=message,
                bg=theme["bg"],
                fg=theme["text"],
                font=font(12),
                anchor="w",
                justify="left",
                wraplength=430,
            ).pack(fill="x", padx=20, pady=(24, 0))
            self._button(buttons, "确定", self.close, primary=True).pack(side="right")
            return

        tk.Label(
            self.body,
            text=f"发现新版本 {info['version']}",
            bg=theme["bg"],
            fg=theme["text"],
            font=font(16, "bold"),
            anchor="w",
        ).pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(
            self.body,
            text=f"当前版本 {VERSION}",
            bg=theme["bg"],
            fg=theme["muted"],
            font=font(10),
            anchor="w",
        ).pack(fill="x", padx=20, pady=(2, 0))

        self.status = tk.Label(self.body, text="", bg=theme["bg"], fg=theme["muted"], font=font(10), anchor="w")
        self.status.pack(side="bottom", fill="x", padx=20)
        self.bar = tk.Canvas(self.body, height=6, bg=theme["input"], highlightthickness=0, bd=0)

        notes = tk.Text(
            self.body,
            wrap="word",
            bd=0,
            bg=theme["input"],
            fg=theme["text"],
            font=font(11),
            highlightthickness=0,
            padx=12,
            pady=8,
            height=10,
        )
        notes.insert("1.0", _plain_notes(info.get("notes")) or "这个版本没有附带更新说明。")
        notes.configure(state="disabled")
        notes.pack(fill="both", expand=True, padx=20, pady=(12, 8))

        self.update_label = self._button(buttons, "立即更新" if can_install() else "打开下载页", self._update, primary=True)
        self.update_label.pack(side="right")
        self._button(buttons, "稍后", self.close).pack(side="right", padx=(0, 8))
        self._button(buttons, "跳过这个版本", self._skip).pack(side="left")

    def _button(self, parent, text, command, primary=False):
        theme = self.theme
        label = tk.Label(
            parent,
            text=text,
            bg=theme["accent"] if primary else theme["card"],
            fg=theme["accent_text"] if primary else theme["text"],
            font=font(12, "bold" if primary else "normal"),
            padx=14,
            pady=6,
            cursor="hand2",
        )
        label.bind("<Button-1>", lambda _event: command())
        return label

    def _skip(self):
        if self.busy:
            return
        self.app.skip_version(self.info["version"])
        self.close()

    def _update(self):
        if self.busy:
            return
        if not can_install():
            webbrowser.open(self.info["page"])
            self.close()
            return
        self.busy = True
        self._percent = -1
        self.update_label.configure(text="下载中…")
        self.status.configure(fg=self.theme["muted"], text="正在下载安装包…")
        self.bar.pack(side="bottom", fill="x", padx=20, pady=(0, 6), before=self.status)

        def progress(done, total):
            percent = int(done * 100 / total) if total else -1
            if percent == self._percent:
                return
            self._percent = percent
            try:
                self.after(0, lambda: self._show_progress(done, total))
            except (tk.TclError, RuntimeError):
                pass

        def work():
            try:
                path = download(self.info, progress, self.cancel)
            except UpdateCancelled:
                return
            except Exception as exc:
                message = str(exc) or "下载失败"
                try:
                    self.after(0, lambda: self._failed(message))
                except (tk.TclError, RuntimeError):
                    pass
                return
            try:
                self.after(0, lambda: self._install(path))
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=work, name="tts-update-download", daemon=True).start()

    def _show_progress(self, done, total):
        if not self.winfo_exists():
            return
        width = max(1, self.bar.winfo_width())
        self.bar.delete("all")
        if total:
            self.bar.create_rectangle(0, 0, width * done / total, 6, fill=self.theme["accent"], outline="")
            self.status.configure(text=f"正在下载 {done / 1048576:.0f} / {total / 1048576:.0f} MB")
        else:
            self.status.configure(text=f"正在下载 {done / 1048576:.0f} MB")

    def _failed(self, message):
        if not self.winfo_exists():
            return
        self.busy = False
        self.update_label.configure(text="重试")
        self.status.configure(fg=self.theme["danger"], text=message)

    def _install(self, path):
        if not self.winfo_exists() or self.cancel.is_set():
            return
        self.status.configure(text="正在安装，完成后会自动重新打开…")
        try:
            launch_installer(path)
        except OSError as exc:
            self._failed(f"无法启动安装程序：{exc}")
            return
        self.app.after(500, self.app.on_close)

    def close(self):
        self.cancel.set()
        super().close()
