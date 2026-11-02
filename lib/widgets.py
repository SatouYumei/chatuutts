"""自绘控件和窗口圆角。"""

import ctypes
import math
import tkinter as tk

from lib.paths import resource_dir

UI_FONT = "Microsoft YaHei UI"


def font(size, weight="normal"):
    if weight == "bold":
        return (UI_FONT, size, "bold")
    return (UI_FONT, size)


def _safe_insets(width, height, radius):
    """内容区退到圆角里面，外圈留给平滑边缘。"""
    radius = min(float(radius), width / 2 - 1, height / 2 - 1)
    if radius < 2:
        return 1, 1
    max_iy = min(3, int(radius), max(1, (height - 48) // 2))
    chosen = None
    for iy in range(1, max_iy + 1):
        remain = radius * radius - (radius - iy) * (radius - iy)
        if remain <= 0:
            continue
        ix = max(1, int(math.ceil(radius - math.sqrt(remain))))
        if ix * 2 >= width - 80:
            continue
        if chosen is None or ix < chosen[0]:
            chosen = (ix, iy)
    return chosen or (1, 1)


def _key_rgb(colors):
    used = {tuple(color[:3]) for color in colors}
    red, green, blue = colors[0][:3]
    for offset in range(1, 8):
        candidate = ((red + offset) % 256, green, blue)
        if candidate not in used:
            return candidate
    return (0, 255, 0)


def _plate(width, height, radius, border_rgb, fill_rgb):
    from PIL import Image, ImageDraw, ImageTk

    scale = 4
    big = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    draw.rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1),
        radius=radius * scale,
        fill=border_rgb + (255,),
    )
    inset = scale
    inner_radius = max(0, radius * scale - inset)
    draw.rounded_rectangle(
        (inset, inset, width * scale - 1 - inset, height * scale - 1 - inset),
        radius=inner_radius,
        fill=fill_rgb + (255,),
    )
    small = big.resize((width, height), Image.Resampling.LANCZOS)
    key = _key_rgb((border_rgb, fill_rgb))
    base = Image.new("RGBA", (width, height), key + (255,))
    plate = Image.alpha_composite(base, small)
    return "#{:02x}{:02x}{:02x}".format(*key), ImageTk.PhotoImage(plate)


def top_hwnd(window):
    try:
        return int(window.frame(), 16)
    except Exception:
        return ctypes.windll.user32.GetParent(window.winfo_id())


def apply_round(window, ellipse):
    window.update_idletasks()
    width, height = window.winfo_width(), window.winfo_height()
    if width < 8 or height < 8 or ellipse <= 0:
        return
    radius = min(ellipse / 2.0, width / 2 - 1, height / 2 - 1)
    shell = getattr(window, "shell", None)
    current = str(window.cget("bg")).lower()
    if current == getattr(window, "_chrome_key", None):
        border = window._chrome_border
    else:
        border = window.cget("bg")
        window._chrome_border = border
    border_rgb = _hex_color(border)
    fill_rgb = _hex_color(shell.cget("bg")) if shell is not None else border_rgb
    try:
        key, plate = _plate(width, height, radius, border_rgb, fill_rgb)
        window.attributes("-transparentcolor", key)
        window.configure(bg=key)
        window._chrome_key = key.lower()
    except tk.TclError:
        return
    old = getattr(window, "_round_label", None)
    if old is not None:
        try:
            old.destroy()
        except tk.TclError:
            pass
    label = tk.Label(window, image=plate, bd=0, bg=key, highlightthickness=0)
    label.image = plate
    label.place(x=0, y=0, width=width, height=height)
    window._round_label = label
    window._round_plate = plate
    if shell is not None:
        ix, iy = _safe_insets(width, height, radius)
        try:
            shell.pack_configure(padx=ix, pady=iy)
        except tk.TclError:
            pass
        label.lower(shell)


def apply_topmost(window, enabled):
    window.attributes("-topmost", bool(enabled))
    insert_after = ctypes.c_void_p(-1 if enabled else -2)
    flags = 0x0001 | 0x0002 | 0x0010
    ctypes.windll.user32.SetWindowPos(top_hwnd(window), insert_after, 0, 0, 0, 0, flags)


def virtual_screen():
    """整块桌面，包含主屏旁边的显示器。"""
    user32 = ctypes.windll.user32
    return (
        int(user32.GetSystemMetrics(76)),
        int(user32.GetSystemMetrics(77)),
        int(user32.GetSystemMetrics(78)),
        int(user32.GetSystemMetrics(79)),
    )


def own_window(window, owner):
    """让弹窗属于主窗口，避免被置顶的主窗口盖住。"""
    set_long = ctypes.windll.user32.SetWindowLongPtrW
    set_long.restype = ctypes.c_void_p
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    set_long(top_hwnd(window), -8, top_hwnd(owner))


def raise_window(window):
    hwnd = top_hwnd(window)
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = ctypes.c_bool
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)


def _hex_color(color):
    text = str(color or "").lstrip("#")
    if len(text) != 6:
        return (32, 24, 16)
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def wordmark_image(color, height):
    """横向花体字标，染成当前主题的文字色。"""
    from PIL import Image, ImageTk

    source = Image.open(resource_dir() / "assets" / "wordmark.png").convert("RGBA")
    ratio = height / source.height
    width = max(1, round(source.width * ratio))
    if width > 168:
        width = 168
        height = max(1, round(source.height * (width / source.width)))
    resized = source.resize((width, height), Image.Resampling.LANCZOS)
    tinted = Image.new("RGBA", resized.size, _hex_color(color) + (0,))
    tinted.putalpha(resized.getchannel("A"))
    return ImageTk.PhotoImage(tinted)


def apply_app_icon(window):
    """窗口、任务栏都使用 chatuutts.ico。"""
    path = str(resource_dir() / "chatuutts.ico")
    try:
        window.iconbitmap(path)
        window.iconbitmap(default=path)
    except Exception:
        pass
    user32 = ctypes.windll.user32
    user32.LoadImageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    user32.SetClassLongPtrW.restype = ctypes.c_void_p
    big = user32.LoadImageW(None, path, 1, 256, 256, 0x00000010)
    small = user32.LoadImageW(None, path, 1, 32, 32, 0x00000010)
    hwnd = top_hwnd(window)
    if big:
        user32.SendMessageW(hwnd, 0x0080, 1, big)
        user32.SetClassLongPtrW(hwnd, -14, big)
    if small:
        user32.SendMessageW(hwnd, 0x0080, 0, small)
        user32.SetClassLongPtrW(hwnd, -34, small)
    window._app_icons = (big, small)


def enable_taskbar(window):
    """无边框窗口仍然出现在任务栏，方便关闭。"""
    hwnd = top_hwnd(window)
    user32 = ctypes.windll.user32
    get_long = user32.GetWindowLongPtrW
    set_long = user32.SetWindowLongPtrW
    get_long.restype = ctypes.c_void_p
    get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
    set_long.restype = ctypes.c_void_p
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    style = get_long(hwnd, -20) or 0
    style = (int(style) & ~0x00000080) | 0x00040000
    set_long(hwnd, -20, style)
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)


def enable_drag(window, widget):
    state = {}

    def start(event):
        state["origin"] = (event.x_root, event.y_root, window.winfo_x(), window.winfo_y())

    def move(event):
        origin = state.get("origin")
        if not origin:
            return
        x0, y0, left, top = origin
        window.geometry(f"+{left + event.x_root - x0}+{top + event.y_root - y0}")

    widget.bind("<ButtonPress-1>", start)
    widget.bind("<B1-Motion>", move)


def _paint_icon(kind, size, color, on=False):
    from PIL import Image, ImageDraw

    scale = 4
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    span = size * scale

    def p(value):
        return value * span / 28

    weight = max(2, round(1.65 * span / 28))

    def dot(x, y):
        radius = weight / 2
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    def stroke(points):
        seq = []
        for x, y in points:
            seq.extend((x, y))
        draw.line(seq, fill=color, width=weight, joint="curve")
        for x, y in points:
            dot(x, y)

    if kind == "pin":
        head = (p(9.2), p(3.2), p(18.8), p(12.8))
        draw.ellipse(head, outline=color, width=weight, fill=color if on else None)
        stroke([(p(14), p(12.2)), (p(14), p(21.2))])
        stroke([(p(10.4), p(21.2)), (p(17.6), p(21.2))])
    elif kind == "keyboard":
        draw.rounded_rectangle((p(4.0), p(6.8), p(24.0), p(21.4)), radius=p(2.6), outline=color, width=weight)
        key_weight = max(2, weight - 2)
        for left in (7.1, 12.3, 17.5):
            draw.rounded_rectangle((p(left), p(9.6), p(left + 3.4), p(13.2)), radius=p(0.8), outline=color, width=key_weight)
        draw.rounded_rectangle((p(8.4), p(15.2), p(19.6), p(18.6)), radius=p(0.9), outline=color, width=key_weight)
    elif kind == "expand":
        corners = (
            [(5.0, 11.4), (5.0, 5.0), (11.4, 5.0)],
            [(16.6, 5.0), (23.0, 5.0), (23.0, 11.4)],
            [(23.0, 16.6), (23.0, 23.0), (16.6, 23.0)],
            [(11.4, 23.0), (5.0, 23.0), (5.0, 16.6)],
        )
        for pts in corners:
            stroke([(p(x), p(y)) for x, y in pts])
    elif kind == "collapse":
        corners = (
            [(11.2, 6.2), (11.2, 11.2), (6.2, 11.2)],
            [(16.8, 6.2), (16.8, 11.2), (21.8, 11.2)],
            [(21.8, 16.8), (16.8, 16.8), (16.8, 21.8)],
            [(6.2, 16.8), (11.2, 16.8), (11.2, 21.8)],
        )
        for pts in corners:
            stroke([(p(x), p(y)) for x, y in pts])
    elif kind == "palette":
        ring = (p(4.4), p(4.4), p(23.6), p(23.6))
        draw.ellipse(ring, outline=color, width=weight)
        mask = Image.new("L", canvas.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        inset = weight * 0.45
        mask_draw.pieslice((ring[0] + inset, ring[1] + inset, ring[2] - inset, ring[3] - inset), start=90, end=270, fill=255)
        ink = Image.new("RGBA", canvas.size, color)
        canvas.alpha_composite(Image.composite(ink, Image.new("RGBA", canvas.size, (0, 0, 0, 0)), mask))
    elif kind == "close":
        stroke([(p(8.4), p(8.4)), (p(19.6), p(19.6))])
        stroke([(p(19.6), p(8.4)), (p(8.4), p(19.6))])
    elif kind == "plus":
        stroke([(p(8), p(14)), (p(20), p(14))])
        stroke([(p(14), p(8)), (p(14), p(20))])
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def _photo(image, master):
    from PIL import ImageTk

    return ImageTk.PhotoImage(image, master=master)


def smooth_disc(master, diameter, fill):
    from PIL import Image, ImageDraw

    scale = 4
    canvas = Image.new("RGBA", (diameter * scale, diameter * scale), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).ellipse((0, 0, diameter * scale - 1, diameter * scale - 1), fill=_hex_color(fill) + (255,))
    image = canvas.resize((diameter, diameter), Image.Resampling.LANCZOS)
    return _photo(image, master)


class IconButton(tk.Canvas):
    def __init__(self, master, kind, command, bg, color, active_color, hover_color, size=28):
        super().__init__(
            master,
            width=size,
            height=size,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.kind = kind
        self.command = command
        self.size = size
        self._bg = bg
        self._color = color
        self._active_color = active_color
        self._hover_color = hover_color
        self._on = False
        self._hover = False
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.redraw()

    def set_on(self, enabled):
        self._on = bool(enabled)
        self.redraw()

    def set_colors(self, bg, color, active_color, hover_color):
        self._bg = bg
        self._color = color
        self._active_color = active_color
        self._hover_color = hover_color
        self.configure(bg=bg)
        self.redraw()

    def _ink(self):
        if self._on:
            return self._active_color
        if self._hover:
            return self._hover_color
        return self._color

    def _enter(self, _event):
        self._hover = True
        self.redraw()

    def _leave(self, _event):
        self._hover = False
        self.redraw()

    def _click(self, _event):
        self.command()
        return "break"

    def redraw(self):
        self.delete("all")
        color = _hex_color(self._ink()) + (255,)
        image = _paint_icon(self.kind, self.size, color, self._on)
        self._photo = _photo(image, self)
        self.create_image(self.size / 2, self.size / 2, image=self._photo)


class PlayButton(tk.Canvas):
    def __init__(self, master, command, fill, foreground, background, size=34):
        super().__init__(
            master,
            width=size,
            height=size,
            bg=background,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.command = command
        self.size = size
        self._fill = fill
        self._foreground = foreground
        self.bind("<Button-1>", self._click)
        self.redraw()

    def set_colors(self, fill, foreground, background):
        self._fill = fill
        self._foreground = foreground
        self.configure(bg=background)
        self.redraw()

    def set_fill(self, fill):
        self._fill = fill
        self.redraw()

    def redraw(self):
        from PIL import Image, ImageDraw

        self.delete("all")
        size = self.size
        scale = 4
        canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((scale, scale, size * scale - scale, size * scale - scale), fill=_hex_color(self._fill) + (255,))
        draw.polygon(
            [
                (size * 0.40 * scale, size * 0.30 * scale),
                (size * 0.40 * scale, size * 0.70 * scale),
                (size * 0.74 * scale, size * 0.50 * scale),
            ],
            fill=_hex_color(self._foreground) + (255,),
        )
        self._photo = _photo(canvas.resize((size, size), Image.Resampling.LANCZOS), self)
        self.create_image(size / 2, size / 2, image=self._photo)

    def _click(self, _event):
        self.command()
        return "break"


class ValueSlider(tk.Canvas):
    def __init__(self, master, min_value, max_value, value, command, bg, accent, track, width=340, height=28):
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.min_value = min_value
        self.max_value = max_value
        self.value = int(value)
        self.command = command
        self._accent = accent
        self._track = track
        self._width = width
        self._height = height
        self.bind("<Button-1>", self._set_event)
        self.bind("<B1-Motion>", self._set_event)
        self.bind("<Configure>", self._on_configure)
        self.redraw()

    def _on_configure(self, event):
        if event.width > 20 and event.width != self._width:
            self._width = event.width
            self.redraw()

    def set_colors(self, bg, accent, track):
        self._accent = accent
        self._track = track
        self.configure(bg=bg)
        self.redraw()

    def _x(self):
        pad = 10
        span = self.max_value - self.min_value
        ratio = 0 if span == 0 else (self.value - self.min_value) / span
        return pad + ratio * (self._width - 2 * pad)

    def _set_event(self, event):
        pad = 10
        ratio = (event.x - pad) / (self._width - 2 * pad)
        ratio = max(0.0, min(1.0, ratio))
        value = int(round(self.min_value + ratio * (self.max_value - self.min_value)))
        if value != self.value:
            self.value = value
            self.command(value)
        self.redraw()

    def redraw(self):
        from PIL import Image, ImageDraw

        self.delete("all")
        width = max(1, int(self._width))
        height = max(1, int(self._height))
        scale = 4
        canvas = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        track_h = max(3 * scale, round(3.4 * height / 28 * scale))
        y = height * scale / 2
        pad = 10 * scale
        x0 = pad
        x1 = width * scale - pad
        knob = self._x() * scale
        radius = track_h / 2
        draw.rounded_rectangle((x0, y - radius, x1, y + radius), radius=radius, fill=_hex_color(self._track) + (255,))
        if knob > x0 + scale:
            draw.rounded_rectangle((x0, y - radius, knob, y + radius), radius=radius, fill=_hex_color(self._accent) + (255,))
        knob_r = 5.6 * height / 28 * scale
        ring = _hex_color(self.cget("bg")) + (255,)
        draw.ellipse((knob - knob_r, y - knob_r, knob + knob_r, y + knob_r), fill=ring)
        inner = knob_r * 0.62
        draw.ellipse((knob - inner, y - inner, knob + inner, y + inner), fill=_hex_color(self._accent) + (255,))
        self._photo = _photo(canvas.resize((width, height), Image.Resampling.LANCZOS), self)
        self.create_image(width / 2, height / 2, image=self._photo)


class PlaceholderEntry(tk.Entry):
    def __init__(self, master, placeholder, placeholder_fg, **kwargs):
        self.placeholder = placeholder
        self._placeholder_fg = placeholder_fg
        self._fg = kwargs.get("fg")
        super().__init__(master, **kwargs)
        self._showing = False
        self.show_placeholder()
        self.bind("<FocusIn>", self._focus_in)
        self.bind("<FocusOut>", self._focus_out)

    def show_placeholder(self):
        self.delete(0, "end")
        self.insert(0, self.placeholder)
        self.configure(fg=self._placeholder_fg)
        self._showing = True

    def _focus_in(self, _event):
        if self._showing:
            self.delete(0, "end")
            self.configure(fg=self._fg)
            self._showing = False

    def _focus_out(self, _event):
        if not self.get():
            self.show_placeholder()

    def value(self):
        if self._showing:
            return ""
        return self.get().strip()

    def clear_value(self):
        self.delete(0, "end")
        self._showing = False
        self.configure(fg=self._fg)
        if self.focus_get() is not self:
            self.show_placeholder()

    def restore(self, text):
        self.delete(0, "end")
        if text:
            self.insert(0, text)
            self.configure(fg=self._fg)
            self._showing = False
        else:
            self.show_placeholder()


class Tooltip:
    def __init__(self, widget, text, bg, fg):
        self.widget = widget
        self.text = text
        self.bg = bg
        self.fg = fg
        self.tip = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<Button-1>", self.hide, add="+")

    def _schedule(self, event):
        self.hide()
        x, y = event.x_root, event.y_root
        self.after_id = self.widget.after(450, lambda: self._show(x, y))

    def _show(self, x, y):
        self.after_id = None
        if not self.widget.winfo_exists():
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.configure(bg=self.bg)
        tk.Label(
            self.tip,
            text=self.text,
            bg=self.bg,
            fg=self.fg,
            font=font(9),
            padx=8,
            pady=3,
        ).pack()
        self.tip.geometry(f"+{x + 12}+{y + 16}")

    def hide(self, _event=None):
        if self.after_id is not None:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None
