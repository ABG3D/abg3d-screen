"""MMU adapters. Detection lives in detect.py; this module holds the command maps.

An MMU tab is only enabled when detect_mmu() reports a supported plugin on the
current printer. Nothing is sent to the printer for an MMU that is not present.
"""
import json

from . import ASSETS_DIR

SUPPORTED = ("happy_hare", "boxturtle_afc", "ktc")


def load_mmu_commands():
    return json.loads((ASSETS_DIR / "data" / "mmu_commands.json").read_text())


def is_active(detection):
    """True only when a supported MMU was detected on this printer."""
    return (detection or {}).get("mmu") in SUPPORTED
