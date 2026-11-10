"""Structural edits of the three-level tree (site -> unit -> equipment) that must keep every reference consistent.

A node is a ``Subsystem``: a unit has ``parent == ""``, equipment has ``parent == <unit name>``. A unit that has equipment
takes its flows from them (``Plant.rollup``), so equipment are where data is entered. Names are unique over the whole tree
because links, series keys, plan targets and parameters refer to a node by name.
"""

from __future__ import annotations

from typing import Optional

from .model import Plant, Subsystem

_FLOW_ATTRS = ("recirculated", "from_other", "to_other", "product", "evaporation", "storage_change")


def _has_data(s: Subsystem, plant: Plant) -> bool:
    return bool(s.intake or s.discharge or s.water_treatments or s.wastewater_treatments or s.pumps or s.params
                or any(getattr(s, a) for a in _FLOW_ATTRS)
                or plant.profile.sub_production.get(s.name) or plant.allocation.get(s.name)
                or any(k.startswith(f"sub:{s.name}:") for k in plant.series)
                or any(x.src == s.name or x.dst == s.name for x in plant.links))


def _clear_flows(u: Subsystem, plant: Plant) -> None:
    u.intake, u.discharge = {}, {}
    for a in _FLOW_ATTRS:
        setattr(u, a, 0.0)
    plant.profile.sub_production.pop(u.name, None)


def _rename_refs(plant: Plant, old: str, new: str, series: bool = True) -> None:
    """Point every reference to node ``old`` at ``new`` (links, layout, plan targets, meters, series, production)."""
    for x in plant.links:
        if x.src == old:
            x.src = new
        if x.dst == old:
            x.dst = new
    if f"subsystem:{old}" in plant.layout:
        plant.layout[f"subsystem:{new}"] = plant.layout.pop(f"subsystem:{old}")
    for it in plant.plan:
        if it.target == old:
            it.target = new
    if old in plant.profile.sub_production:
        plant.profile.sub_production[new] = plant.profile.sub_production.pop(old)
    if old in plant.allocation:
        plant.allocation[new] = plant.allocation.pop(old)
    pre = f"sub:{old}:"
    for m in plant.site.meters:
        if m.tag.startswith(pre):
            m.tag = f"sub:{new}:" + m.tag[len(pre):]
    if series:
        for k in [k for k in plant.series if k.startswith(pre)]:
            plant.series[f"sub:{new}:" + k[len(pre):]] = plant.series.pop(k)


def _prepare_unit(plant: Plant, unit: Subsystem, holder: str) -> Optional[Subsystem]:
    """Before a unit gets its first equipment: whatever it carries moves to a holder equipment, so no number is lost."""
    if plant.has_children(unit.name) or not _has_data(unit, plant):
        return None
    h = Subsystem(holder, unit.kind, t_intake_c=unit.t_intake_c, t_wastewater_c=unit.t_wastewater_c, intake=dict(unit.intake),
                  discharge=dict(unit.discharge), water_treatments=dict(unit.water_treatments),
                  wastewater_treatments=dict(unit.wastewater_treatments), pumps=list(unit.pumps),
                  params=dict(unit.params), parent=unit.name)
    for a in _FLOW_ATTRS:
        setattr(h, a, getattr(unit, a))
    plant.subsystems.append(h)
    # series, links, production follow the data to the holder
    pre = f"sub:{unit.name}:"
    for k in [k for k in plant.series if k.startswith(pre)]:
        plant.series[f"sub:{holder}:" + k[len(pre):]] = plant.series.pop(k)
    for x in plant.links:
        if x.src == unit.name:
            x.src = holder
        if x.dst == unit.name:
            x.dst = holder
    if unit.name in plant.profile.sub_production:
        plant.profile.sub_production[holder] = plant.profile.sub_production.pop(unit.name)
    if unit.name in plant.allocation:
        plant.allocation[holder] = plant.allocation.pop(unit.name)
    for m in plant.site.meters:
        if m.tag.startswith(pre):
            m.tag = f"sub:{holder}:" + m.tag[len(pre):]
    unit.water_treatments, unit.wastewater_treatments, unit.pumps, unit.params = {}, {}, [], {}
    return h


def tidy(plant: Plant) -> None:
    """Keep the stored list in tree order (each unit followed by its equipment); the editors index into it."""
    ordered = plant.ordered()
    if len(ordered) == len(plant.subsystems):
        plant.subsystems = ordered


def add_equipment(plant: Plant, unit: str, name: str, kind: str = "other", holder: str = "") -> Subsystem:
    """Add equipment ``name`` to ``unit``. If the unit already carries data, that moves to a holder equipment first."""
    u = plant.node(unit)
    if u is None:
        raise KeyError(unit)
    if u.parent:
        raise ValueError("equipment cannot have equipment: the tree has three levels (site, unit, equipment)")
    name = name.strip()
    if not name or plant.node(name) is not None:
        raise ValueError(f"the name '{name}' is empty or already used")
    _prepare_unit(plant, u, holder or f"{unit} · unallocated")
    eq = Subsystem(name, kind, parent=unit)
    plant.subsystems.append(eq)
    plant.rollup()
    tidy(plant)
    return eq


def rename_node(plant: Plant, old: str, new: str) -> None:
    new = new.strip()
    s = plant.node(old)
    if s is None:
        raise KeyError(old)
    if not new or (new != old and plant.node(new) is not None):
        raise ValueError(f"the name '{new}' is empty or already used")
    if new == old:
        return
    s.name = new
    for c in plant.subsystems:
        if c.parent == old:
            c.parent = new
    _rename_refs(plant, old, new)


def _drop_refs(plant: Plant, name: str) -> None:
    plant.links = [x for x in plant.links if x.src != name and x.dst != name]
    plant.plan = [it for it in plant.plan if it.target != name]
    plant.layout.pop(f"subsystem:{name}", None)
    plant.profile.sub_production.pop(name, None)
    plant.allocation.pop(name, None)
    for k in [k for k in plant.series if k.startswith(f"sub:{name}:")]:
        plant.series.pop(k)
    plant.site.meters = [m for m in plant.site.meters if not m.tag.startswith(f"sub:{name}:")]


def remove_node(plant: Plant, name: str) -> None:
    """Remove a node; removing a unit removes its equipment. A unit left without equipment becomes a plain empty unit."""
    s = plant.node(name)
    if s is None:
        raise KeyError(name)
    doomed = [name] + [c.name for c in plant.children(name)]
    parent = s.parent
    plant.subsystems = [x for x in plant.subsystems if x.name not in doomed]
    for n in doomed:
        _drop_refs(plant, n)
    if parent:
        u = plant.node(parent)
        if u is not None and not plant.has_children(parent):
            _clear_flows(u, plant)
    plant.rollup()
    plant.sync_production()
    tidy(plant)


def move_equipment(plant: Plant, name: str, unit: str, holder: str = "") -> None:
    """Move equipment to another unit (its flows, series and links go with it)."""
    s = plant.node(name)
    u = plant.node(unit)
    if s is None or u is None:
        raise KeyError(name if s is None else unit)
    if not s.parent:
        raise ValueError("only equipment can be moved; a unit has no parent")
    if u.parent or unit == s.parent:
        raise ValueError("the target must be another unit")
    old = s.parent
    _prepare_unit(plant, u, holder or f"{unit} · unallocated")
    s.parent = unit
    ou = plant.node(old)
    if ou is not None and not plant.has_children(old):
        _clear_flows(ou, plant)
    plant.rollup()
    tidy(plant)
