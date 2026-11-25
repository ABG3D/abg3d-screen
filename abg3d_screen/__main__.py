"""Entry point.

    python3 -m abg3d_screen [--windowed] [--demo] [--no-splash]
"""
import argparse
import sys
import tkinter as tk

from . import __app_name__, __version__


def main(argv=None):
    parser = argparse.ArgumentParser(prog="abg3d-screen", description=f"{__app_name__} {__version__}")
    parser.add_argument("--windowed", action="store_true", help="run in an 800x480 window (testing)")
    parser.add_argument("--demo", action="store_true", help="force demo mode even if Moonraker is running")
    parser.add_argument("--no-splash", action="store_true", help="skip the splash screen")
    parser.add_argument("--simulate-mmu", choices=["happy_hare", "boxturtle_afc", "ktc"],
                        help="testing: pretend this MMU is detected (demo UI only)")
    args = parser.parse_args(argv)

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Cannot open a display ({exc}). Start from a desktop session or via bin/run.sh.",
              file=sys.stderr)
        return 1

    from .app import App
    App(root, args)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
