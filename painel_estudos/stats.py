"""Numbers for the dashboard: today's goal, the matérias, accuracy and weak spots."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from anki.utils import ids2str

DAY = 86400
META_TAGS = ("banca::", "ano::", "leech", "marked", "duplicate")


def today_start(col) -> int:
    return int(col.sched.day_cutoff) - DAY


def leaf(name: str) -> str:
    return name.split("::")[-1]


def _children(col, did: int) -> list[tuple[str, int]]:
    return [(leaf(name), int(cid)) for name, cid in col.decks.children(did) if not col.decks.is_filtered(cid)]


def matter_decks(col, root: int | None = None) -> list[tuple[str, int]]:
    """(display name, deck id) of each matéria.

    With a root deck chosen in the settings, its subdecks are the matérias. Otherwise the
    top-level decks are, unless there is a single top-level deck with subdecks.
    """
    if root and col.decks.get(root, default=False):
        kids = _children(col, int(root))
        if kids:
            return kids
    tops = [d for d in col.decks.all_names_and_ids(skip_empty_default=True, include_filtered=False) if "::" not in d.name]
    if len(tops) == 1:
        kids = _children(col, int(tops[0].id))
        if kids:
            return kids
    return [(d.name, int(d.id)) for d in tops]


def due_nodes(col) -> dict[int, Any]:
    nodes: dict[int, Any] = {}

    def walk(node: Any) -> None:
        nodes[int(node.deck_id)] = node
        for child in node.children:
            walk(child)

    walk(col.sched.deck_due_tree())
    return nodes


def subtree(col, did: int) -> list[int]:
    return [int(d) for d in col.decks.deck_and_child_ids(did)]


def accuracy(col, dids: list[int], days: int = 30) -> tuple[float | None, int]:
    """Share of answers that were not "De novo" in the last days."""
    since = (today_start(col) - (days - 1) * DAY) * 1000
    ids = ids2str(dids)
    total, ok = col.db.first(
        f"select count(), coalesce(sum(r.ease > 1), 0) from revlog r join cards c on c.id = r.cid "
        f"where (c.did in {ids} or c.odid in {ids}) and r.ease > 0 and r.id >= ?",
        since,
    )
    return (ok / total if total else None), total


def maturity(col, dids: list[int]) -> dict[str, int]:
    ids = ids2str(dids)
    row = col.db.first(
        "select count(), "
        "coalesce(sum(queue = -1), 0), "
        "coalesce(sum(queue != -1 and type = 0), 0), "
        "coalesce(sum(queue != -1 and type in (1, 3)), 0), "
        "coalesce(sum(queue != -1 and type = 2 and ivl < 21), 0), "
        "coalesce(sum(queue != -1 and type = 2 and ivl >= 21), 0) "
        f"from cards where did in {ids} or odid in {ids}"
    )
    keys = ("total", "suspended", "new", "learning", "young", "mature")
    return dict(zip(keys, (int(v or 0) for v in row)))


def _pretty_part(part: str) -> str:
    words = part.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words.islower() else words


def pretty_tag(tag: str, drop_first: bool = False) -> str:
    """direito_penal::CP::parte_especial::titulo_II::crimes_contra_patrimonio -> CP › Crimes contra patrimonio"""
    parts = tag.split("::")
    if drop_first and len(parts) > 1:
        parts = parts[1:]
    if len(parts) > 2:
        parts = [parts[0], parts[-1]]
    return " › ".join(_pretty_part(p) for p in parts)


def weak_tags(col, dids: list[int], days: int = 90, depth: int = 8, min_answers: int = 5, limit: int = 6) -> list[dict]:
    """Tags inside the deck with the lowest share of right answers (each full tag is one topic)."""
    since = (today_start(col) - (days - 1) * DAY) * 1000
    ids = ids2str(dids)
    rows = col.db.all(
        "select r.ease, n.tags from revlog r join cards c on c.id = r.cid join notes n on n.id = c.nid "
        f"where (c.did in {ids} or c.odid in {ids}) and r.ease > 0 and r.id >= ?",
        since,
    )
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for ease, tags in rows:
        seen = set()
        for tag in tags.split():
            if tag.lower().startswith(META_TAGS):
                continue
            key = "::".join(tag.split("::")[:depth])
            if key in seen:
                continue
            seen.add(key)
            tally[key][0] += 1
            tally[key][1] += ease > 1
    firsts = {key.split("::")[0].lower() for key in tally}
    drop_first = len(firsts) == 1
    items = [
        {"tag": key, "label": pretty_tag(key, drop_first), "path": " › ".join(_pretty_part(p) for p in key.split("::")), "acc": ok / n, "n": n}
        for key, (n, ok) in tally.items()
        if n >= min_answers
    ]
    items.sort(key=lambda item: (item["acc"], -item["n"]))
    return items[:limit]


def today(col) -> tuple[int, float]:
    """Cards answered today and minutes spent on them."""
    cards, ms = col.db.first(
        "select count(), coalesce(sum(time), 0) from revlog where id >= ? and ease > 0", today_start(col) * 1000
    )
    return int(cards or 0), (ms or 0) / 60000


def goal(col, unit: str, value: float) -> dict[str, Any]:
    """Today's progress toward the daily goal, the streak of days that met it, and pace."""
    start = today_start(col)
    rows = col.db.all("select id, time from revlog where id >= ? and ease > 0", (start - 400 * DAY) * 1000)
    per_day: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for rid, ms in rows:
        day = (rid // 1000 - start) // DAY  # 0 = today, -1 = yesterday
        per_day[day][0] += 1
        per_day[day][1] += ms

    def amount(day: int) -> float:
        cards, ms = per_day.get(day, (0, 0))
        return cards if unit == "cards" else ms / 60000

    done = amount(0)
    streak = 0
    if value > 0:
        day = 0 if done >= value else -1
        while amount(day) >= value:
            streak += 1
            day -= 1
    recent = [per_day[d] for d in range(-13, 1) if d in per_day]
    answered = sum(c for c, _ms in recent)
    avg_secs = (sum(ms for _c, ms in recent) / answered / 1000) if answered else 10.0
    return {
        "unit": unit,
        "value": value,
        "done": round(done) if unit == "cards" else round(done, 1),
        "pct": min(1.0, done / value) if value else 0.0,
        "streak": streak,
        "avg_secs": round(avg_secs, 1),
        "today_cards": per_day.get(0, (0, 0))[0],
        "today_minutes": round(per_day.get(0, (0, 0))[1] / 60000, 1),
    }


def plan(col, root: int | None) -> list[dict[str, Any]]:
    """The matérias with cards for today, weakest first."""
    nodes = due_nodes(col)
    rows = []
    for name, did in matter_decks(col, root):
        node = nodes.get(did)
        new, learn, review = (node.new_count, node.learn_count, node.review_count) if node else (0, 0, 0)
        acc, answers = accuracy(col, subtree(col, did), 30)
        rows.append(
            {
                "did": did,
                "name": name,
                "new": new,
                "learn": learn,
                "review": review,
                "due": new + learn + review,
                "acc": acc,
                "answers": answers,
            }
        )
    rows.sort(key=lambda r: (r["due"] == 0, r["acc"] if r["acc"] is not None else 2.0, r["name"].lower()))
    return rows
