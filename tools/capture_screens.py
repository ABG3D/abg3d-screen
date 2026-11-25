#!/usr/bin/env python3
"""Headless screenshot capture for the README.

Renders every main tab and Settings sub-tab in demo mode and saves PNG files.
Run under a virtual X server so no monitor is needed:

    xvfb-run -a -s "-screen 0 800x480x24" python3 tools/capture_screens.py

Options:
    --out DIR    output folder (default: docs/screenshots)
    --wait SEC   time to let demo data settle before each capture (default: 1.2)

Needs python3-tk and Pillow with X11 support (ImageGrab).
"""
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Isolated settings so captures never touch a real user's configuration.
os.environ["ABG3D_CONFIG_DIR"] = tempfile.mkdtemp(prefix="abg3d-shots-")

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from abg3d_screen.app import App  # noqa: E402
from abg3d_screen.config import Settings  # noqa: E402


def seed_settings():
    Settings().update(setup_done=True, mmu_enabled=True, allow_quit=True, theme="midnight",
                      printer_family="voron", printer_model="Trident", mouse_pointer=True)


def goto(app, key, tab=None, sub=None):
    app.show(key)
    page = app.pages[key]
    if tab:
        page._set_tab(tab)
    if sub:
        page._set_sub(sub)
    return page


def settle(root, seconds):
    for _ in range(max(1, int(seconds / 0.1))):
        root.update()
        time.sleep(0.1)


def snap(root, path):
    root.update_idletasks()
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)


VIEWS = [
    ("home", lambda app: goto(app, "home")),
    ("control-movement", lambda app: goto(app, "control", tab="movement")),
    ("control-fan", lambda app: goto(app, "control", tab="fan")),
    ("control-led", lambda app: goto(app, "control", tab="led")),
    ("console", lambda app: goto(app, "console")),
    ("mmu", lambda app: goto(app, "mmu")),
    ("system", lambda app: goto(app, "system")),
    ("settings-appearance", lambda app: goto(app, "settings", sub="appearance")),
    ("settings-themes-open", lambda app: goto(app, "settings", sub="appearance")._toggle_dropdown()),
    ("settings-mmu", lambda app: goto(app, "settings", sub="mmu")),
    ("settings-macros", lambda app: goto(app, "settings", sub="macros")),
    ("settings-network", lambda app: goto(app, "settings", sub="network")),
    ("settings-system", lambda app: goto(app, "settings", sub="system")),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="docs/screenshots")
    parser.add_argument("--wait", type=float, default=1.2)
    args = parser.parse_args()

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    seed_settings()

    root = tk.Tk()
    try:
        ImageGrab.grab(bbox=(0, 0, 1, 1))
    except Exception as exc:  # Pillow built without X11 support
        root.destroy()
        sys.exit(f"ImageGrab needs X11 support in Pillow: {exc}")

    opts = SimpleNamespace(windowed=True, demo=True, no_splash=False, reset_setup=False,
                           simulate_mmu="happy_hare")
    app = App(root, opts)
    settle(root, 0.4)
    snap(root, out / "splash.png")
    app._dismiss_splash()
    settle(root, args.wait)

    saved = ["splash.png"]
    for name, setup in VIEWS:
        setup(app)
        settle(root, args.wait)
        snap(root, out / f"{name}.png")
        saved.append(f"{name}.png")
    app.quit()
    print("saved:", ", ".join(saved), "->", out)


if __name__ == "__main__":
    main()
