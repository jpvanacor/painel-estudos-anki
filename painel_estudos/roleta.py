"""The Roleta de Estudos, inside the panel.

Same data shape as the Roleta de Estudos app (v2), so the app's backups import as they are and
the panel's backups open in the app:

    {"v": 2, "cats": [{id, name, sel, subs: [{id, name, topics: [{id, t, seen, note}]}]}],
     "ui": {"cat": id}, "last": topic id}

``seen`` is the moment (ms) a topic was drawn in the current cycle, or None. A cycle belongs to
the selection being spun (a subcategory, or all of a matéria): when every topic there has been
drawn, the next spin puts them all back. The panel adds the Anki deck of each matéria
(``deck``, ``deck_manual``), how many times each topic was drawn (``times``) and, when the person
set it, how to find a topic's cards (``cards``: a law or a tag, see topics.py).

No Anki imports here, so this module is tested on its own.
"""

from __future__ import annotations

import copy
import json
import random
import re
import secrets
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any

Roleta = dict[str, Any]
SEP_RE = re.compile(r"\s+[>›»]\s+")
LINE_BULLET_RE = re.compile(r"^\s*(?:[-*•·▪◦–—]+|\d+(?:\.\d+)+\.?|\d+[.)]|[a-zA-Z]\))\s+")


class RoletaError(Exception):
    """A message for the person, shown as is."""


# ------------------------------------------------------------------ text helpers
def now_ms() -> int:
    return int(time.time() * 1000)


def uid() -> str:
    return secrets.token_hex(5)


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def norm(value: Any) -> str:
    """Comparison key used by the Roleta: no accents, lower case, single spaces."""
    text = unicodedata.normalize("NFD", "" if value is None else str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


def deck_key(value: Any) -> str:
    """Looser key for matching a matéria to a deck name."""
    return re.sub(r"[^a-z0-9]+", " ", norm(value)).strip()


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


# ------------------------------------------------------------------ model
def empty() -> Roleta:
    return {"v": 2, "cats": [], "ui": {"cat": None}, "last": None}


def new_cat(name: str) -> dict:
    return {"id": uid(), "name": name, "sel": None, "deck": None, "deck_manual": False, "subs": [new_sub("")]}


def new_sub(name: str) -> dict:
    return {"id": uid(), "name": name, "topics": []}


def new_topic(text: str) -> dict:
    return {"id": uid(), "t": text, "seen": None, "note": "", "times": 0}


def clean_link(link: Any) -> dict | None:
    """How a topic finds its cards, when the person chose: {"tag": ...} or {"law": ...}."""
    if not isinstance(link, dict):
        return None
    for key in ("tag", "law"):
        value = link.get(key)
        if isinstance(value, str) and value.strip() and len(value) <= 300:
            return {key: value.strip()}
    return None


def sanitize_cats(arr: Any) -> list[dict]:
    """Cleans cats from storage or a backup: unique ids, trimmed names, no repeated topics."""
    ids: set[str] = set()

    def fresh(value: Any = None) -> str:
        new = value if isinstance(value, str) and value and value not in ids else uid()
        while new in ids:
            new = uid()
        ids.add(new)
        return new

    out = []
    for c in arr if isinstance(arr, list) else []:
        if not isinstance(c, dict) or not clean(c.get("name")):
            continue
        deck = c.get("deck")
        cat = {
            "id": fresh(c.get("id")),
            "name": clean(c.get("name")),
            "sel": c.get("sel") if isinstance(c.get("sel"), str) else None,
            "deck": int(deck) if isinstance(deck, int) and not isinstance(deck, bool) else None,
            "deck_manual": bool(c.get("deck_manual")),
            "subs": [],
        }
        sub_ids: dict[str, str] = {}
        for s in c.get("subs") if isinstance(c.get("subs"), list) else []:
            if not isinstance(s, dict):
                continue
            sub = {"id": fresh(s.get("id")), "name": clean(s.get("name")), "topics": []}
            if isinstance(s.get("id"), str):
                sub_ids[s["id"]] = sub["id"]
            names: set[str] = set()
            for t in s.get("topics") if isinstance(s.get("topics"), list) else []:
                text = clean(t if isinstance(t, str) else (t.get("t") if isinstance(t, dict) else ""))
                if not text or norm(text) in names:
                    continue
                names.add(norm(text))
                td = t if isinstance(t, dict) else {}
                seen = td.get("seen")
                times = td.get("times")
                topic = {
                    "id": fresh(td.get("id")),
                    "t": text,
                    "seen": seen if isinstance(seen, (int, float)) and not isinstance(seen, bool) and seen > 0 else None,
                    "note": td.get("note") if isinstance(td.get("note"), str) else "",
                    "times": int(times) if isinstance(times, int) and not isinstance(times, bool) and times > 0 else 0,
                }
                link = clean_link(td.get("cards"))
                if link:
                    topic["cards"] = link
                deck = td.get("deck")
                if isinstance(deck, int) and not isinstance(deck, bool) and deck > 0:
                    topic["deck"] = deck
                sub["topics"].append(topic)
            cat["subs"].append(sub)
        if not cat["subs"]:
            cat["subs"].append({"id": fresh(), "name": "", "topics": []})
        if cat["sel"] and cat["sel"] != "_all":
            cat["sel"] = sub_ids.get(cat["sel"])
        out.append(cat)
    return out


def migrate_v1(subjects: Any, seen: Any) -> list[dict]:
    """Roleta v1 backups: {matéria: [..] | {sub: [..]}} plus seen positions by index."""
    cats: list[dict] = []
    if not isinstance(subjects, dict):
        return cats
    seen = seen if isinstance(seen, dict) else {}
    for cat_name, value in subjects.items():
        subs_obj = {"_": value} if isinstance(value, list) else value if isinstance(value, dict) else None
        if subs_obj is None or not clean(cat_name):
            continue
        cat = new_cat(clean(cat_name))
        cat["subs"] = []
        by_key: dict[str, list] = {}
        flat: list = []
        for key, arr in subs_obj.items():
            if not isinstance(arr, list):
                continue
            sub = new_sub("" if key == "_" else clean(key))
            positions = []
            for x in arr:
                topic = new_topic(clean(x)) if isinstance(x, str) and clean(x) else None
                if topic:
                    sub["topics"].append(topic)
                positions.append(topic)
                flat.append(topic)
            by_key[key] = positions
            cat["subs"].append(sub)

        def mark(topic: dict | None, order: int) -> None:
            if topic and not topic["seen"]:
                topic["seen"] = order + 1  # small number: drawn, time unknown

        sc = seen.get(cat_name)
        if isinstance(sc, list):
            for order, i in enumerate(sc):
                if isinstance(i, int) and 0 <= i < len(by_key.get("_", [])):
                    mark(by_key["_"][i], order)
        elif isinstance(sc, dict):
            for key, idxs in sc.items():
                positions = flat if key == "_all" else by_key.get(key)
                if positions and isinstance(idxs, list):
                    for order, i in enumerate(idxs):
                        if isinstance(i, int) and 0 <= i < len(positions):
                            mark(positions[i], order)
        if not cat["subs"]:
            cat["subs"].append(new_sub(""))
        cats.append(cat)
    return sanitize_cats(cats)


def from_edital(old: Any) -> Roleta:
    """Converts the edital of Painel 0.1 (drawn and done per global cycle) to the Roleta's shape."""
    state = empty()
    if not isinstance(old, dict):
        return state
    cycle = old.get("cycle") or 1
    cats = []
    for m in old.get("materias") or []:
        cat = {
            "id": uid(),
            "name": m.get("name"),
            "sel": None,
            "deck": m.get("deck"),
            "deck_manual": bool(m.get("deck_manual")),
            "subs": [],
        }
        for g in m.get("groups") or []:
            topics = []
            for t in g.get("topics") or []:
                drawn = t.get("drawn") == cycle or t.get("done") == cycle
                last = t.get("last")
                seen = (int(last) * 1000 if isinstance(last, (int, float)) and last else now_ms()) if drawn else None
                topics.append({"id": t.get("id"), "t": t.get("name"), "seen": seen, "note": "", "times": t.get("times") or 0})
            cat["subs"].append({"id": uid(), "name": g.get("name") or "", "topics": topics})
        cats.append(cat)
    state["cats"] = sanitize_cats(cats)
    current = old.get("current")
    if current and find_topic(state, current):
        state["last"] = current
    return state


def load(raw: Any) -> Roleta:
    if not isinstance(raw, dict):
        return empty()
    state = empty()
    state["cats"] = sanitize_cats(raw.get("cats"))
    ui = raw.get("ui") if isinstance(raw.get("ui"), dict) else {}
    state["ui"]["cat"] = ui.get("cat") if isinstance(ui.get("cat"), str) else None
    state["last"] = raw.get("last") if isinstance(raw.get("last"), str) else None
    return state


# ------------------------------------------------------------------ lookups
def find_cat(state: Roleta, cat_id: str | None) -> dict | None:
    return next((c for c in state["cats"] if c["id"] == cat_id), None)


def cur_cat(state: Roleta) -> dict | None:
    return find_cat(state, state["ui"].get("cat")) or (state["cats"][0] if state["cats"] else None)


def has_named_subs(cat: dict) -> bool:
    return any(s["name"] for s in cat["subs"])


def scope_of(cat: dict | None) -> tuple[list[dict], bool]:
    """The subcategories being spun, and whether that is all of the matéria."""
    if not cat or not cat["subs"]:
        return [], False
    if len(cat["subs"]) > 1 and (cat.get("sel") == "_all" or not any(s["id"] == cat.get("sel") for s in cat["subs"])):
        return cat["subs"], True
    sub = next((s for s in cat["subs"] if s["id"] == cat.get("sel")), cat["subs"][0])
    return [sub], False


def items_of(subs: list[dict]) -> list[tuple[dict, dict]]:
    return [(sub, topic) for sub in subs for topic in sub["topics"]]


def find_topic(state: Roleta, tid: str | None) -> tuple[dict, dict, dict, int] | None:
    if not tid:
        return None
    for cat in state["cats"]:
        for sub in cat["subs"]:
            for i, topic in enumerate(sub["topics"]):
                if topic["id"] == tid:
                    return cat, sub, topic, i
    return None


def path_of(cat: dict, sub: dict) -> str:
    return f"{cat['name']} › {sub['name'] or 'Geral'}" if has_named_subs(cat) else cat["name"]


def deck_part(text: Any) -> str:
    """A Roleta name as one level of an Anki deck name: "::" would start a new level."""
    part = re.sub(r":{2,}", ":", clean(text)).strip(" :")
    return part or "Sem nome"


def deck_parts(cat: dict, sub: dict, topic: dict) -> list[str]:
    """The levels under the matéria's deck for a topic: subcategoria, then the topic.

    Matérias without named subcategories go straight to the topic. A subcategory imported from
    nested headings ("Parte especial › Crimes contra o patrimônio") gets one level per heading,
    the same levels the Roleta shows.
    """
    parts = []
    if has_named_subs(cat):
        parts += [deck_part(p) for p in SEP_RE.split(sub["name"] or "Geral") if clean(p)] or ["Geral"]
    parts.append(deck_part(topic["t"]))
    return parts


def scope_name(cat: dict) -> str:
    subs, everything = scope_of(cat)
    if everything:
        return f"{cat['name']}, todos os tópicos"
    return path_of(cat, subs[0]) if subs else cat["name"]


def counts(subs: list[dict]) -> dict[str, int]:
    items = items_of(subs)
    seen = sum(1 for _s, t in items if t["seen"])
    return {"total": len(items), "seen": seen, "left": len(items) - seen}


# ------------------------------------------------------------------ the draw
def spin(state: Roleta, cat_id: str | None = None, exclude: str | None = None, rng: random.Random | None = None, now: int | None = None) -> dict:
    cat = find_cat(state, cat_id) or cur_cat(state)
    if not cat:
        raise RoletaError("Importe ou crie uma matéria antes de girar.")
    subs, _everything = scope_of(cat)
    items = items_of(subs)
    if not items:
        raise RoletaError("Adicione tópicos a esta seleção para girar.")
    pool = [it for it in items if not it[1]["seen"]]
    reset = 0
    if not pool:
        for _s, topic in items:
            topic["seen"] = None
        pool = list(items)
        reset = len(items)
        state["last"] = None
    if exclude and len(pool) > 1:
        pool = [it for it in pool if it[1]["id"] != exclude]
    sub, topic = (rng or random).choice(pool)
    topic["seen"] = now or now_ms()
    topic["times"] = int(topic.get("times") or 0) + 1
    state["last"] = topic["id"]
    state["ui"]["cat"] = cat["id"]
    return {
        "id": topic["id"],
        "index": next(i for i, it in enumerate(items) if it[1] is topic),
        "n": len(items),
        "reset": reset,
        "cycle_done": all(t["seen"] for _s, t in items),
    }


def again(state: Roleta, tid: str, rng: random.Random | None = None) -> dict:
    """Sortear outro: the topic goes back to the draw and the wheel spins without it."""
    found = find_topic(state, tid)
    if not found:
        raise RoletaError("Esse tópico não está mais na roleta.")
    cat, _sub, topic, _i = found
    topic["seen"] = None
    if topic.get("times"):
        topic["times"] -= 1
    return spin(state, cat["id"], exclude=tid, rng=rng)


def toggle_seen(state: Roleta, tid: str, now: int | None = None) -> bool:
    found = find_topic(state, tid)
    if not found:
        raise RoletaError("Esse tópico não está mais na roleta.")
    topic = found[2]
    topic["seen"] = None if topic["seen"] else (now or now_ms())
    if not topic["seen"] and state.get("last") == tid:
        state["last"] = None
    return bool(topic["seen"])


def reset_scope(state: Roleta, cat_id: str | None = None) -> int:
    cat = find_cat(state, cat_id) or cur_cat(state)
    if not cat:
        return 0
    subs, _everything = scope_of(cat)
    n = 0
    for _s, topic in items_of(subs):
        if topic["seen"]:
            topic["seen"] = None
            n += 1
    state["last"] = None
    return n


# ------------------------------------------------------------------ editing topics
def set_note(state: Roleta, tid: str, note: str) -> None:
    found = find_topic(state, tid)
    if found:
        found[2]["note"] = str(note or "")


def set_cards_link(state: Roleta, tid: str, link: Any) -> None:
    found = find_topic(state, tid)
    if not found:
        raise RoletaError("Esse tópico não existe mais.")
    topic = found[2]
    clean = clean_link(link)
    if clean:
        topic["cards"] = clean
    else:
        topic.pop("cards", None)


def rename_topic(state: Roleta, tid: str, value: str) -> str:
    found = find_topic(state, tid)
    if not found:
        raise RoletaError("Esse tópico não está mais na roleta.")
    _cat, sub, topic, _i = found
    text = clean(value)
    if not text:
        raise RoletaError("O nome do tópico não pode ficar vazio.")
    if any(t is not topic and norm(t["t"]) == norm(text) for t in sub["topics"]):
        raise RoletaError(f"Já existe um tópico com esse nome em {sub['name'] or 'Geral'}.")
    topic["t"] = text
    return text


def remove_topic(state: Roleta, tid: str) -> str:
    found = find_topic(state, tid)
    if not found:
        raise RoletaError("Esse tópico não está mais na roleta.")
    _cat, sub, topic, i = found
    sub["topics"].pop(i)
    if state.get("last") == tid:
        state["last"] = None
    return topic["t"]


def add_topic(state: Roleta, cat_id: str, sub_id: str | None, value: str) -> dict:
    cat = find_cat(state, cat_id)
    if not cat:
        raise RoletaError("Escolha uma matéria antes de adicionar tópicos.")
    sub = next((s for s in cat["subs"] if s["id"] == sub_id), None) or scope_of(cat)[0][0]
    text = clean(value)
    if not text:
        raise RoletaError("Digite o nome do tópico.")
    if any(norm(t["t"]) == norm(text) for t in sub["topics"]):
        raise RoletaError(f"Esse tópico já existe em {sub['name'] or 'Geral'}.")
    topic = new_topic(text)
    sub["topics"].append(topic)
    return topic


def select(state: Roleta, cat_id: str, sel: str | None = None) -> None:
    cat = find_cat(state, cat_id)
    if not cat:
        raise RoletaError("Essa matéria não está mais na roleta.")
    state["ui"]["cat"] = cat["id"]
    if sel is not None:
        cat["sel"] = sel if sel == "_all" or any(s["id"] == sel for s in cat["subs"]) else None


# ------------------------------------------------------------------ organizer
def save_cat(state: Roleta, cat_id: str | None, name: str, subs: list[dict]) -> dict:
    """Creates (cat_id None) or edits a matéria and its subcategories.

    ``subs`` lists the subcategories to keep, as {"id": existing id or None, "name": ...}.
    Subcategories left out are deleted with their topics. Returns {"cat": id, "removed": n}.
    """
    text = clean(name)
    if not text:
        raise RoletaError("Dê um nome à matéria.")
    if any(c["id"] != cat_id and norm(c["name"]) == norm(text) for c in state["cats"]):
        raise RoletaError("Já existe uma matéria com esse nome.")
    keep = [{"id": s.get("id"), "name": clean(s.get("name"))} for s in subs or []]
    if len(keep) > 1:
        keep = [s for s in keep if s["id"] or s["name"]]
    if sum(1 for s in keep if not s["name"]) > 1:
        raise RoletaError("Só uma subcategoria pode ficar sem nome. Dê nome às outras.")
    names: set[str] = set()
    for s in keep:
        if s["name"]:
            if norm(s["name"]) in names:
                raise RoletaError(f'Há duas subcategorias chamadas "{s["name"]}".')
            names.add(norm(s["name"]))
    if cat_id is None:
        cat = new_cat(text)
        cat["subs"] = []
        state["cats"].append(cat)
    else:
        cat = find_cat(state, cat_id)
        if not cat:
            raise RoletaError("Essa matéria não está mais na roleta.")
        cat["name"] = text
    old = {s["id"]: s for s in cat["subs"]}
    kept_ids = {s["id"] for s in keep if s["id"]}
    removed = sum(len(s["topics"]) for sid, s in old.items() if sid not in kept_ids)
    new_subs = []
    for s in keep:
        existing = old.get(s["id"]) if s["id"] else None
        if existing:
            existing["name"] = s["name"]
            new_subs.append(existing)
        else:
            new_subs.append(new_sub(s["name"]))
    cat["subs"] = new_subs or [new_sub("")]
    if cat.get("sel") and cat["sel"] != "_all" and not any(s["id"] == cat["sel"] for s in cat["subs"]):
        cat["sel"] = None
    state["ui"]["cat"] = cat["id"]
    if state.get("last") and not find_topic(state, state["last"]):
        state["last"] = None
    return {"cat": cat["id"], "removed": removed}


def delete_cat(state: Roleta, cat_id: str) -> int:
    cat = find_cat(state, cat_id)
    if not cat:
        return 0
    state["cats"] = [c for c in state["cats"] if c["id"] != cat_id]
    if state["ui"].get("cat") == cat_id:
        state["ui"]["cat"] = state["cats"][0]["id"] if state["cats"] else None
    if state.get("last") and not find_topic(state, state["last"]):
        state["last"] = None
    return len(items_of(cat["subs"]))


def link_deck(state: Roleta, cat_id: str, did: int | None) -> None:
    cat = find_cat(state, cat_id)
    if not cat:
        raise RoletaError("Essa matéria não está mais na roleta.")
    cat["deck"] = int(did) if did else None
    cat["deck_manual"] = True


def auto_map(state: Roleta, decks: list[tuple[str, int]]) -> bool:
    """Links each matéria to the deck with the same name, unless linked by hand. Returns True if changed."""
    by_name = {deck_key(name.split("::")[-1]): did for name, did in decks}
    valid = {did for _name, did in decks}
    changed = False
    for cat in state["cats"]:
        if cat.get("deck_manual") or cat.get("deck") in valid:
            continue
        new = by_name.get(deck_key(cat["name"]))
        if new != cat.get("deck"):
            cat["deck"] = new
            changed = True
    return changed


# ------------------------------------------------------------------ import and export
def looks_like_json(text: str) -> bool:
    return bool(re.match(r"^[\[{\"`]", text) or re.search(r"\"\s*:\s*[\[{\"]", text))


def parse_lenient(raw: str) -> Any:
    """Reads JSON pasted with a code fence, a line of text before it, a trailing comma,
    curly quotes, or without the outer braces."""
    s = re.sub(r"^﻿", "", str(raw or "")).strip()
    fenced = re.search(r"```[\w-]*\s*(.*?)\s*```", s, re.S)
    candidates = [fenced.group(1).strip()] if fenced else []
    candidates.append(re.sub(r"\s*```\s*$", "", re.sub(r"^```[\w-]*\s*", "", s)).strip())
    starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
    if starts:
        candidates.append(s[min(starts):])
    attempts: list[str] = []
    for c in candidates:
        no_trailing = re.sub(r",\s*([}\]])", r"\1", c)
        attempts += [c, no_trailing, no_trailing.replace("“", '"').replace("”", '"')]
        if not re.match(r"^[\[{]", c):
            attempts.append("{" + re.sub(r",\s*$", "", no_trailing) + "}")
    first_error: Exception | None = None
    for attempt in attempts:
        try:
            value, end = json.JSONDecoder().raw_decode(attempt)
            if attempt[end:].strip() in ("", "```"):
                return value
        except ValueError as err:
            first_error = first_error or err
    raise RoletaError(f"JSON inválido: {first_error}")


def is_backup(d: Any) -> bool:
    return isinstance(d, dict) and (
        (isinstance(d.get("cats"), list) and (d.get("_roleta") == 2 or d.get("v") == 2))
        or (d.get("_backup") is True and isinstance(d.get("subjects"), dict))
    )


def backup_cats(d: dict) -> list[dict]:
    return migrate_v1(d.get("subjects"), d.get("seen")) if d.get("_backup") is True else sanitize_cats(d.get("cats"))


def merge_topics(state: Roleta, d: dict) -> dict:
    result = {"added": 0, "dup": 0, "bad": 0, "first": None}
    touched: list[dict] = []

    def add(cat_name: str, sub_name: str, arr: list) -> None:
        cat_name, sub_name = clean(cat_name), clean(sub_name)
        if sub_name == "_":
            sub_name = ""
        if not cat_name:
            result["bad"] += len(arr)
            return
        cat = next((c for c in state["cats"] if norm(c["name"]) == norm(cat_name)), None)
        if not cat:
            cat = new_cat(cat_name)
            state["cats"].append(cat)
        sub = next((s for s in cat["subs"] if norm(s["name"]) == norm(sub_name)), None)
        if not sub:
            sub = new_sub(sub_name)
            cat["subs"].append(sub)
        have = {norm(t["t"]) for t in sub["topics"]}
        for x in arr:
            text = clean(x) if isinstance(x, str) else ""
            if not text:
                result["bad"] += 1
                continue
            if norm(text) in have:
                result["dup"] += 1
                continue
            have.add(norm(text))
            sub["topics"].append(new_topic(text))
            result["added"] += 1
        if cat not in touched:
            touched.append(cat)
        result["first"] = result["first"] or cat["id"]

    for key, value in d.items():
        m = SEP_RE.search(key)
        cat_name = key[: m.start()] if m else key
        base_sub = key[m.end():] if m else ""
        if isinstance(value, list):
            add(cat_name, base_sub, value)
        elif isinstance(value, dict):
            for sk, sv in value.items():
                sub_name = f"{base_sub} › {sk}" if base_sub else sk
                if isinstance(sv, list):
                    add(cat_name, sub_name, sv)
                elif isinstance(sv, dict):
                    for k3, v3 in sv.items():
                        if isinstance(v3, list):
                            add(cat_name, f"{sub_name} › {k3}", v3)
                        else:
                            result["bad"] += 1
                else:
                    result["bad"] += 1
        else:
            result["bad"] += 1
    # the unnamed "Geral" subcategory goes away when it stays empty and named ones arrive
    for cat in touched:
        if len(cat["subs"]) > 1:
            cat["subs"] = [s for s in cat["subs"] if s["name"] or s["topics"]]
    return result


def clean_line(line: str) -> str:
    return clean(re.sub(r"[;,.]+\s*$", "", LINE_BULLET_RE.sub("", str(line))))


def import_lines(state: Roleta, text: str) -> dict:
    cat = cur_cat(state)
    if not cat:
        raise RoletaError("Para colar uma lista simples, crie ou escolha uma matéria antes. Ou use o formato JSON com o nome da matéria.")
    subs, _everything = scope_of(cat)
    sub = subs[0]
    lines = [clean_line(line) for line in re.split(r"\r?\n", text)]
    lines = [line for line in lines if line]
    if not lines:
        raise RoletaError("Nenhum tópico encontrado no texto.")
    have = {norm(t["t"]) for t in sub["topics"]}
    result = {"added": 0, "dup": 0, "bad": 0, "first": cat["id"]}
    for line in lines:
        if norm(line) in have:
            result["dup"] += 1
            continue
        have.add(norm(line))
        sub["topics"].append(new_topic(line))
        result["added"] += 1
    if not result["added"]:
        raise RoletaError(f"Nada novo: {plural(result['dup'], 'tópico já existia', 'tópicos já existiam')} em {path_of(cat, sub)}.")
    return result


def inspect_import(text: str) -> dict:
    """What a pasted text is: {"kind": "backup", "cats": n, "topics": n} or {"kind": "topics"}."""
    raw = str(text or "").strip()
    if not raw:
        raise RoletaError("Cole um conteúdo ou escolha um arquivo.")
    if not looks_like_json(raw):
        return {"kind": "lines"}
    data = parse_lenient(raw)
    if is_backup(data):
        cats = backup_cats(data)
        return {"kind": "backup", "cats": len(cats), "topics": sum(len(items_of(c["subs"])) for c in cats)}
    return {"kind": "topics"}


def import_text(state: Roleta, text: str) -> dict:
    """Imports topics (JSON or one per line) or restores a backup. Returns counts and the kind."""
    raw = str(text or "").strip()
    if not raw:
        raise RoletaError("Cole um conteúdo ou escolha um arquivo.")
    if not looks_like_json(raw):
        return {"kind": "lines", **import_lines(state, raw)}
    data = parse_lenient(raw)
    if is_backup(data):
        cats = backup_cats(data)
        state["cats"] = cats
        state["ui"]["cat"] = cats[0]["id"] if cats else None
        state["last"] = None
        return {"kind": "backup", "cats": len(cats), "added": sum(len(items_of(c["subs"])) for c in cats), "dup": 0, "bad": 0}
    if isinstance(data, list):
        if data and all(isinstance(x, str) for x in data):
            return {"kind": "lines", **import_lines(state, "\n".join(data))}
        raise RoletaError("Formato não reconhecido. Veja os formatos aceitos abaixo do campo.")
    if not isinstance(data, dict):
        raise RoletaError("Formato não reconhecido. Veja os formatos aceitos abaixo do campo.")
    snapshot = copy.deepcopy(state["cats"])
    result = merge_topics(state, data)
    if not result["added"]:
        state["cats"] = snapshot
        if result["dup"]:
            raise RoletaError(f"Nada novo: {plural(result['dup'], 'tópico já existia', 'tópicos já existiam')}.")
        raise RoletaError("Nenhum tópico válido encontrado. Veja os formatos aceitos abaixo do campo.")
    if result["first"]:
        state["ui"]["cat"] = result["first"]
    return {"kind": "topics", **result}


def backup_json(state: Roleta) -> str:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return json.dumps({"_roleta": 2, "exportedAt": stamp, "cats": state["cats"]}, ensure_ascii=False, indent=2)


def topics_json(state: Roleta) -> str:
    out: dict[str, Any] = {}
    for cat in state["cats"]:
        named = [s for s in cat["subs"] if s["name"]]
        general = [t["t"] for s in cat["subs"] if not s["name"] for t in s["topics"]]
        if not named:
            out[cat["name"]] = general
        elif not general:
            out[cat["name"]] = {s["name"]: [t["t"] for t in s["topics"]] for s in named}
        else:
            out[cat["name"]] = general
            for s in named:
                out[f"{cat['name']} > {s['name']}"] = [t["t"] for t in s["topics"]]
    return json.dumps(out, ensure_ascii=False, indent=2)
