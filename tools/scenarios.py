"""Shared documentation scenarios (used by the screenshot tool and the guide generator)."""

from __future__ import annotations

from waterprofiler.model import Plant
from waterprofiler.sample import demo_plant


def leaky_plant(lang: str = "fa", factor: float = 1.10) -> Plant:
    """Demo plant where the cooling-tower makeup is measured 10 % above its explained use.

    The extra water is unaccounted for (a leak, drift or an unmetered use), so the
    subsystem shows a positive unaccounted loss and the plant no longer closes against meters.
    """
    p = demo_plant(lang)
    ct = p.subsystems[1]
    ct.intake = {k: v * factor for k, v in ct.intake.items()}
    return p
