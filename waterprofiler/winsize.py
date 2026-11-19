"""Main-window size that fits the usable screen (pure arithmetic, no Qt)."""

from __future__ import annotations

from typing import Tuple

DEFAULT_W, DEFAULT_H = 1180, 760
MIN_W, MIN_H = 760, 480
ROOMY_W, ROOMY_H = 1280, 800        # below this the window opens maximised


def fit_size(avail_w: int, avail_h: int) -> Tuple[int, int, bool]:
    """(width, height, maximise) for a screen whose usable area (taskbar excluded) is avail_w x avail_h."""
    w = min(DEFAULT_W, int(avail_w * 0.96))
    h = min(DEFAULT_H, int(avail_h * 0.94))
    return max(MIN_W, w), max(MIN_H, h), avail_w < ROOMY_W or avail_h < ROOMY_H
