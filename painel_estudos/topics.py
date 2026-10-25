"""Finds the Anki cards of a Roleta topic.

Topic names made by the exportar-roleta skill carry the articles they cover, as in
"Crimes contra o patrimônio (Arts. 155 a 183)", and cards made by the anki-lei-seca skill start
with the article they test, as in "[Art. 155, §1º] ...". A topic's cards are the cards of its
matéria's deck whose leading article falls in the topic's ranges.

A deck can hold more than one law (the art. 33 of the Código Penal and the art. 33 of the Lei de
Drogas). The law of a card comes from its tag (matéria::legislação::...); when the matched cards
belong to more than one law, the names of the matéria and subcategory pick one, or the person
chooses once and the choice is kept on the topic.

Topics without articles can be tied to a tag instead. No Anki imports here.
"""

from __future__ import annotations

import html as _html
import re
import unicodedata
from collections import Counter
from typing import Any

KEYWORD_RE = re.compile(r"\b(?:arts?|artigos?)\b\.?\s*", re.I)
NUM_RE = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(?:º|°|ª|o(?![a-z]))?(?:\s*-\s*[a-z]{1,2}(?![a-z]))?", re.I)
RANGE_RE = re.compile(r"\s*(?:a|ao|à|até|–|—|-)\s*(?=\d)", re.I)
LIST_RE = re.compile(r"\s*(?:,|;|\be\b)\s*(?=\d)", re.I)
LEAD_RE = re.compile(r"^\s*\[([^\]]{1,160})\]")
TAG_RE = re.compile(r"<[^>]+>")
CE_LINE_RE = re.compile(r"\(\s*\)\s*Certo\s*\(\s*\)\s*Errado\s*$", re.I)
META_TAGS = ("banca::", "ano::", "leech", "marked", "duplicate")
MAX_SPAN = 2000

Range = tuple[int, int]

# Names of matérias and subcategories that point to a law, and the keys its tags use.
ALIASES = [
    ("codigo de processo penal", {"cpp"}),
    ("processo penal", {"cpp"}),
    ("processual penal", {"cpp"}),
    ("codigo de processo civil", {"cpc"}),
    ("processo civil", {"cpc"}),
    ("processual civil", {"cpc"}),
    ("codigo penal", {"cp"}),
    ("codigo civil", {"cc"}),
    ("constituicao", {"cf", "cf88", "crfb", "crfb88"}),
    ("constitucional", {"cf", "cf88", "crfb", "crfb88"}),
    ("codigo tributario", {"ctn"}),
    ("defesa do consumidor", {"cdc"}),
    ("crianca e do adolescente", {"eca"}),
    ("improbidade", {"lia", "lei8429"}),
    ("licitacoes", {"lei14133"}),
    ("execucao penal", {"lep", "lei7210"}),
    ("maria da penha", {"lei11340"}),
    ("drogas", {"lei11343"}),
]
STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "na", "no", "nas", "nos", "por",
    "para", "com", "ao", "aos", "um", "uma", "art", "arts", "artigo", "artigos", "lei", "geral",
}


# ------------------------------------------------------------------ text
def fold(value: Any) -> str:
    """Lower case, no accents, single spaces."""
    text = unicodedata.normalize("NFD", "" if value is None else str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


def key_of(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", fold(value))


def plain(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>|</(?:div|p)>", " ", str(fragment or ""), flags=re.I)
    text = _html.unescape(TAG_RE.sub(" ", text)).replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def statement(front_html: str) -> str:
    """The text of a card's front, without the "( ) Certo ( ) Errado" line."""
    return CE_LINE_RE.sub("", plain(front_html)).strip()


# ------------------------------------------------------------------ articles
def _num(token: str) -> int:
    return int(token.replace(".", ""))


def _span(lo: int, hi: int) -> Range | None:
    if hi < lo:
        lo, hi = hi, lo
    return (lo, hi) if hi - lo <= MAX_SPAN else None


def parse_articles(text: Any) -> list[Range]:
    """Article ranges cited in a text: "(Arts. 155 a 183)" -> [(155, 183)].

    Reads "Art. 5º", "Arts. 18 e 19", "Arts. 1º a 4º", "Arts. 1.228 a 1.368", "Arts. 121 a
    154-B", "Arts. 5º a 17 e 22". Paragraphs and incisos after a comma ("Art. 121, §2º, I") are
    left out.
    """
    s = str(text or "")
    out: list[Range] = []
    for match in KEYWORD_RE.finditer(s):
        first = NUM_RE.match(s, match.end())
        if not first:
            continue
        current: int | None = _num(first.group(1))
        pos = first.end()
        while True:
            sep = RANGE_RE.match(s, pos)
            nxt = NUM_RE.match(s, sep.end()) if sep else None
            if nxt and current is not None:
                span = _span(current, _num(nxt.group(1)))
                if span:
                    out.append(span)
                current = None
                pos = nxt.end()
                continue
            sep = LIST_RE.match(s, pos)
            nxt = NUM_RE.match(s, sep.end()) if sep else None
            if not nxt:
                break
            if current is not None:
                out.append((current, current))
            current = _num(nxt.group(1))
            pos = nxt.end()
        if current is not None:
            out.append((current, current))
    return out


def card_articles(front_html: str) -> list[Range]:
    """The article a card tests, from the "[Art. 155, §1º]" that starts its front."""
    lead = LEAD_RE.match(plain(front_html)[:300])
    return parse_articles(lead.group(1)) if lead else []


def overlaps(a: list[Range], b: list[Range]) -> bool:
    return any(lo1 <= hi2 and lo2 <= hi1 for lo1, hi1 in a for lo2, hi2 in b)


def ranges_text(ranges: list[Range]) -> str:
    """[(155, 183)] -> "arts. 155 a 183"; [(5, 5)] -> "art. 5"."""
    parts = [f"{lo} a {hi}" if hi != lo else str(lo) for lo, hi in ranges]
    many = len(ranges) > 1 or any(hi != lo for lo, hi in ranges)
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " e " + parts[-1]
    return f"arts. {joined}" if many else f"art. {joined}"


def ranges_label(ranges: list[Range]) -> str:
    """[(155, 183)] -> "pelos arts. 155 a 183"; [(5, 5)] -> "pelo art. 5"."""
    text = ranges_text(ranges)
    return ("pelos " if text.startswith("arts.") else "pelo ") + text


# ------------------------------------------------------------------ laws and tags
def content_tags(tags: Any) -> list[str]:
    items = tags.split() if isinstance(tags, str) else list(tags or [])
    return [t for t in items if not t.lower().startswith(META_TAGS)]


def law_of_tags(tags: Any) -> tuple[str, str] | None:
    """(key, label) of the law in the first hierarchical tag: direito_penal::CP::... -> ("cp", "CP")."""
    for tag in content_tags(tags):
        parts = tag.split("::")
        if len(parts) >= 2 and key_of(parts[1]):
            return key_of(parts[1]), pretty(parts[1])
    return None


def pretty(part: str) -> str:
    words = part.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def tag_label(tag: str) -> str:
    """direito_penal::CP::parte_especial::crimes_contra_patrimonio -> CP › Parte especial › Crimes contra patrimonio"""
    parts = tag.split("::")
    if len(parts) > 1:
        parts = parts[1:]
    return " › ".join(pretty(p) for p in parts)


def law_hints(names: list[str]) -> tuple[set[str], set[str]]:
    """Law keys and law numbers named by the matéria, subcategory and deck."""
    keys: set[str] = set()
    numbers: set[str] = set()
    for name in names:
        folded = fold(name)
        for words, found in ALIASES:
            if words in folded:
                keys |= found
        for token in re.findall(r"\d{1,3}(?:\.\d{3})+|\d{3,}", folded):
            numbers.add(token.replace(".", ""))
    return keys, numbers


def pick_law(laws: Counter, names: list[str]) -> str | None:
    keys, numbers = law_hints(names)
    hits = [law for law in laws if law in keys or (re.sub(r"\D", "", law) in numbers)]
    return hits[0] if len(hits) == 1 else None


def tag_counts(entries: list[dict]) -> dict[str, int]:
    """Cards under each tag and its parents (from the second level down)."""
    counts: Counter = Counter()
    for entry in entries:
        if not entry["ok"]:
            continue
        seen: set[str] = set()
        for tag in content_tags(entry["tags"]):
            parts = tag.split("::")
            for depth in range(2, len(parts) + 1):
                key = "::".join(parts[:depth])
                if key.lower() not in seen:
                    seen.add(key.lower())
                    counts[key] += 1
    return dict(counts)


def _words(text: str) -> set[str]:
    text = fold(re.sub(r"\([^)]*\)", " ", str(text or "")))
    return {w for w in re.split(r"[^a-z0-9]+", text) if w and w not in STOPWORDS and not w.isdigit()}


def suggest_tag(topic_text: str, counts: dict[str, int]) -> str | None:
    """A tag whose last part has the same words as the topic name, for topics without articles."""
    wanted = _words(topic_text)
    if not wanted:
        return None
    best: tuple[float, int, str] | None = None
    for tag, n in counts.items():
        have = _words(tag.split("::")[-1].replace("_", " "))
        if not have:
            continue
        common = wanted & have
        score = len(common) / len(wanted | have)
        if score >= 0.6 and (len(common) >= 2 or have == wanted):
            candidate = (score, n, tag)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    return best[2] if best else None


def has_tag(tags: list[str], wanted: str) -> bool:
    wanted = wanted.lower()
    return any(t.lower() == wanted or t.lower().startswith(wanted + "::") for t in tags)


# ------------------------------------------------------------------ a topic's cards
def topic_cards(topic_text: str, link: dict | None, entries: list[dict], names: list[str]) -> dict:
    """Which cards belong to a topic.

    entries: one per card of the matéria's deck, {"cid", "ok" (can be studied), "arts" (ranges
    from card_articles), "law" (key or None), "law_label", "tags"}.
    link: what the topic keeps, None (by articles), {"law": key} or {"tag": tag}.
    Returns the mode ("tag", "articles" or "none"), the card ids that can be studied ("cids")
    and, for articles, the laws found and whether a law still has to be chosen ("ambiguous").
    """
    link = link if isinstance(link, dict) else {}
    ranges = parse_articles(topic_text)
    if link.get("tag"):
        picked = [e for e in entries if has_tag(e["tags"], link["tag"])]
        return {"mode": "tag", "tag": link["tag"], "has_articles": bool(ranges), "cids": [e["cid"] for e in picked if e["ok"]]}
    if not ranges:
        return {"mode": "none", "has_articles": False, "cids": []}
    picked = [e for e in entries if e["arts"] and overlaps(e["arts"], ranges)]
    laws = Counter(e["law"] for e in picked if e["law"])
    labels = {e["law"]: e["law_label"] for e in picked if e["law"]}
    law = None
    ambiguous = False
    if len(laws) > 1:
        wanted = link.get("law")
        law = wanted if wanted in laws else pick_law(laws, names)
        if law:
            picked = [e for e in picked if e["law"] == law]
        else:
            ambiguous = True
    elif len(laws) == 1:
        law = next(iter(laws))
    return {
        "mode": "articles",
        "has_articles": True,
        "ranges": ranges,
        "arts_label": ranges_label(ranges),
        "arts_text": ranges_text(ranges),
        "laws": [{"key": k, "label": labels[k], "n": n} for k, n in laws.most_common()],
        "law": law,
        "law_label": labels.get(law) if law else None,
        "chosen": bool(link.get("law")) and link.get("law") == law,
        "ambiguous": ambiguous,
        "cids": [] if ambiguous else [e["cid"] for e in picked if e["ok"]],
    }
