"""
Graphical IT Toolkit window.

The toolkit is a single frameless window with its own title bar. A cat dozes
on top of it with its paws over the edge. Pick a tool (click a card or press
1-4 / 0) and it wakes up, bats a couple of the other cards out of line, taps
yours, runs the tool inside the window, and drifts back to sleep a little later.
"""

import math
import os
import queue
import random
import subprocess
import sys
import threading
import time
from collections import OrderedDict
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

import fix_corrupted
import hardware_scan
import toolkit_launcher as launcher


VERSION = "v0.2.0"
MISCHIEF = 2  # how many other cards the cat bats out of line (0-3)
WINDOWS = os.name == "nt"

# ========= Layout (px) =========

HEADROOM = 50                    # extra see-through space for the hearts to float into
CAT_SPACE = 180 + HEADROOM       # see-through space above the window where the cat lies
PANEL_W, BAR_H, BODY_H, BORDER = 1040, 44, 600, 2
PANEL_X, PANEL_Y = 0, CAT_SPACE
BX = PANEL_X + BORDER                    # body origin
BY = PANEL_Y + BORDER + BAR_H + 1
BODY_W = PANEL_W - 2 * BORDER
WIN_W = PANEL_W
WIN_H = BY + BODY_H + BORDER

CAT_X, CAT_Y, CAT_W, CAT_H = PANEL_X + 390, HEADROOM + 9, 259, 196
CAT_ORIGIN = (CAT_W * 0.5, CAT_H * 0.87)
CAT_PAD = 16
ZZZ_X, ZZZ_Y = PANEL_X + 596, HEADROOM + 18

PAW_W, PAW_H = 80, 560
PAW_REST = (503, -40)

CTRL_W, CTRL_H, CTRL_GAP = 36, 28, 4

# ========= Colours =========

INK = "#3b2e24"
INK_SOFT = "#6e5c4a"
DESC = "#6a5847"
META = "#8c7a64"
LOG_INK = "#3d3a35"
LINE = "#cdbb9e"
EDGE = "#b9a588"
FRAME = "#5a4636"
PAPER = "#fbf6ea"
CARD = "#fffaf0"
BAR = "#efe4cf"
BAR_HOVER = "#e4d6bd"
ACCENT = "#d58042"           # oklch(0.68 0.13 55)
ACCENT_HOVER = "#c4733a"
CLOSE_HOVER = "#c42b1c"
PAD_PINK = "#eda9ad"         # oklch(0.8 0.08 15)
PAW_FUR = "#fffbf2"
PAW_LINE = "#9a7a5e"
ZZZ_INK = "#8a7a6a"
# Pixels of exactly this colour are see-through on Windows. It sits one step
# away from the frame colour so anti-aliased edges blend into the outline.
KEY = "#5a4637"

TOOLS = [
    ("1", "Hardware Scan", "Takes a snapshot of your computer's components and health status.",
     "reports/hardware_scan_report.txt"),
    ("2", "System File Repair", "Fixes corrupted Windows system files that may cause errors, crashes, or performance issues.",
     "DISM + SFC · runs in this window"),
    ("3", "Reliability History", "Shows a timeline of system events, crashes, and updates to help identify patterns.",
     "perfmon.exe /rel"),
    ("4", "Event Viewer", "Provides detailed logs for troubleshooting specific issues.",
     "eventvwr.msc"),
]
RETURN_LINE = "Returning to IT Toolkit menu in 3 seconds..."
LOG_LINES = 5
REPAIR_INTRO = ("This will run DISM (CheckHealth, ScanHealth, RestoreHealth) and SFC /scannow.\n"
                "Depending on system speed, this can take quite a while.\n\n"
                "Press Start repair to begin.")
REPAIR_STEPS = ["DISM CheckHealth", "DISM ScanHealth", "DISM RestoreHealth", "SFC /scannow"]


# ========= Helpers =========

def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def hex_rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    """Blend colour a towards b by t (0..1). Accepts hex strings or RGB tuples."""
    a = hex_rgb(a) if isinstance(a, str) else a
    b = hex_rgb(b) if isinstance(b, str) else b
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def cubic_bezier(x1, y1, x2, y2):
    """CSS cubic-bezier timing function."""
    def bez(t, p1, p2):
        u = 1 - t
        return 3 * u * u * t * p1 + 3 * u * t * t * p2 + t ** 3

    def ease(x):
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(30):
            mid = (lo + hi) / 2
            if bez(mid, x1, x2) < x:
                lo = mid
            else:
                hi = mid
        return bez((lo + hi) / 2, y1, y2)
    return ease


EASE = cubic_bezier(.25, .1, .25, 1)
EASE_IN_OUT = cubic_bezier(.42, 0, .58, 1)
SPRING = cubic_bezier(.2, 1.6, .4, 1)        # card swats
PAW_MOVE = cubic_bezier(.5, 0, .3, 1)
HEAD_WAKE = cubic_bezier(.3, 1.5, .5, 1)
HEAD_BREATHE = cubic_bezier(.45, 0, .55, 1)


def now_ms():
    return time.monotonic() * 1000


class Tween:
    """A value that eases to new targets like a CSS transition."""

    def __init__(self, value):
        self.v0 = self.v1 = value
        self.t0 = 0.0
        self.dur = 0.0
        self.ease = EASE

    def set(self, target, dur, ease):
        if target == self.v1:
            return
        t = now_ms()
        self.v0, self.v1, self.t0, self.dur, self.ease = self.get(t), target, t, dur, ease

    def get(self, t=None):
        t = now_ms() if t is None else t
        if self.dur <= 0 or t >= self.t0 + self.dur:
            return self.v1
        return self.v0 + (self.v1 - self.v0) * self.ease((t - self.t0) / self.dur)

    def moving(self, t):
        return t < self.t0 + self.dur


def rounded_points(x0, y0, x1, y1, r_tl, r_tr, r_br, r_bl, seg=8):
    pts = []
    for cx, cy, r, a0 in ((x0 + r_tl, y0 + r_tl, r_tl, 180), (x1 - r_tr, y0 + r_tr, r_tr, 270),
                          (x1 - r_br, y1 - r_br, r_br, 0), (x0 + r_bl, y1 - r_bl, r_bl, 90)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def ellipse_points(x0, y0, x1, y1, seg=20):
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    return [(cx + rx * math.cos(2 * math.pi * i / seg), cy + ry * math.sin(2 * math.pi * i / seg))
            for i in range(seg)]


def transformer(ox, oy, dx=0.0, dy=0.0, deg=0.0, scale=1.0):
    """Map local points like CSS translate(dx,dy) rotate(deg) scale(s) about (ox, oy)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))

    def f(x, y):
        x, y = (x - ox) * scale, (y - oy) * scale
        return ox + dx + x * c - y * s, oy + dy + x * s + y * c
    return f


def flat(pts):
    return [v for p in pts for v in p]


def register_fonts():
    """Load the bundled fonts for this process only (Windows). Returns True on success."""
    if not WINDOWS:
        return False
    try:
        import ctypes
        ok = True
        for name in ("ZenMaruGothic-Regular.ttf", "ZenMaruGothic-Medium.ttf",
                     "ZenMaruGothic-Bold.ttf", "JetBrainsMono-Regular.ttf"):
            path = resource_path("assets", "fonts", name)
            ok &= ctypes.windll.gdi32.AddFontResourceExW(path, 0x10, 0) > 0  # FR_PRIVATE
        return ok
    except Exception:
        return False


def short_path(path):
    """reports/<file> relative to the toolkit folder, for display."""
    try:
        return os.path.join("reports", os.path.basename(path)).replace("\\", "/")
    except Exception:
        return str(path)


# ========= Windows window helpers =========

def _hwnd(root):
    import ctypes
    return ctypes.windll.user32.GetParent(root.winfo_id())


def show_in_taskbar(root):
    """A frameless Tk window is hidden from the taskbar by default; put it back."""
    if not WINDOWS:
        return
    try:
        import ctypes
        GWL_EXSTYLE, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = -20, 0x40000, 0x80
        hwnd = _hwnd(root)
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        root.withdraw()
        root.after(10, root.deiconify)
    except Exception:
        pass


def minimize(root):
    if WINDOWS:
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(_hwnd(root), 6)  # SW_MINIMIZE
            return
        except Exception:
            pass
    root.iconify()


def kill_tree(proc):
    """Stop a running command and anything it started."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            proc.kill()
    except Exception:
        pass


# ========= Static artwork =========

def paint_background():
    """The see-through key colour with the window frame, title bar and body on it."""
    S = 2  # supersample for smooth corners
    img = Image.new("RGB", (WIN_W * S, WIN_H * S), hex_rgb(KEY))
    d = ImageDraw.Draw(img)
    px0, py0, px1, py1 = PANEL_X, PANEL_Y, PANEL_X + PANEL_W, BY + BODY_H + BORDER
    d.rounded_rectangle([px0 * S, py0 * S, px1 * S - 1, py1 * S - 1], radius=16 * S, fill=hex_rgb(FRAME))
    ix0, iy0, ix1, iy1 = px0 + BORDER, py0 + BORDER, px1 - BORDER, py1 - BORDER
    d.rounded_rectangle([ix0 * S, iy0 * S, ix1 * S - 1, iy1 * S - 1], radius=14 * S, fill=hex_rgb(PAPER))
    d.rounded_rectangle([ix0 * S, iy0 * S, ix1 * S - 1, (iy0 + BAR_H + 20) * S], radius=14 * S, fill=hex_rgb(BAR))
    d.rectangle([ix0 * S, (iy0 + BAR_H) * S, ix1 * S - 1, BY * S - 1], fill=hex_rgb(LINE))
    d.rectangle([ix0 * S, BY * S, ix1 * S - 1, (BY + 30) * S], fill=hex_rgb(PAPER))
    img = img.resize((WIN_W, WIN_H), Image.LANCZOS)
    # resampling can leave soft pixels outside the frame; snap them back to the key
    outside = Image.new("L", (WIN_W, WIN_H), 255)
    ImageDraw.Draw(outside).rounded_rectangle([px0, py0, px1 - 1, py1 - 1], radius=16, fill=0)
    img.paste(hex_rgb(KEY), (0, 0), outside)
    return img


def crop_padded(img, x, y, w, h, fill):
    out = Image.new("RGB", (w, h), fill)
    out.paste(img.crop((max(x, 0), max(y, 0), x + w, y + h)), (max(-x, 0), max(-y, 0)))
    return out


class CatArt:
    """
    Renders the cat (asleep/awake cross-fade, breathing scale, drop shadow)
    as a solid image: over the window it is blended normally, over the
    see-through area its soft edges are cut to the key colour.
    """

    def __init__(self, background):
        def load(name):
            im = Image.open(resource_path("assets", name)).convert("RGBA")
            return im.resize((CAT_W, CAT_H), Image.LANCZOS)
        self.asleep = load("cat4-asleep.png")
        self.awake = load("cat4-awake.png")
        self.cache = OrderedDict()   # recently used frames, oldest first
        self.alpha = self.asleep.getchannel("A")
        W, H = CAT_W + 2 * CAT_PAD, CAT_H + 2 * CAT_PAD
        self.size = (W, H)
        key = hex_rgb(KEY)
        self.under = crop_padded(background, CAT_X - CAT_PAD, CAT_Y - CAT_PAD, W, H, key)
        self.key_img = Image.new("RGB", (W, H), key)
        self.outside = self.is_key(self.under)
        self.under_edge = self.under.copy()
        self.under_edge.paste(hex_rgb(FRAME), (0, 0), self.outside)

    def is_key(self, img):
        diff = ImageChops.difference(img, self.key_img).convert("L")
        return diff.point(lambda v: 255 if v == 0 else 0)

    def hit(self, x, y):
        """Is window point (x, y) on the cat itself (not its see-through surroundings)?"""
        lx, ly = int(x - CAT_X), int(y - CAT_Y)
        return 0 <= lx < CAT_W and 0 <= ly < CAT_H and self.alpha.getpixel((lx, ly)) > 100

    def frame(self, eyes_open, sx, sy):
        """
        eyes_open: 0 = asleep art, 1 = awake art; in between is a blend of the
        two, so the cat stays fully solid while its eyes open or close.
        """
        key = (round(eyes_open * 20) / 20, round(sx, 3), round(sy, 3))
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        eyes_open, sx, sy = key
        W, H = self.size
        if eyes_open <= 0:
            cat = self.asleep
        elif eyes_open >= 1:
            cat = self.awake
        else:
            cat = Image.blend(self.asleep, self.awake, eyes_open)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.alpha_composite(cat, (CAT_PAD, CAT_PAD))
        ox, oy = CAT_PAD + CAT_ORIGIN[0], CAT_PAD + CAT_ORIGIN[1]
        if (sx, sy) != (1, 1):
            # inverse affine: source = (dest - origin) / scale + origin
            layer = layer.transform((W, H), Image.AFFINE,
                                    (1 / sx, 0, ox - ox / sx, 0, 1 / sy, oy - oy / sy),
                                    resample=Image.BICUBIC)
        # drop-shadow(0 3px 3px rgba(70,45,25,.22)) - only lands on the window
        alpha = layer.getchannel("A")
        shadow = Image.new("RGBA", (W, H), (70, 45, 25, 0))
        shadow.putalpha(alpha.point(lambda v: round(v * .22)).filter(ImageFilter.GaussianBlur(1.5)))
        art = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        art.alpha_composite(shadow, (0, 3))
        art.alpha_composite(layer)

        out = self.under_edge.convert("RGBA")
        out.alpha_composite(art)
        out = out.convert("RGB")
        # never let a visible pixel match the key by accident
        out.paste((0x5a, 0x46, 0x38), (0, 0), self.is_key(out))
        see_through = ImageChops.multiply(self.outside, art.getchannel("A").point(lambda v: 255 if v < 128 else 0))
        out.paste(hex_rgb(KEY), (0, 0), see_through)

        photo = ImageTk.PhotoImage(out)
        self.cache[key] = photo
        # Drop the oldest frames, never the newest ones (one of them is on screen)
        while len(self.cache) > 400:
            self.cache.popitem(last=False)
        return photo

    def icon(self):
        face = self.awake.crop((40, 0, 220, 180)).resize((64, 64), Image.LANCZOS)
        return ImageTk.PhotoImage(face)


# ========= The app =========

class ToolkitApp:
    def __init__(self, root):
        self.root = root
        self.cv = tk.Canvas(root, width=WIN_W, height=WIN_H, highlightthickness=0, bd=0, bg=KEY)
        self.cv.pack()
        self.timers = []
        self.events = queue.Queue()

        self.pick_fonts()
        bg = paint_background()
        self.bg_rgb = bg
        self.bg_photo = ImageTk.PhotoImage(bg)
        self.cv.create_image(0, 0, image=self.bg_photo, anchor="nw")
        self.cat = CatArt(bg)
        self.icon = self.cat.icon()
        root.iconphoto(True, self.icon)

        # state (mirrors the design's component state)
        self.awake = False
        self.breath = False
        self.blink = False
        self.stare = False
        self.busy = False
        self.exited = False
        self.pressed = None
        self.log = ["Ready."]
        self.sleep_timer = None
        self.view = "menu"
        self.task = None        # {"k", "state": confirm|running|done|failed, ...}
        self.drag = None

        self.layout_body()
        self.draw_body()
        self.draw_task_view()

        # paw (drawn above the body, below the masks)
        self.paw_x, self.paw_y, self.paw_r = Tween(PAW_REST[0]), Tween(PAW_REST[1]), Tween(0.0)
        self.paw_items = self.make_paw()

        self.draw_masks()
        self.draw_title_bar()

        # cat
        self.a_asleep, self.a_awake = Tween(1.0), Tween(0.0)
        self.head_sx, self.head_sy = Tween(1.0), Tween(1.0)
        self.cat_key = None
        self.cat_item = self.cv.create_image(CAT_X - CAT_PAD, CAT_Y - CAT_PAD, anchor="nw")
        self.zzz = [self.cv.create_text(0, 0, text=t, anchor="nw", font=self.bold(s), fill=ZZZ_INK, state="hidden")
                    for t, s in (("z", 16), ("z", 20), ("Z", 24))]
        self.zzz_start = now_ms()
        self.cat_photo = None       # keep the frame on screen alive
        self.hearts = []
        self.pet_start = self.pet_until = 0.0
        self.press = None
        self.cv.tag_bind(self.cat_item, "<Motion>", self.cat_hover)
        self.cv.tag_bind(self.cat_item, "<Leave>", lambda e: self.cv.config(cursor=""))

        root.bind("<Key>", self.on_key)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.cv.bind("<ButtonPress-1>", self.drag_start, add="+")
        self.cv.bind("<B1-Motion>", self.drag_move, add="+")
        self.cv.bind("<ButtonRelease-1>", self.drag_end, add="+")
        self.breathe()
        self.schedule_blink()
        self.tick()

    # ----- fonts -----

    def pick_fonts(self):
        registered = register_fonts()
        fams = set(tkfont.families(self.root))

        def first(*names):
            for n in names:
                if n in fams:
                    return n
            return names[-1]

        ok = registered or "Zen Maru Gothic" in fams
        self.ui = "Zen Maru Gothic" if ok else first("Segoe UI", "Helvetica", "Arial")
        self.ui_med = ("Zen Maru Gothic Medium" if registered or "Zen Maru Gothic Medium" in fams
                       else self.ui)
        self.mono = ("JetBrains Mono" if registered or "JetBrains Mono" in fams
                     else first("Consolas", "DejaVu Sans Mono", "Courier New"))
        self.fonts = {}

    def font(self, family, px, weight="normal"):
        key = (family, px, weight)
        if key not in self.fonts:
            self.fonts[key] = tkfont.Font(root=self.root, family=family, size=-px, weight=weight)
        return self.fonts[key]

    def bold(self, px):
        return self.font(self.ui, px, "bold")

    # ----- layout -----

    def wrap(self, text, fnt, width):
        lines, cur = [], ""
        for word in text.split():
            trial = f"{cur} {word}".strip()
            if cur and fnt.measure(trial) > width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        return lines + ([cur] if cur else [])

    def layout_body(self):
        pad_x, pad_y, gap = 32, 28, 22
        self.title_y = pad_y
        self.sub_y = pad_y + 26 * 1.15 + 6
        grid_y = self.sub_y + 14 * 1.4 + gap
        self.grid_y = grid_y
        col_w = (BODY_W - 2 * pad_x - 16) / 2
        desc_font = self.font(self.ui, 14)
        cards = []
        for i, (k, title, desc, meta) in enumerate(TOOLS):
            lines = self.wrap(desc, desc_font, col_w - 40)
            h = max(118, 18 + 22 + 8 + len(lines) * 14 * 1.45 + 8 + 11 * 1.2 + 18)
            cards.append({"k": k, "title": title, "lines": lines, "meta": meta, "h": h})
        y = grid_y
        for row in (cards[0:2], cards[2:4]):
            row_h = max(c["h"] for c in row)
            for col, c in enumerate(row):
                c.update(x=pad_x + col * (col_w + 16), y=y, w=col_w, h=row_h)
            y += row_h + 16
        self.cards = cards
        bottom_y = y - 16 + gap
        self.exit_rect = (BODY_W - pad_x - 120, bottom_y, BODY_W - pad_x, BODY_H - pad_y)
        self.log_rect = (pad_x, bottom_y, BODY_W - pad_x - 120 - 16, BODY_H - pad_y)

    # ----- drawing: menu -----

    def body_bg_at(self, x, y):
        return self.bg_rgb.getpixel((int(BX + x), int(BY + y)))

    def hand_cursor(self, tag):
        self.cv.tag_bind(tag, "<Enter>", lambda e: self.cv.config(cursor="hand2"), add="+")
        self.cv.tag_bind(tag, "<Leave>", lambda e: self.cv.config(cursor=""), add="+")

    def draw_body(self):
        cv = self.cv
        cv.create_text(BX + 32, BY + self.title_y + 26 * 1.15 / 2, anchor="w", text="IT Diagnostic Toolkit",
                       fill=INK, font=self.bold(26))
        cv.create_text(BX + 32, BY + self.sub_y + 14 * 1.4 / 2, anchor="w", fill=INK_SOFT, font=self.font(self.ui, 14),
                       text="Basic system health checks, hardware scanning, and automated troubleshooting.")

        for i, c in enumerate(self.cards):
            c["dx"], c["dy"], c["r"], c["s"] = Tween(0.0), Tween(0.0), Tween(0.0), Tween(1.0)
            tag = f"card{i}"
            tags = (tag, "menu")
            c["tag"] = tag
            c["shadow"] = [cv.create_polygon(0, 0, 0, 0, 0, 0, outline="", tags=tags) for _ in range(3)]
            c["box"] = cv.create_polygon(0, 0, 0, 0, 0, 0, fill=CARD, outline=EDGE, width=1.5, tags=tags)
            c["badge"] = cv.create_polygon(0, 0, 0, 0, 0, 0, fill="", outline=LINE, width=1, tags=tags)
            c["texts"] = []
            # (local x, local centre y, text, font, colour, anchor)
            c["texts"].append((20, 18 + 11, c["title"], self.bold(16), INK, "w"))
            c["texts"].append((c["w"] - 20 - 11, 18 + 11, c["k"], self.font(self.mono, 12), INK_SOFT, "center"))
            for j, line in enumerate(c["lines"]):
                c["texts"].append((20, 48 + (j + 0.5) * 14 * 1.45, line, self.font(self.ui, 14), DESC, "w"))
            c["texts"].append((20, c["h"] - 18 - 11 * 1.2 / 2, c["meta"], self.font(self.mono, 11), META, "w"))
            c["text_items"] = [cv.create_text(0, 0, text=t[2], font=t[3], fill=t[4], anchor=t[5], tags=tags)
                               for t in c["texts"]]
            cv.tag_bind(tag, "<Button-1>", lambda e, k=c["k"]: self.pick(k))
            self.hand_cursor(tag)
            self.place_card(c)

        # activity log
        x0, y0, x1, y1 = self.log_rect
        cv.create_polygon(flat(self.at_body(rounded_points(x0, y0, x1, y1, 10, 10, 10, 10))),
                          fill=BAR, outline=LINE, width=1, tags="menu")
        cv.create_text(BX + x0 + 16, BY + y0 + 12 + 5.5, anchor="w", text="ACTIVITY",
                       fill=META, font=self.bold(11), tags="menu")
        self.log_items = [cv.create_text(BX + x0 + 16, BY + y0 + 12 + 11 + 6 + i * 22 + 9, anchor="w", text="",
                                         fill=LOG_INK, font=self.font(self.mono, 12), tags="menu")
                          for i in range(LOG_LINES)]
        self.log_width = x1 - x0 - 32
        self.render_log()

        # exit button
        self.exit_s = Tween(1.0)
        tags = ("exit", "menu")
        self.exit_box = cv.create_polygon(0, 0, 0, 0, 0, 0, fill=CARD, outline=EDGE, width=1, tags=tags)
        self.exit_badge = cv.create_polygon(0, 0, 0, 0, 0, 0, fill="", outline=LINE, width=1, tags=tags)
        self.exit_key = cv.create_text(0, 0, text="0", font=self.font(self.mono, 12), fill=INK_SOFT, tags=tags)
        self.exit_label = cv.create_text(0, 0, text="Exit", font=self.font(self.ui_med, 14), fill=INK, tags=tags)
        cv.tag_bind("exit", "<Button-1>", lambda e: self.pick("0"))
        self.hand_cursor("exit")
        self.place_exit()

    def at_body(self, pts):
        return [(BX + x, BY + y) for x, y in pts]

    def place_card(self, c, t=None):
        cv = self.cv
        x, y, w, h = c["x"], c["y"], c["w"], c["h"]
        dx, dy, r, s = c["dx"].get(t), c["dy"].get(t), c["r"].get(t), c["s"].get(t)
        f = transformer(BX + x + w / 2, BY + y + h / 2, dx, dy, r, s)

        def shape(x0, y0, x1, y1, rad, ox=0.0, oy=0.0):
            return flat(f(BX + px + ox, BY + py + oy) for px, py in rounded_points(x0, y0, x1, y1, rad, rad, rad, rad))

        pressed = self.pressed == c["k"]
        bg = self.body_bg_at(x - 4, y - 4)
        if pressed:
            layers = [(3, 0, mix(bg, ACCENT, .25))]
        elif abs(c["r"].v1) > 0.01:
            shadow_ink = (40, 30, 20)
            layers = [(6, 6, mix(bg, shadow_ink, .03)), (3, 6, mix(bg, shadow_ink, .06)), (0, 6, mix(bg, shadow_ink, .09))]
        else:
            layers = [(0.5, 1, mix(bg, (40, 30, 20), .05))]
        visible = "normal" if self.view == "menu" else "hidden"
        for i, item in enumerate(c["shadow"]):
            if i < len(layers):
                grow, off, colour = layers[i]
                cv.coords(item, shape(x - grow, y - grow, x + w + grow, y + h + grow, 14 + grow, 0, off))
                cv.itemconfig(item, fill=colour, state=visible)
            else:
                cv.itemconfig(item, state="hidden")
        cv.coords(c["box"], shape(x, y, x + w, y + h, 14))
        cv.itemconfig(c["box"], outline=ACCENT if pressed else EDGE)
        bx = x + w - 20 - 22
        cv.coords(c["badge"], shape(bx, y + 18, bx + 22, y + 40, 5))
        for item, (lx, ly, *_rest) in zip(c["text_items"], c["texts"]):
            cv.coords(item, *f(BX + x + lx, BY + y + ly))
            cv.itemconfig(item, angle=-r)

    def place_exit(self, t=None):
        x0, y0, x1, y1 = self.exit_rect
        s = self.exit_s.get(t)
        f = transformer(BX + (x0 + x1) / 2, BY + (y0 + y1) / 2, scale=s)
        cv = self.cv
        cv.coords(self.exit_box, flat(f(BX + px, BY + py) for px, py in rounded_points(x0, y0, x1, y1, 14, 14, 14, 14)))
        label_w = self.font(self.ui_med, 14).measure("Exit")
        left = (x0 + x1) / 2 - (22 + 10 + label_w) / 2
        cy = (y0 + y1) / 2
        cv.coords(self.exit_badge, flat(f(BX + px, BY + py) for px, py in
                                        rounded_points(left, cy - 11, left + 22, cy + 11, 5, 5, 5, 5)))
        cv.coords(self.exit_key, *f(BX + left + 11, BY + cy))
        cv.coords(self.exit_label, *f(BX + left + 32 + label_w / 2, BY + cy))

    def render_log(self):
        fnt = self.font(self.mono, 12)
        for item, line in zip(self.log_items, self.log[-LOG_LINES:] + [""] * LOG_LINES):
            if fnt.measure(line) > self.log_width:
                while line and fnt.measure("…" + line) > self.log_width:
                    line = line[1:]
                line = "…" + line
            self.cv.itemconfig(item, text=line)

    # ----- drawing: task view (tool output inside the window) -----

    def make_button(self, tag, label, primary):
        cv = self.cv
        tags = (tag, "task")
        fnt = self.font(self.ui_med, 14)
        w = fnt.measure(label) + 36
        b = {"tag": tag, "w": w, "primary": primary,
             "box": cv.create_polygon(0, 0, 0, 0, 0, 0, fill=ACCENT if primary else CARD,
                                      outline=ACCENT if primary else EDGE, width=1, tags=tags),
             "text": cv.create_text(0, 0, text=label, font=fnt, fill="#ffffff" if primary else INK, tags=tags)}
        normal, hover = (ACCENT, ACCENT_HOVER) if primary else (CARD, BAR)
        cv.tag_bind(tag, "<Enter>", lambda e: (cv.itemconfig(b["box"], fill=hover), cv.config(cursor="hand2")))
        cv.tag_bind(tag, "<Leave>", lambda e: (cv.itemconfig(b["box"], fill=normal), cv.config(cursor="")))
        return b

    def place_buttons(self, buttons):
        """Right-align the given buttons on the task view's bottom row; hide the rest."""
        x1, y0, y1 = BODY_W - 32, BODY_H - 28 - 38, BODY_H - 28
        shown = set()
        for b in reversed(buttons):
            x0 = x1 - b["w"]
            self.cv.coords(b["box"], flat(self.at_body(rounded_points(x0, y0, x1, y1, 10, 10, 10, 10))))
            self.cv.coords(b["text"], BX + (x0 + x1) / 2, BY + (y0 + y1) / 2)
            shown.add(b["tag"])
            x1 = x0 - 10
        for b in self.buttons.values():
            state = "normal" if b["tag"] in shown and self.view == "task" else "hidden"
            self.cv.itemconfig(b["tag"], state=state)

    def draw_task_view(self):
        cv = self.cv
        x0, x1 = 32, BODY_W - 32
        y0 = self.grid_y
        self.task_box = (x0, y0 + 76, x1, BODY_H - 28 - 38 - 14)
        tags = ("task",)
        self.task_title = cv.create_text(BX + x0, BY + y0 + 12, anchor="w", text="", fill=INK,
                                         font=self.bold(18), tags=tags)
        self.task_status = cv.create_text(BX + x1, BY + y0 + 12, anchor="e", text="", fill=INK_SOFT,
                                          font=self.font(self.mono, 12), tags=tags)
        # progress bar
        self.prog_rect = (x0, y0 + 34, x1, y0 + 44)
        px0, py0, px1, py1 = self.prog_rect
        cv.create_polygon(flat(self.at_body(rounded_points(px0, py0, px1, py1, 5, 5, 5, 5))),
                          fill=BAR, outline=LINE, width=1, tags=tags)
        self.prog_fill = cv.create_polygon(0, 0, 0, 0, 0, 0, fill=ACCENT, outline="", tags=tags)
        self.prog_value = None   # 0..100, or None for "working..." sweep
        self.task_step = cv.create_text(BX + x0, BY + y0 + 60, anchor="w", text="", fill=DESC,
                                        font=self.font(self.ui, 14), tags=tags)
        # output box
        bx0, by0, bx1, by1 = self.task_box
        cv.create_polygon(flat(self.at_body(rounded_points(bx0, by0, bx1, by1, 10, 10, 10, 10))),
                          fill=BAR, outline=LINE, width=1, tags=tags)
        self.text = tk.Text(cv, bg=BAR, fg=LOG_INK, font=self.font(self.mono, 12), relief="flat", bd=0,
                            highlightthickness=0, wrap="word", padx=0, pady=0, cursor="arrow",
                            selectbackground=mix(BAR, ACCENT, .45), inactiveselectbackground=mix(BAR, ACCENT, .3),
                            spacing1=2, spacing3=2, takefocus=0)
        self.text.config(state="disabled", yscrollcommand=self.on_text_scroll)
        self.text.tag_config("head", foreground=INK, font=self.font(self.mono, 12, "bold"))
        self.text.tag_config("warn", foreground="#b0412e")
        self.text_win = cv.create_window(BX + bx0 + 16, BY + by0 + 12, anchor="nw", window=self.text,
                                         width=bx1 - bx0 - 16 - 26, height=by1 - by0 - 24, state="hidden")
        # slim scrollbar
        self.sb_track = (bx1 - 14, by0 + 12, bx1 - 8, by1 - 12)
        self.sb_thumb = cv.create_polygon(0, 0, 0, 0, 0, 0, fill=EDGE, outline="", tags=("task", "sb"))
        cv.tag_bind("sb", "<ButtonPress-1>", self.sb_press)
        cv.tag_bind("sb", "<B1-Motion>", self.sb_drag)
        self.sb_span = (0.0, 1.0)
        # bottom row
        self.task_note = cv.create_text(BX + x0, BY + BODY_H - 28 - 19, anchor="w", text="", fill=META,
                                        font=self.font(self.mono, 11), tags=tags)
        self.buttons = {
            "start": self.make_button("btn_start", "Start repair", True),
            "cancel": self.make_button("btn_cancel", "Cancel", False),
            "back": self.make_button("btn_back", "Back to tools", True),
        }
        cv.tag_bind("btn_start", "<Button-1>", lambda e: self.start_repair())
        cv.tag_bind("btn_cancel", "<Button-1>", lambda e: self.close_task())
        cv.tag_bind("btn_back", "<Button-1>", lambda e: self.close_task())
        cv.itemconfig("task", state="hidden")

    def set_progress(self, value):
        self.prog_value = value
        self.draw_progress()

    def draw_progress(self, t=None):
        px0, py0, px1, py1 = self.prog_rect
        w = px1 - px0
        if self.prog_value is None:
            # back-and-forth sweep while we can't tell how far along we are
            p = (now_ms() if t is None else t) % 1800 / 1800
            p = EASE_IN_OUT(p * 2 if p < .5 else 2 - p * 2)
            seg = w * .22
            a = px0 + (w - seg) * p
            b = a + seg
        else:
            a, b = px0, px0 + max(10, w * max(0, min(100, self.prog_value)) / 100)
        visible = self.view == "task" and self.prog_value != 0
        self.cv.itemconfig(self.prog_fill, state="normal" if visible else "hidden")
        self.cv.coords(self.prog_fill, flat(self.at_body(rounded_points(a, py0, b, py1, 5, 5, 5, 5))))

    def on_text_scroll(self, first, last):
        self.sb_span = (float(first), float(last))
        tx0, ty0, tx1, ty1 = self.sb_track
        f, l = self.sb_span
        if l - f >= 0.999:
            self.cv.itemconfig(self.sb_thumb, state="hidden")
            return
        h = ty1 - ty0
        a, b = ty0 + h * f, max(ty0 + h * f + 24, ty0 + h * l)
        self.cv.coords(self.sb_thumb, flat(self.at_body(rounded_points(tx0, a, tx1, b, 3, 3, 3, 3))))
        if self.view == "task":
            self.cv.itemconfig(self.sb_thumb, state="normal")

    def sb_press(self, e):
        self.sb_grab = (e.y, self.sb_span[0])

    def sb_drag(self, e):
        y_start, f0 = self.sb_grab
        ty0, ty1 = self.sb_track[1], self.sb_track[3]
        self.text.yview_moveto(f0 + (e.y - y_start) / (ty1 - ty0))

    def text_write(self, line, tag=None, replace=False):
        at_end = self.sb_span[1] >= 0.999
        self.text.config(state="normal")
        if replace:
            self.text.delete("1.0", "end")
        self.text.insert("end", line + "\n", tag or ())
        self.text.config(state="disabled")
        if at_end or replace:
            self.text.see("end" if not replace else "1.0")

    # ----- drawing: paw, masks, title bar -----

    def make_paw(self):
        cv = self.cv
        shadow = cv.create_polygon(0, 0, 0, 0, 0, 0, fill=mix(PAPER, (90, 55, 25), .10), outline="")
        body = cv.create_polygon(0, 0, 0, 0, 0, 0, fill=PAW_FUR, outline=PAW_LINE, width=1.5)
        pads = [cv.create_polygon(0, 0, 0, 0, 0, 0, fill=PAD_PINK, outline="") for _ in range(4)]
        items = {"shadow": shadow, "body": body, "pads": pads}
        self.place_paw(items)
        return items

    def place_paw(self, items=None, t=None):
        items = items or self.paw_items
        x, y, r = self.paw_x.get(t), self.paw_y.get(t), self.paw_r.get(t)
        left, top = BX + x - PAW_W / 2, BY + y - PAW_H
        f = transformer(left + PAW_W / 2, top, 0, 0, r)

        def pts(local):
            return flat(f(left + px, top + py) for px, py in local)
        outline = rounded_points(0, 0, PAW_W, PAW_H, 20, 20, 40, 40)
        self.cv.coords(items["body"], pts(outline))
        self.cv.coords(items["shadow"], pts([(px, py + 6) for px, py in outline]))
        pads = [(22, PAW_H - 62, 58, PAW_H - 34), (10, PAW_H - 28, 26, PAW_H - 12),
                (32, PAW_H - 22, 48, PAW_H - 6), (54, PAW_H - 28, 70, PAW_H - 12)]
        for item, box in zip(items["pads"], pads):
            self.cv.coords(item, pts(ellipse_points(*box)))

    def draw_masks(self):
        """Repaint everything outside the body so the paw is clipped to the window body."""
        self.masks = []
        regions = [(0, 0, WIN_W, BY), (0, BY, BX, BY + BODY_H), (BX + BODY_W, BY, WIN_W, BY + BODY_H),
                   (0, BY + BODY_H, WIN_W, WIN_H)]
        for x0, y0, x1, y1 in regions:
            photo = ImageTk.PhotoImage(self.bg_rgb.crop((x0, y0, x1, y1)))
            self.masks.append(photo)
            self.cv.create_image(x0, y0, image=photo, anchor="nw")

    def draw_title_bar(self):
        cv = self.cv
        cy = PANEL_Y + BORDER + BAR_H / 2
        x = PANEL_X + BORDER + 18
        title_font = self.bold(13)
        cv.create_text(x, cy, anchor="w", text="IT Toolkit", fill=INK, font=title_font)
        x += title_font.measure("IT Toolkit") + 10
        role = "Administrator" if launcher.is_admin() else "Standard user"
        mono11 = self.font(self.mono, 11)
        w = mono11.measure(role) + 16
        cv.create_polygon(flat(rounded_points(x, cy - 10, x + w, cy + 10, 10, 10, 10, 10)),
                          fill="", outline=EDGE, width=1)
        cv.create_text(x + 8, cy, anchor="w", text=role, fill=DESC, font=mono11)

        # window controls: minimise, maximise (fixed-size window, so dimmed), close
        right = PANEL_X + PANEL_W - BORDER - 8
        self.ctrl_left = right - 3 * CTRL_W - 2 * CTRL_GAP
        cv.create_text(self.ctrl_left - 10, cy, anchor="e", text=VERSION, fill=INK_SOFT, font=mono11)
        glyph = INK_SOFT
        for i, name in enumerate(("min", "max", "close")):
            x0 = self.ctrl_left + i * (CTRL_W + CTRL_GAP)
            x1, y0, y1 = x0 + CTRL_W, cy - CTRL_H / 2, cy + CTRL_H / 2
            tag = f"ctrl_{name}"
            bg = cv.create_polygon(flat(rounded_points(x0, y0, x1, y1, 6, 6, 6, 6)), fill=BAR, outline="", tags=tag)
            mx, my = (x0 + x1) / 2, cy
            if name == "min":
                marks = [cv.create_line(mx - 5, my, mx + 5, my, fill=glyph, width=1.2, tags=tag)]
            elif name == "max":
                marks = [cv.create_rectangle(mx - 5, my - 5, mx + 5, my + 5, outline=mix(BAR, glyph, .35),
                                             width=1.2, tags=tag)]
            else:
                marks = [cv.create_line(mx - 5, my - 5, mx + 5, my + 5, fill=glyph, width=1.3, tags=tag),
                         cv.create_line(mx - 5, my + 5, mx + 5, my - 5, fill=glyph, width=1.3, tags=tag)]
            if name == "max":
                continue
            hover_bg, hover_ink = (CLOSE_HOVER, "#ffffff") if name == "close" else (BAR_HOVER, INK)

            def enter(e, bg=bg, marks=marks, hb=hover_bg, hi=hover_ink):
                cv.itemconfig(bg, fill=hb)
                for m in marks:
                    cv.itemconfig(m, fill=hi)

            def leave(e, bg=bg, marks=marks):
                cv.itemconfig(bg, fill=BAR)
                for m in marks:
                    cv.itemconfig(m, fill=glyph)
            cv.tag_bind(tag, "<Enter>", enter)
            cv.tag_bind(tag, "<Leave>", leave)
        cv.tag_bind("ctrl_min", "<ButtonRelease-1>", lambda e: minimize(self.root))
        cv.tag_bind("ctrl_close", "<ButtonRelease-1>", lambda e: self.close())

    # ----- moving the frameless window -----

    def drag_start(self, e):
        on_controls = e.x >= self.ctrl_left - 4 and PANEL_Y <= e.y <= BY
        if e.y < BY and not on_controls:
            self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self.press = (e.x_root, e.y_root) if self.cat.hit(e.x, e.y) else None
        self.root.focus_force()

    def drag_end(self, e):
        self.drag = None
        # a click on the cat that didn't move the window is a pet
        if self.press and abs(e.x_root - self.press[0]) < 5 and abs(e.y_root - self.press[1]) < 5:
            self.pet(e.x, e.y)
        self.press = None

    def cat_hover(self, e):
        self.cv.config(cursor="hand2" if self.cat.hit(e.x, e.y) else "")

    def drag_move(self, e):
        if self.drag:
            dx, dy = self.drag
            self.root.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    # ----- animation loop -----

    def tick(self):
        t = now_ms()
        for c in self.cards:
            if any(c[k].moving(t) or c.get("dirty") for k in ("dx", "dy", "r", "s")):
                c["dirty"] = any(c[k].moving(t) for k in ("dx", "dy", "r", "s"))
                self.place_card(c, t)
        if self.exit_s.moving(t) or getattr(self, "exit_dirty", False):
            self.exit_dirty = self.exit_s.moving(t)
            self.place_exit(t)
        if any(tw.moving(t) for tw in (self.paw_x, self.paw_y, self.paw_r)) or getattr(self, "paw_dirty", False):
            self.paw_dirty = any(tw.moving(t) for tw in (self.paw_x, self.paw_y, self.paw_r))
            self.place_paw(t=t)
        if self.view == "task" and self.prog_value is None:
            self.draw_progress(t)
        self.draw_cat(t)
        self.draw_zzz(t)
        self.draw_hearts(t)
        self.drain_events()
        self.root.after(16, self.tick)

    def draw_cat(self, t):
        a_asleep, a_awake = self.a_asleep.get(t), self.a_awake.get(t)
        eyes_open = a_awake / (a_awake + a_asleep) if a_awake + a_asleep > 0 else 0.0
        sx, sy = self.head_sx.get(t), self.head_sy.get(t)
        if t < self.pet_until:
            # leans into the hand: a soft squash-and-stretch bob that settles at the end
            settle = min(1.0, (self.pet_until - t) / 500)
            bob = math.sin((t - self.pet_start) / 420 * 2 * math.pi) * 0.022 * settle
            sx, sy = sx * (1 + bob * 0.6), sy * (1 - bob)
        key = (round(eyes_open * 20) / 20, round(sx, 3), round(sy, 3))
        if key != self.cat_key:
            self.cat_key = key
            self.cat_photo = self.cat.frame(*key)
            self.cv.itemconfig(self.cat_item, image=self.cat_photo)

    def draw_zzz(self, t):
        if self.awake:
            for item in self.zzz:
                self.cv.itemconfig(item, state="hidden")
            return
        elapsed = t - self.zzz_start
        for item, (ox, oy, delay) in zip(self.zzz, ((0, 10, 0), (10, 0, 800), (22, -12, 1600))):
            if elapsed < delay:
                self.cv.itemconfig(item, state="hidden")
                continue
            p = ((elapsed - delay) % 2400) / 2400
            opacity = EASE_IN_OUT(p / .3) if p < .3 else 1 - EASE_IN_OUT((p - .3) / .7)
            m = EASE_IN_OUT(p)
            # floating over the see-through area, so fade by showing only the brighter part
            self.cv.coords(item, ZZZ_X + ox + 10 * m, ZZZ_Y + oy + 6 - 20 * m)
            self.cv.itemconfig(item, state="normal" if opacity > .3 else "hidden")

    # ----- petting -----

    def petting(self, t=None):
        return (now_ms() if t is None else t) < self.pet_until

    def pet(self, x, y):
        t = now_ms()
        if not self.petting(t):
            self.pet_start = t
        self.pet_until = t + 1600
        for i in range(3):
            self.spawn_heart(x, y, delay=i * 140)
        self.update_cat()
        self.root.after(1650, self.update_cat)   # open the eyes again afterwards
        if self.busy and self.view == "menu":
            self.set_awake(True)                 # the paw choreography decides when to nap
        else:
            self.nudge_cat(3500)

    def spawn_heart(self, x, y, delay=0):
        if len(self.hearts) >= 15:
            return
        cx = CAT_X + CAT_W / 2
        x = min(max(x + random.uniform(-30, 30), cx - 100), cx + 100)
        heart = {
            "x": x, "y": min(y, CAT_Y + 120) - 10,
            "rise": random.uniform(80, 120), "sway": random.uniform(6, 14),
            "size": random.uniform(9, 13), "t0": now_ms() + delay, "dur": random.uniform(1300, 1700),
            "phase": random.uniform(0, 2 * math.pi),
            "item": self.cv.create_polygon(0, 0, 0, 0, 0, 0, fill="#f07a93", outline="#c9566f",
                                           width=1, smooth=True, state="hidden"),
        }
        self.hearts.append(heart)

    def draw_hearts(self, t):
        for h in list(self.hearts):
            p = (t - h["t0"]) / h["dur"]
            if p < 0:
                continue
            if p >= 1:
                self.cv.delete(h["item"])
                self.hearts.remove(h)
                continue
            # pop in with a little overshoot, float up and sway, then shrink away
            # (the space around the cat is see-through, so hearts shrink instead of fading)
            if p < .18:
                grow = SPRING(p / .18)
            elif p > .7:
                grow = 1 - EASE_IN_OUT((p - .7) / .3)
            else:
                grow = 1.0
            r = h["size"] * max(grow, 0.01) / 16
            cx = h["x"] + math.sin(p * 2 * math.pi * 0.9 + h["phase"]) * h["sway"]
            cy = h["y"] - h["rise"] * cubic_bezier(.2, .6, .4, 1)(p)
            pts = []
            for i in range(24):
                a = 2 * math.pi * i / 24
                hx = 16 * math.sin(a) ** 3
                hy = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)
                pts += [cx + hx * r, cy - hy * r]
            self.cv.coords(h["item"], pts)
            self.cv.itemconfig(h["item"], state="normal")
            self.cv.tag_raise(h["item"])

    # ----- cat moods -----

    def update_cat(self):
        open_eyes = self.awake and not self.blink and not self.petting()
        self.a_asleep.set(0.0 if open_eyes else 1.0, 180, EASE)
        self.a_awake.set(1.0 if open_eyes else 0.0, 180, EASE)
        if self.awake:
            sx, sy = (1.02, 1.025) if self.stare else (1.01, 1.015)
            dur, ease = 450, HEAD_WAKE
        else:
            sx, sy = 1.0, (1.014 if self.breath else 1.0)
            dur, ease = 1600, HEAD_BREATHE
        self.head_sx.set(sx, dur, ease)
        self.head_sy.set(sy, dur, ease)

    def set_awake(self, awake):
        if awake == self.awake:
            return
        self.awake = awake
        if not awake:
            self.zzz_start = now_ms()
        self.update_cat()

    def nudge_cat(self, nap_after_ms):
        """Wake the cat and let it doze off again after a while."""
        if self.sleep_timer:
            self.root.after_cancel(self.sleep_timer)
        self.set_awake(True)
        self.sleep_timer = self.root.after(nap_after_ms, lambda: self.set_awake(False))

    def breathe(self):
        self.breath = not self.breath
        self.update_cat()
        self.root.after(1600, self.breathe)

    def schedule_blink(self):
        def blink():
            if self.awake:
                self.blink = True
                self.update_cat()
                self.root.after(150, unblink)
            self.schedule_blink()

        def unblink():
            self.blink = False
            self.update_cat()
        self.root.after(int(1800 + random.random() * 2200), blink)

    # ----- choreography -----

    def at(self, ms, fn):
        self.timers.append(self.root.after(int(ms), fn))

    def move_paw(self, x, y, r):
        self.paw_x.set(x, 380, PAW_MOVE)
        self.paw_y.set(y, 380, PAW_MOVE)
        self.paw_r.set(r, 220, EASE)

    def set_pressed(self, k):
        self.pressed = k
        for c in self.cards:
            c["s"].set(0.97 if c["k"] == k else 1.0, 280, SPRING)
            c["dirty"] = True
        self.exit_s.set(0.96 if k == "0" else 1.0, 280, SPRING)
        self.exit_dirty = True

    def push_log(self, line):
        self.log = (self.log + [line])[-LOG_LINES:]
        self.render_log()

    def on_key(self, e):
        if self.view == "task":
            state = self.task["state"] if self.task else None
            if e.keysym == "Return" and state == "confirm":
                self.start_repair()
            elif e.keysym == "Escape" and state in ("confirm", "done", "failed"):
                self.close_task()
            return
        if e.char in ("0", "1", "2", "3", "4"):
            self.pick(e.char)

    def pick(self, k):
        if self.busy or self.exited or self.view != "menu":
            return
        n = max(0, min(3, MISCHIEF))
        is_exit = k == "0"
        ci = next((i for i, c in enumerate(self.cards) if c["k"] == k), -1)
        if is_exit:
            x0, y0, x1, y1 = self.exit_rect
            R0 = (x0, y0, x1 - x0, y1 - y0)
        else:
            c = self.cards[ci]
            R0 = (c["x"], c["y"], c["w"], c["h"])
        hide_x = self.paw_x.v1
        if self.sleep_timer:
            self.root.after_cancel(self.sleep_timer)
            self.sleep_timer = None
        self.busy = True
        self.set_awake(True)

        t = 700
        others = [i for i in range(len(self.cards)) if i != ci]
        random.shuffle(others)
        for i in others[:n]:
            c = self.cards[i]
            direction = random.choice((-1, 1))
            sx = c["x"] + c["w"] * (0.25 if direction > 0 else 0.75)
            t += 80
            self.at(t, lambda sx=sx, c=c, d=direction: self.move_paw(sx, c["y"] + 16, d * 8))

            def swat(c=c, d=direction, sx=sx):
                c["dx"].set(c["dx"].v1 + d * (12 + random.random() * 18), 280, SPRING)
                c["dy"].set(-2 - random.random() * 6, 280, SPRING)
                c["r"].set(d * (2 + random.random() * 4), 280, SPRING)
                c["dirty"] = True
                self.move_paw(sx + d * c["w"] * 0.35, c["y"] + 22, -d * 14)
            t += 420
            self.at(t, swat)
            t += 240
            self.at(t, lambda c=c: self.move_paw(self.paw_x.v1, c["y"] - 30, 0))

        cx = R0[0] + R0[2] / 2
        t += 120
        self.at(t, lambda: self.move_paw(cx, R0[1] - 50, 0))

        def stare():
            self.stare = True
            self.update_cat()
            self.move_paw(cx, R0[1] - 20, 0)
        t += 420
        self.at(t, stare)
        t += 650
        self.at(t, lambda: (self.move_paw(cx, R0[1] + R0[3] * 0.45, 0), self.set_pressed(k)))

        def lift():
            self.move_paw(hide_x, PAW_REST[1], 0)
            self.stare = False
            self.update_cat()
        t += 300
        self.at(t, lift)
        t += 150
        self.at(t, lambda: self.run_tool(k))

    def reset_cards(self):
        for c in self.cards:
            for key in ("dx", "dy", "r"):
                c[key].set(0.0, 280, SPRING)
            c["dirty"] = True
        self.set_pressed(None)

    def back_to_menu(self):
        self.busy = False
        self.reset_cards()
        self.nudge_cat(1400)

    # ----- switching views -----

    def show_view(self, view):
        self.view = view
        self.cv.itemconfig("menu", state="normal" if view == "menu" else "hidden")
        self.cv.itemconfig("task", state="normal" if view == "task" else "hidden")
        self.cv.itemconfig(self.text_win, state="normal" if view == "task" else "hidden")
        if view == "menu":
            for c in self.cards:
                self.place_card(c)   # restores the right shadow layers
        else:
            self.on_text_scroll(*self.sb_span)

    def open_task(self, k, title):
        self.task = {"k": k, "state": "confirm", "title": title}
        self.reset_cards()
        self.cv.itemconfig(self.task_title, text=title)
        self.cv.itemconfig(self.task_note, text="")
        self.show_view("task")

    def set_task_state(self, state, status, step="", note=""):
        self.task["state"] = state
        self.cv.itemconfig(self.task_status, text=status, fill="#b0412e" if state == "failed" else INK_SOFT)
        self.cv.itemconfig(self.task_step, text=step)
        self.cv.itemconfig(self.task_note, text=note)
        buttons = {"confirm": ["cancel", "start"], "running": [], "done": ["back"], "failed": ["back"]}[state]
        self.place_buttons([self.buttons[b] for b in buttons])

    def close_task(self):
        if not self.task or self.task["state"] == "running":
            return
        self.task = None
        self.show_view("menu")
        self.back_to_menu()

    # ----- the real tools -----

    def run_tool(self, k):
        if k == "0":
            self.show_goodbye()
            return
        if k == "1":
            self.start_hardware_scan()
            return
        if k == "2":
            self.open_task("2", "System File Repair")
            self.set_progress(0)
            self.text_write(REPAIR_INTRO, replace=True)
            self.set_task_state("confirm", "Ready", "DISM + SFC · 4 steps")
            self.nudge_cat(4000)
            return

        if k == "3":
            lines = ["Opening Reliability Monitor..."]
            try:
                launcher.shell_open("perfmon.exe", "/rel")
            except Exception as e:
                lines.append(f"[!] Failed to open Reliability Monitor: {e}")
        else:
            lines = ["Opening Event Viewer..."]
            try:
                launcher.shell_open("eventvwr.msc")
            except Exception as e:
                lines.append(f"[!] Failed to open Event Viewer: {e}")

        self.push_log(lines[0])
        for j, line in enumerate(lines[1:]):
            self.at(500 + j * 500, lambda line=line: self.push_log(line))
        last = 500 * len(lines)
        self.at(last, lambda: self.push_log(RETURN_LINE))
        self.at(last + 3000, self.back_to_menu)

    def start_hardware_scan(self):
        self.push_log("=== Hardware Scan Tool ===")
        self.open_task("1", "Hardware Scan")
        self.set_progress(None)
        self.text_write("Collecting system information...", replace=True)
        self.set_task_state("running", "Scanning…", "CPU, GPU, RAM, BIOS, Secure Boot and disk health")
        self.nudge_cat(6000)

        def work():
            try:
                path = hardware_scan.run_hardware_scan()
                with open(path, encoding="utf-8") as f:
                    report = f.read()
                self.events.put(("scan_done", path, report))
            except Exception as e:
                self.events.put(("scan_failed", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def start_repair(self):
        if not self.task or self.task["state"] != "confirm":
            return
        self.text_write("Starting System File Repair (DISM + SFC)...", replace=True)
        self.set_progress(None)
        self.set_task_state("running", "Running…", "Preparing")
        self.push_log("System File Repair started.")
        self.nudge_cat(6000)
        q = self.events

        def work():
            try:
                path = fix_corrupted.run_fix_corrupted(
                    on_step=lambda i, n, cmd: q.put(("repair_step", i, n)),
                    on_progress=lambda p: q.put(("repair_progress", p)),
                    on_message=lambda m: q.put(("repair_line", m)),
                )
                q.put(("repair_done", path))
            except Exception as e:
                q.put(("repair_failed", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def drain_events(self):
        for _ in range(200):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            kind, args = event[0], event[1:]
            if kind == "scan_done":
                path, report = args
                self.set_progress(100)
                self.text.config(state="normal")
                self.text.delete("1.0", "end")
                for line in report.splitlines():
                    head = line.startswith("===")
                    self.text.insert("end", line + "\n", "head" if head else ())
                self.text.config(state="disabled")
                self.text.see("1.0")
                self.set_task_state("done", "Finished", "Hardware scan completed.",
                                    f"Saved to {short_path(path)}")
                self.push_log(f"Report saved to {short_path(path)}")
                self.nudge_cat(4000)
            elif kind == "scan_failed":
                self.set_progress(0)
                self.text_write(f"[!] Hardware scan failed: {args[0]}", "warn")
                self.set_task_state("failed", "Failed", "The scan stopped with an error.")
                self.push_log("[!] Hardware scan failed.")
                self.nudge_cat(4000)
            elif kind == "repair_step":
                i, n = args
                self.set_progress(None)
                self.cv.itemconfig(self.task_step, text=f"Step {i + 1} of {n} · {REPAIR_STEPS[i]}")
                self.cv.itemconfig(self.task_status, text=f"Running · {i + 1}/{n}")
            elif kind == "repair_progress":
                self.set_progress(args[0])
            elif kind == "repair_line":
                text = args[0].strip("\n")
                if text.strip():
                    tag = "head" if text.lstrip().startswith(("===", "Windows Resource Protection")) else None
                    self.text_write(text.strip(), tag)
            elif kind == "repair_done":
                path = args[0]
                self.set_progress(100)
                self.set_task_state("done", "Finished", "All health checks finished.", f"Saved to {short_path(path)}")
                self.push_log(f"System File Repair finished. Report saved to {short_path(path)}")
                self.nudge_cat(4000)
            elif kind == "repair_failed":
                self.text_write(f"\nAn unexpected error occurred: {args[0]}", "warn")
                self.set_task_state("failed", "Failed", "The repair stopped with an error.")
                self.push_log("[!] System File Repair stopped with an error.")
                self.nudge_cat(4000)

    # ----- leaving -----

    def show_goodbye(self):
        self.exited = True
        self.push_log("Exiting IT Toolkit. Goodbye!")
        veil = Image.new("RGBA", (BODY_W, BODY_H), (250, 248, 245, 0))
        ImageDraw.Draw(veil).rounded_rectangle([0, -20, BODY_W - 1, BODY_H - 1], radius=14,
                                               fill=(250, 248, 245, round(255 * .94)))
        self.veil = ImageTk.PhotoImage(veil)
        self.cv.create_image(BX, BY, image=self.veil, anchor="nw")
        self.cv.create_text(BX + BODY_W / 2, BY + BODY_H / 2, text="Exiting IT Toolkit. Goodbye!",
                            fill=INK, font=self.bold(20))
        self.root.after(1500, self.close, True)

    def close(self, force=False):
        running = self.task and self.task["state"] == "running"
        if running and not force:
            if self.task["k"] == "2":
                question = "System File Repair is still running.\n\nStop it and close the IT Toolkit?"
            else:
                question = "The hardware scan is still running.\n\nClose the IT Toolkit anyway?"
            if not messagebox.askyesno("IT Toolkit", question, parent=self.root, icon="warning"):
                return
        kill_tree(fix_corrupted.current_process)
        self.root.destroy()


def run():
    root = tk.Tk()
    root.withdraw()
    root.title("IT Toolkit")
    root.overrideredirect(True)
    root.resizable(False, False)
    root.configure(bg=KEY)
    if WINDOWS:
        root.wm_attributes("-transparentcolor", KEY)
    ToolkitApp(root)
    x = max(0, (root.winfo_screenwidth() - WIN_W) // 2)
    y = max(0, (root.winfo_screenheight() - WIN_H) // 2 - 20)
    root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")
    root.deiconify()
    root.update_idletasks()
    show_in_taskbar(root)
    root.after(50, root.focus_force)
    root.mainloop()


if __name__ == "__main__":
    run()
