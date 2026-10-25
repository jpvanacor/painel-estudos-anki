"""Settings and the Roleta, saved inside the Anki collection so they sync with it."""

from __future__ import annotations

import copy
from typing import Any

from . import roleta as ro

KEY = "painelEstudos"

DEFAULTS: dict[str, Any] = {
    "version": 2,
    "goal": {"unit": "cards", "value": 100},
    "root": None,  # deck whose children are the matérias; None = automatic
    "fx": {"sound": True, "volume": 0.7, "motion": True},
    "roleta": None,
}


def load(col) -> dict[str, Any]:
    raw = col.get_config(KEY, None)
    data = raw if isinstance(raw, dict) else {}
    merged = copy.deepcopy(DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    merged["goal"] = {**DEFAULTS["goal"], **(data.get("goal") or {})}
    merged["fx"] = {**DEFAULTS["fx"], **(data.get("fx") or {})}
    if isinstance(data.get("roleta"), dict):
        merged["roleta"] = ro.load(data["roleta"])
        merged["_converted"] = False
    else:
        old = data.get("edital")  # Painel 0.1 kept the edital in its own shape
        has_old = isinstance(old, dict) and bool(old.get("materias"))
        merged["roleta"] = ro.from_edital(old) if has_old else ro.empty()
        merged["_converted"] = has_old
    return merged


def save(col, data: dict[str, Any]) -> None:
    col.set_config(KEY, {k: v for k, v in data.items() if k in DEFAULTS})
