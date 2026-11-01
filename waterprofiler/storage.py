"""Project files: versioned JSON (.wpj) with atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Tuple

from . import __version__
from .model import Plant

FORMAT = "waterprofiler-project"
SCHEMA_VERSION = 1
EXTENSION = ".wpj"


class ProjectFileError(Exception):
    pass


def save_project(plant: Plant, path: str) -> None:
    doc = {"format": FORMAT, "schema": SCHEMA_VERSION, "app_version": __version__, "plant": plant.to_dict()}
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".wp_", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_project(path: str) -> Plant:
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        raise ProjectFileError(str(e)) from e
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ProjectFileError("not a CEPWater project file")
    if doc.get("schema", 0) > SCHEMA_VERSION:
        raise ProjectFileError("project was saved by a newer version of the program")
    try:
        return Plant.from_dict(doc["plant"])
    except (KeyError, TypeError) as e:
        raise ProjectFileError(f"corrupt project: {e}") from e
