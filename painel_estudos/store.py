"""Settings, edital and draw history, saved inside the Anki collection so they sync with it."""

from __future__ import annotations

import copy
from typing import Any

from . import edital

KEY = "painelEstudos"

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "goal": {"unit": "cards", "value": 100},
    "root": None,  # deck whose children are the matérias; None = automatic
    "scope": None,  # draw scope: None, {"materia": ...} or {"materia": ..., "group": ...}
    "edital": None,
}


def load(col) -> dict[str, Any]:
    data = col.get_config(KEY, None)
    if not isinstance(data, dict):
        data = {}
    merged = copy.deepcopy(DEFAULTS)
    merged.update(data)
    goal = dict(DEFAULTS["goal"])
    goal.update(data.get("goal") or {})
    merged["goal"] = goal
    if not isinstance(merged.get("edital"), dict):
        merged["edital"] = edital.empty()
    return merged


def save(col, data: dict[str, Any]) -> None:
    col.set_config(KEY, data)
