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


def flow_plant(lang: str = "fa") -> Plant:
    """Demo plant where part of the cooling-tower blowdown is reused to irrigate the landscape."""
    from waterprofiler.model import Transfer, sync_transfers
    p = demo_plant(lang)
    ct, irr = p.subsystems[1], p.subsystems[4]
    moved = 1500.0
    sewer = next(iter(ct.discharge))
    ct.discharge[sewer] -= moved
    well = next(iter(irr.intake))
    irr.intake[well] -= moved
    p.links = [Transfer(ct.name, irr.name, moved)]
    sync_transfers(p)
    return p
