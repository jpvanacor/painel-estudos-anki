"""The study schedule: one matéria per day, Monday to Saturday, over two weeks that repeat.

Sunday is free. The cycle counts from a Monday (start): that Monday is the first day of
week 1. Saved inside the collection with the rest of the panel's data, so it syncs.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Any, Iterable

DAYS = 12  # 2 weeks x Monday..Saturday
WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
MAX_NAME = 80

DEFAULT: dict[str, Any] = {
    "start": "2026-11-16",
    "days": [
        "Direito Constitucional",
        "Direito Penal",
        "Língua Portuguesa",
        "Direito Civil",
        "Direito Institucional do Ministério Público",
        "Direito Processual Penal",
        "Informática",
        "Direito Administrativo",
        "Legislação Especial",
        "Direito Processual Civil",
        "Redação",
        "Direito Ambiental",
    ],
}


def _monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def clean(raw: Any) -> dict[str, Any]:
    """A valid schedule: start on a Monday, twelve names (empty = nothing that day)."""
    if not isinstance(raw, dict):
        return {"start": DEFAULT["start"], "days": list(DEFAULT["days"])}
    try:
        start = dt.date.fromisoformat(str(raw.get("start")))
    except ValueError:
        start = dt.date.fromisoformat(DEFAULT["start"])
    days = raw.get("days") if isinstance(raw.get("days"), list) else []
    names = [re.sub(r"\s+", " ", str(d or "")).strip()[:MAX_NAME] for d in days[:DAYS]]
    names += [""] * (DAYS - len(names))
    return {"start": _monday(start).isoformat(), "days": names}


def slot(plan: dict[str, Any], day: dt.date) -> int | None:
    """Which of the twelve days `day` is (0 = Monday of week 1), or None on Sundays."""
    if day.weekday() == 6:
        return None
    start = dt.date.fromisoformat(plan["start"])
    week = ((_monday(day) - start).days // 7) % 2
    return week * 6 + day.weekday()


# ---- matching a name in the schedule to a deck
STOP = {"direito", "de", "do", "da", "dos", "das", "e", "a", "o", "lingua", "nocoes", "no", "na"}
ALIASES = {"mp": ["ministerio", "publico"], "mprs": ["ministerio", "publico"], "proc": ["processual"]}


def key(name: str) -> frozenset[str]:
    """Words that identify a matéria: no accents, no "Direito", no parentheses, first 6 letters.

    "Língua Portuguesa" and "Português" give the same key; "Direito Civil" and "Direito
    Processual Civil" don't.
    """
    text = unicodedata.normalize("NFD", name.split("::")[-1].lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\([^)]*\)", " ", text)
    words: list[str] = []
    for word in re.findall(r"[a-z0-9]+", text):
        words += ALIASES.get(word, [word])
    return frozenset(w[:6] for w in words if w not in STOP)


def _plain(name: str) -> str:
    text = unicodedata.normalize("NFD", name.split("::")[-1].lower())
    return " ".join(re.findall(r"[a-z0-9]+", "".join(ch for ch in text if not unicodedata.combining(ch))))


def match(name: str, decks: Iterable[tuple[str, int]]) -> int | None:
    """The deck whose name means the same matéria. With several, the one with the very same
    name; otherwise none (no guessing)."""
    want = key(name)
    if not want:
        return None
    found = {did: deck_name for deck_name, did in decks if key(deck_name) == want}
    if len(found) == 1:
        return next(iter(found))
    same = [did for did, deck_name in found.items() if _plain(deck_name) == _plain(name)]
    return same[0] if len(same) == 1 else None


def view(plan: dict[str, Any], today: dt.date, decks: list[tuple[str, int]]) -> dict[str, Any]:
    """What Hoje shows: today's matéria, tomorrow's, and the two weeks with today marked."""
    names = plan["days"]
    now = slot(plan, today)
    nxt = today + dt.timedelta(days=1)
    while slot(plan, nxt) is None or not names[slot(plan, nxt)]:
        nxt += dt.timedelta(days=1)
        if (nxt - today).days > 14:
            break
    nxt_slot = slot(plan, nxt)
    weeks = []
    for w in range(2):
        weeks.append([{"day": WEEKDAYS[d], "name": names[w * 6 + d], "today": now == w * 6 + d} for d in range(6)])

    def item(i: int | None) -> dict[str, Any] | None:
        if i is None or not names[i]:
            return None
        return {"name": names[i], "did": match(names[i], decks), "week": i // 6 + 1, "day": WEEKDAYS[i % 6]}

    return {
        "today": item(now),
        "sunday": now is None,
        "next": item(nxt_slot) if nxt_slot is not None else None,
        "next_when": "amanhã" if (nxt - today).days == 1 else WEEKDAYS[nxt.weekday()].lower() if nxt.weekday() < 6 else "",
        "week": (now if now is not None else slot(plan, today - dt.timedelta(days=1))) // 6 + 1,
        "weeks": weeks,
        "start": plan["start"],
    }
