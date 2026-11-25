#!/usr/bin/env python3
"""Developer tool: regenerates the logo, tab icons and printer thumbnails.

Requires Pillow (sudo apt install python3-pil). All artwork is drawn from scratch by
this script; no third-party icon or photo assets are included. Replace any output
with your own artwork at any time, keeping the same file names and sizes:
    logo.png        -> abg3d_screen/assets/logo.png       (960x420, transparent)
    icons/*.png     -> abg3d_screen/assets/icons/         (96x96, white line icons)
    printers/*.png  -> abg3d_screen/assets/printers/      (240x150)
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent.parent / "abg3d_screen" / "assets"
SS = 4  # supersampling factor for smooth edges
WHITE = (236, 241, 247, 255)
ACCENT = (90, 169, 230, 255)
PANEL = (29, 35, 45, 255)
STROKE = 6


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for base in ("/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/TTF/"):
        if Path(base + name).exists():
            return ImageFont.truetype(base + name, size)
    return ImageFont.load_default(size=size)


def sc(*values):
    return [int(v * SS) for v in values]


# ---------------------------------------------------------------- logo
def make_logo():
    """Splash logo: rounded emblem with a layered cube, wordmark and tagline."""
    W, H = 960, 420
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ex, ey, es = 40, 60, 300
    grad = Image.new("RGBA", (es * SS, es * SS))
    gd = ImageDraw.Draw(grad)
    top, bot = (34, 46, 64), (16, 21, 30)
    for y in range(es * SS):
        t = y / (es * SS)
        gd.line([(0, y), (es * SS, y)],
                fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", grad.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, es * SS - 1, es * SS - 1), radius=56 * SS, fill=255)
    img.paste(grad, (ex * SS, ey * SS), mask)
    d.rounded_rectangle(sc(ex, ey, ex + es, ey + es), radius=56 * SS, outline=ACCENT, width=4 * SS)

    cx, cy, e = (ex + es / 2) * SS, (ey + es / 2 + 6) * SS, 116 * SS
    w, hh = e * math.sqrt(3) / 2, e / 2
    top_f = [(cx, cy - e), (cx + w, cy - hh), (cx, cy), (cx - w, cy - hh)]
    left_f = [(cx - w, cy - hh), (cx, cy), (cx, cy + e), (cx - w, cy + hh)]
    right_f = [(cx, cy), (cx + w, cy - hh), (cx + w, cy + hh), (cx, cy + e)]
    d.polygon(top_f, fill=(176, 220, 248, 255))
    d.polygon(left_f, fill=ACCENT)
    d.polygon(right_f, fill=(44, 108, 168, 255))
    for i in range(1, 9):
        y0 = cy - hh + (i / 9) * e
        d.line([(cx - w, y0), (cx, y0 + hh)], fill=(60, 130, 196, 255), width=2 * SS)
    edge = (14, 20, 30, 255)
    for poly in (top_f, left_f, right_f):
        d.line(poly + [poly[0]], fill=edge, width=3 * SS, joint="curve")

    tx = 380
    d.text((tx * SS, 96 * SS), "ABG3D", font=font(88 * SS, True), fill=WHITE)
    f = font(40 * SS, True)
    x = (tx + 4) * SS
    for ch in "SCREEN":
        d.text((x, 214 * SS), ch, font=f, fill=ACCENT)
        x += f.getlength(ch) + 12 * SS
    d.line(sc(tx, 290, tx + 470, 290), fill=(51, 61, 78, 255), width=2 * SS)
    d.text((tx * SS, 310 * SS), "Touchscreen interface for Klipper",
           font=font(24 * SS, False), fill=(141, 150, 165, 255))
    img.resize((W, H), Image.LANCZOS).save(ASSETS / "logo.png")


# ---------------------------------------------------------------- icons (line style)
def _icon(name, draw):
    size = 96
    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    draw(ImageDraw.Draw(img))
    img.resize((size, size), Image.LANCZOS).save(ASSETS / "icons" / f"{name}.png")


def icon_home(d):
    d.line(sc(10, 46, 48, 14, 86, 46), fill=WHITE, width=STROKE * SS, joint="curve")
    d.line(sc(22, 42, 22, 84, 74, 84, 74, 42), fill=WHITE, width=STROKE * SS, joint="curve")
    d.line(sc(40, 84, 40, 62, 56, 62, 56, 84), fill=ACCENT, width=STROKE * SS, joint="curve")


def icon_control(d):
    d.ellipse(sc(16, 16, 80, 80), outline=WHITE, width=STROKE * SS)
    d.ellipse(sc(42, 42, 54, 54), fill=ACCENT)
    for seg in ((48, 4, 48, 22), (48, 74, 48, 92), (4, 48, 22, 48), (74, 48, 92, 48)):
        d.line(sc(*seg), fill=WHITE, width=STROKE * SS)


def icon_temps(d):
    d.rounded_rectangle(sc(38, 8, 58, 64), radius=10 * SS, outline=WHITE, width=STROKE * SS)
    d.ellipse(sc(28, 56, 68, 96), outline=WHITE, width=STROKE * SS)
    d.rectangle(sc(45, 36, 51, 74), fill=ACCENT)
    d.ellipse(sc(38, 66, 58, 86), fill=ACCENT)


def icon_mmu(d):
    d.rounded_rectangle(sc(8, 14, 24, 82), radius=4 * SS, outline=WHITE, width=STROKE * SS)
    d.rounded_rectangle(sc(72, 14, 88, 82), radius=4 * SS, outline=WHITE, width=STROKE * SS)
    d.line(sc(24, 48, 72, 48), fill=ACCENT, width=STROKE * SS)
    d.ellipse(sc(40, 40, 56, 56), fill=ACCENT)


def icon_system(d):
    d.arc(sc(12, 12, 84, 84), start=300, end=240, fill=WHITE, width=STROKE * SS)
    d.line(sc(48, 8, 48, 46), fill=WHITE, width=STROKE * SS)


def icon_settings(d):
    for y in (24, 48, 72):
        d.line(sc(10, y, 86, y), fill=WHITE, width=STROKE * SS)
    for x, y in ((30, 24), (64, 48), (40, 72)):
        d.ellipse(sc(x - 9, y - 9, x + 9, y + 9), fill=ACCENT, outline=WHITE, width=3 * SS)


# ---------------------------------------------------------------- printer thumbnails
def make_printer(key, accent):
    """Stylised frame drawings with a family-specific detail (placeholders, not photos)."""
    W, H = 240, 150
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(sc(0, 0, W, H), radius=18 * SS, fill=PANEL)
    frame = (128, 138, 154, 255)
    belt = (70, 80, 96, 255)
    x0, x1, y0, y1 = 58, 182, 24, 118
    tx = (x0 + x1) // 2

    # frame: posts, top and bottom rails
    for x in (x0, x1):
        d.rectangle(sc(x - 3, y0, x + 3, y1), fill=frame)
    d.rectangle(sc(x0, y0 - 3, x1, y0 + 3), fill=frame)
    d.rectangle(sc(x0, y1 - 3, x1, y1 + 3), fill=frame)

    bed_inset = 4 if key == "vzbot" else 12
    gy = y0 + 32  # gantry height

    if key == "voron":
        # Voron: corner braces on every corner, bed slightly recessed
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            d.line(sc(x, y, x + (14 if x == x0 else -14), y + (14 if y == y0 else -14)),
                   fill=frame, width=3 * SS)
    elif key == "ratrig":
        # Rat Rig: V-core, two rails converging on the toolhead
        d.line(sc(tx, gy, x0 + 4, y0 + 2), fill=accent, width=3 * SS)
        d.line(sc(tx, gy, x1 - 4, y0 + 2), fill=accent, width=3 * SS)
    elif key == "vzbot":
        # VzBot: wide bed slinger style with a centre gantry beam
        d.line(sc(x0, gy + 14, x1, gy + 14), fill=belt, width=2 * SS)
    elif key == "rh3dng":
        # RH3D NG: CoreXY belts crossing the frame diagonally
        d.line(sc(x0 + 2, y0 + 4, x1 - 2, y1 - 4), fill=belt, width=2 * SS)
        d.line(sc(x1 - 2, y0 + 4, x0 + 2, y1 - 4), fill=belt, width=2 * SS)

    bed_y0 = y1 - 20
    d.rounded_rectangle(sc(x0 + bed_inset, bed_y0, x1 - bed_inset, bed_y0 + 10), radius=4 * SS,
                        fill=(62, 74, 92, 255))
    d.rectangle(sc(x0 + 6, gy - 3, x1 - 6, gy + 3), fill=accent)
    d.rounded_rectangle(sc(tx - 14, gy - 10, tx + 14, gy + 10), radius=4 * SS, fill=accent)
    d.ellipse(sc(tx - 4, gy + 10, tx + 4, gy + 18), fill=WHITE)  # nozzle
    img.resize((W, H), Image.LANCZOS).save(ASSETS / "printers" / f"{key}.png")


def _house(letter=None):
    def draw(d):
        d.line(sc(10, 46, 48, 14, 86, 46), fill=WHITE, width=STROKE * SS, joint="curve")
        d.line(sc(22, 42, 22, 84, 74, 84, 74, 42), fill=WHITE, width=STROKE * SS, joint="curve")
        if letter:
            d.text((48 * SS, 66 * SS), letter, font=font(36 * SS, True), fill=ACCENT, anchor="mm")
    return draw


def icon_ztilt(d):
    d.polygon(sc(48, 14, 84, 76, 12, 76), outline=WHITE, width=STROKE * SS)
    for x, y in ((48, 14), (84, 76), (12, 76)):
        d.ellipse(sc(x - 8, y - 8, x + 8, y + 8), fill=ACCENT)


def icon_qgl(d):
    d.rounded_rectangle(sc(14, 14, 82, 82), radius=8 * SS, outline=WHITE, width=STROKE * SS)
    for x, y in ((14, 14), (82, 14), (14, 82), (82, 82)):
        d.ellipse(sc(x - 8, y - 8, x + 8, y + 8), fill=ACCENT)


def icon_console(d):
    d.line(sc(18, 80, 46, 16), fill=WHITE, width=STROKE * SS)
    d.line(sc(54, 30, 78, 48, 54, 66), fill=ACCENT, width=STROKE * SS, joint="curve")


def _house_xy(d):
    d.line(sc(10, 46, 48, 14, 86, 46), fill=WHITE, width=STROKE * SS, joint="curve")
    d.line(sc(22, 42, 22, 84, 74, 84, 74, 42), fill=WHITE, width=STROKE * SS, joint="curve")
    d.text((48 * SS, 66 * SS), "XY", font=font(24 * SS, True), fill=ACCENT, anchor="mm")


def icon_pause(d):
    d.rounded_rectangle(sc(22, 16, 40, 80), radius=4 * SS, fill=WHITE)
    d.rounded_rectangle(sc(56, 16, 74, 80), radius=4 * SS, fill=WHITE)


def icon_play(d):
    d.polygon(sc(26, 14, 84, 48, 26, 82), fill=WHITE)


def icon_cancel(d):
    d.ellipse(sc(10, 10, 86, 86), outline=WHITE, width=STROKE * SS)
    d.line(sc(34, 34, 62, 62), fill=WHITE, width=STROKE * SS)
    d.line(sc(62, 34, 34, 62), fill=WHITE, width=STROKE * SS)


def icon_stop(d):
    d.rounded_rectangle(sc(16, 16, 80, 80), radius=12 * SS, fill=WHITE)


def icon_motor_off(d):
    d.rounded_rectangle(sc(12, 30, 60, 66), radius=6 * SS, outline=WHITE, width=STROKE * SS)
    d.rectangle(sc(60, 42, 78, 54), fill=WHITE)
    d.line(sc(8, 8, 88, 88), fill=ACCENT, width=STROKE * SS)


def icon_trash(d):
    d.line(sc(18, 26, 78, 26), fill=WHITE, width=STROKE * SS)
    d.line(sc(40, 14, 56, 14), fill=WHITE, width=STROKE * SS)
    d.polygon(sc(24, 32, 72, 32, 66, 84, 30, 84), outline=WHITE, width=STROKE * SS)
    for x in (40, 48, 56):
        d.line(sc(x, 42, x, 74), fill=ACCENT, width=4 * SS)


def icon_enter(d):
    d.line(sc(78, 22, 78, 50, 26, 50), fill=WHITE, width=STROKE * SS, joint="curve")
    d.polygon(sc(10, 50, 32, 36, 32, 64), fill=WHITE)


def icon_quit(d):
    d.rounded_rectangle(sc(14, 12, 56, 84), radius=4 * SS, outline=WHITE, width=STROKE * SS)
    d.line(sc(40, 48, 84, 48), fill=ACCENT, width=STROKE * SS)
    d.polygon(sc(84, 48, 70, 38, 70, 58), fill=ACCENT)


def icon_move(d):
    d.line(sc(48, 16, 48, 80), fill=WHITE, width=STROKE * SS)
    d.line(sc(16, 48, 80, 48), fill=WHITE, width=STROKE * SS)
    d.polygon(sc(48, 6, 38, 22, 58, 22), fill=ACCENT)
    d.polygon(sc(48, 90, 38, 74, 58, 74), fill=ACCENT)
    d.polygon(sc(6, 48, 22, 38, 22, 58), fill=ACCENT)
    d.polygon(sc(90, 48, 74, 38, 74, 58), fill=ACCENT)


def icon_fan(d):
    import math
    for base in (-90, 30, 150):
        pts = []
        for r, ang in ((9, -28), (40, -12), (38, 16), (10, 34)):
            a = math.radians(base + ang)
            pts.append((48 + r * math.cos(a), 48 + r * math.sin(a)))
        d.polygon([(x * SS, y * SS) for x, y in pts], outline=WHITE, width=4 * SS)
    d.ellipse(sc(40, 40, 56, 56), fill=ACCENT)


def icon_led(d):
    d.ellipse(sc(26, 14, 70, 58), outline=WHITE, width=STROKE * SS)
    d.rounded_rectangle(sc(38, 56, 58, 78), radius=3 * SS, outline=WHITE, width=STROKE * SS)
    for seg in ((10, 30, 18, 38), (86, 30, 78, 38), (22, 8, 28, 16), (74, 8, 68, 16)):
        d.line(sc(*seg), fill=ACCENT, width=5 * SS)


def icon_palette(d):
    d.ellipse(sc(8, 10, 88, 86), outline=WHITE, width=STROKE * SS)
    for x, y, col in ((30, 36, ACCENT), (50, 26, WHITE), (66, 44, ACCENT), (34, 62, WHITE)):
        d.ellipse(sc(x - 6, y - 6, x + 6, y + 6), fill=col)


def icon_hotend(d):
    d.rounded_rectangle(sc(30, 8, 66, 34), radius=4 * SS, outline=WHITE, width=STROKE * SS)
    d.polygon(sc(36, 34, 60, 34, 48, 60), outline=WHITE, width=STROKE * SS)
    d.ellipse(sc(42, 66, 54, 78), fill=ACCENT)


def icon_script(d):
    d.line(sc(34, 26, 16, 48, 34, 70), fill=WHITE, width=STROKE * SS, joint="curve")
    d.line(sc(62, 26, 80, 48, 62, 70), fill=WHITE, width=STROKE * SS, joint="curve")
    d.line(sc(58, 20, 38, 76), fill=ACCENT, width=STROKE * SS)


def icon_wifi(d):
    for radius in (24, 40, 56):
        d.arc(sc(48 - radius, 70 - radius, 48 + radius, 70 + radius), start=225, end=315,
              fill=WHITE, width=STROKE * SS)
    d.ellipse(sc(42, 64, 54, 76), fill=ACCENT)


def icon_gear(d):
    import math
    for k in range(8):
        a = math.radians(45 * k)
        d.line(sc(48 + 28 * math.cos(a), 48 + 28 * math.sin(a),
                  48 + 40 * math.cos(a), 48 + 40 * math.sin(a)), fill=WHITE, width=STROKE * SS)
    d.ellipse(sc(20, 20, 76, 76), outline=WHITE, width=STROKE * SS)
    d.ellipse(sc(40, 40, 56, 56), fill=ACCENT)


if __name__ == "__main__":
    (ASSETS / "icons").mkdir(parents=True, exist_ok=True)
    (ASSETS / "printers").mkdir(parents=True, exist_ok=True)
    make_logo()
    for name, fn in (("home", icon_home), ("control", icon_control), ("temps", icon_temps),
                     ("mmu", icon_mmu), ("system", icon_system), ("settings", icon_settings),
                     ("home_all", _house()), ("home_x", _house("X")), ("home_y", _house("Y")),
                     ("home_z", _house("Z")), ("ztilt", icon_ztilt), ("qgl", icon_qgl),
                     ("console", icon_console), ("pause", icon_pause), ("play", icon_play),
                     ("cancel", icon_cancel), ("stop", icon_stop), ("motor_off", icon_motor_off),
                     ("home_xy", _house_xy), ("trash", icon_trash), ("enter", icon_enter),
                     ("quit", icon_quit), ("move", icon_move), ("fan", icon_fan), ("led", icon_led),
                     ("palette", icon_palette), ("hotend", icon_hotend), ("script", icon_script),
                     ("wifi", icon_wifi), ("gear", icon_gear)):
        _icon(name, fn)
    for key, accent in (("voron", (242, 156, 56, 255)), ("ratrig", (142, 209, 106, 255)),
                        ("vzbot", (61, 181, 232, 255)), ("rh3dng", (217, 103, 93, 255))):
        make_printer(key, accent)
    print("Assets written to", ASSETS)
