"""Edital topics and the Roleta-style draw.

Topics come in as the same JSON block the Roleta de Estudos app takes:

    {"Matéria": ["Tópico", ...]}
    {"Matéria": {"Subcategoria": ["Tópico", ...]}}
    {"Matéria > Subcategoria": ["Tópico", ...]}

A drawn topic leaves the pool until every topic of the cycle has been drawn; then a new cycle
starts. The data is a plain dict, saved inside the Anki collection by store.py, so it syncs
with the collection. No Anki imports here.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from typing import Any, Iterator

Edital = dict[str, Any]


def norm(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def topic_id(materia: str, group: str | None, topic: str) -> str:
    key = f"{norm(materia)}|{norm(group)}|{norm(topic)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def empty() -> Edital:
    return {"cycle": 1, "current": None, "materias": []}


def extract_json(text: str) -> Any:
    """Reads the first JSON object in the text, ignoring code fences or a line before it."""
    start = text.find("{")
    if start < 0:
        raise ValueError("Não encontrei um bloco JSON no texto colado.")
    try:
        value, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as err:
        raise ValueError(f"O bloco JSON tem um erro perto do caractere {err.pos}.") from err
    return value


def parse_block(text: str) -> list[tuple[str, str | None, list[str]]]:
    data = extract_json(text)
    if not isinstance(data, dict) or not data:
        raise ValueError("O bloco precisa ser um objeto com matérias como chaves.")
    entries: list[tuple[str, str | None, list[str]]] = []

    def topics_of(value: Any, where: str) -> list[str]:
        if not isinstance(value, list):
            raise ValueError(f"Em {where}, os tópicos precisam estar numa lista.")
        return [str(t).strip() for t in value if str(t).strip()]

    for key, value in data.items():
        if " > " in key:
            materia, group = (part.strip() for part in key.split(" > ", 1))
        else:
            materia, group = key.strip(), None
        if isinstance(value, dict):
            for sub, topics in value.items():
                name = f"{group} › {sub.strip()}" if group else sub.strip()
                entries.append((materia, name, topics_of(topics, f"{materia} > {sub}")))
        else:
            entries.append((materia, group, topics_of(value, materia)))
    return entries


def _find_by_name(items: list[dict], name: str | None) -> dict | None:
    target = norm(name)
    for item in items:
        if norm(item.get("name")) == target:
            return item
    return None


def merge(edital: Edital, entries: list[tuple[str, str | None, list[str]]]) -> int:
    """Adds new topics and keeps the status of the ones already there. Returns how many were added."""
    added = 0
    for materia_name, group_name, topics in entries:
        materia = _find_by_name(edital["materias"], materia_name)
        if materia is None:
            materia = {"name": materia_name, "deck": None, "groups": []}
            edital["materias"].append(materia)
        group = _find_by_name(materia["groups"], group_name)
        if group is None:
            group = {"name": group_name, "topics": []}
            materia["groups"].append(group)
        known = {t["id"] for t in group["topics"]}
        for name in topics:
            tid = topic_id(materia_name, group_name, name)
            if tid in known:
                continue
            group["topics"].append({"id": tid, "name": name, "drawn": 0, "done": 0, "times": 0, "last": None})
            known.add(tid)
            added += 1
    return added


def iter_topics(edital: Edital, scope: dict | None = None) -> Iterator[tuple[dict, dict, dict]]:
    for materia in edital["materias"]:
        if scope and scope.get("materia") and norm(scope["materia"]) != norm(materia["name"]):
            continue
        for group in materia["groups"]:
            if scope and scope.get("group") and norm(scope["group"]) != norm(group["name"]):
                continue
            for topic in group["topics"]:
                yield materia, group, topic


def find(edital: Edital, tid: str | None) -> tuple[dict, dict, dict] | None:
    if not tid:
        return None
    for materia, group, topic in iter_topics(edital):
        if topic["id"] == tid:
            return materia, group, topic
    return None


def pool(edital: Edital, scope: dict | None = None, exclude: str | None = None) -> list[dict]:
    cycle = edital["cycle"]
    return [t for _m, _g, t in iter_topics(edital, scope) if t["drawn"] != cycle and t["id"] != exclude]


def draw(edital: Edital, scope: dict | None = None, exclude: str | None = None, rng: random.Random | None = None) -> dict | None:
    candidates = pool(edital, scope, exclude)
    if not candidates:
        return None
    topic = (rng or random).choice(candidates)
    topic["drawn"] = edital["cycle"]
    edital["current"] = topic["id"]
    return topic


def mark_done(edital: Edital, tid: str, now: int) -> None:
    found = find(edital, tid)
    if not found:
        return
    topic = found[2]
    topic["drawn"] = edital["cycle"]
    topic["done"] = edital["cycle"]
    topic["times"] = int(topic.get("times") or 0) + 1
    topic["last"] = now
    if edital.get("current") == tid:
        edital["current"] = None


def unmark_done(edital: Edital, tid: str) -> None:
    found = find(edital, tid)
    if not found:
        return
    topic = found[2]
    if topic["done"] == edital["cycle"]:
        topic["done"] = 0
        topic["drawn"] = 0
        topic["times"] = max(0, int(topic.get("times") or 0) - 1)


def skip(edital: Edital, tid: str) -> None:
    """Puts the drawn topic back in the pool."""
    found = find(edital, tid)
    if found and found[2]["done"] != edital["cycle"]:
        found[2]["drawn"] = 0
    if edital.get("current") == tid:
        edital["current"] = None


def new_cycle(edital: Edital) -> None:
    edital["cycle"] = int(edital.get("cycle") or 1) + 1
    edital["current"] = None


def counts(edital: Edital, scope: dict | None = None) -> dict[str, int]:
    cycle = edital["cycle"]
    total = done = 0
    for _m, _g, topic in iter_topics(edital, scope):
        total += 1
        done += topic["done"] == cycle
    return {"total": total, "done": done, "left": len(pool(edital, scope))}


def auto_map(edital: Edital, decks: list[tuple[str, int]]) -> None:
    """Links each edital matéria to the deck with the same name, when not linked yet."""
    by_name = {norm(name.split("::")[-1]): did for name, did in decks}
    valid = {did for _name, did in decks}
    for materia in edital["materias"]:
        if materia.get("deck_manual") or materia.get("deck") in valid:
            continue
        materia["deck"] = by_name.get(norm(materia["name"]))
