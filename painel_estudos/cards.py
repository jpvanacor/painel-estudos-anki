"""Recognizes the card formats made by João's flashcard skills.

Certo/Errado cards (skill anki-lei-seca): the front ends with "( ) Certo ( ) Errado" and
the back starts with "✅ CERTO" or "❌ ERRADO".

Question cards (skill questoes-concurso): the front lists the alternatives "A) ..." to "E) ..."
after the question, and the back starts with "Gabarito: X".

Any other card is studied the normal Anki way. This module has no Anki imports, so it can be
tested on its own.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field

STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
ANSWER_SPLIT_RE = re.compile(r"<hr\b[^>]*\bid\s*=\s*[\"']?answer[\"']?[^>]*>", re.I)
BR_RE = re.compile(r"<br\s*/?>", re.I)
BLOCK_RE = re.compile(r"</?(?:div|p)\b[^>]*>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
AV_REF_RE = re.compile(r"\[anki:play:[qa]:\d+\]")
TYPE_ANS_RE = re.compile(r"\[\[type:[^\]]*\]\]")

_SPACE = r"(?:\s|&nbsp;|&#160;| )"
CE_LINE_RE = re.compile(
    rf"(?:<br\s*/?>|{_SPACE})*\(\s*\)\s*Certo{_SPACE}*\(\s*\)\s*Errado{_SPACE}*(?:<br\s*/?>)*",
    re.I,
)
CE_ANSWER_RE = re.compile(r"^[\W_]*(?:gabarito\s*[:\-]?\s*)?(certo|errado)\b", re.I)
MC_ANSWER_RE = re.compile(r"gabarito\s*[:\-]?\s*(?:letra\s+)?\(?([A-E])\)?(?![\w])", re.I)
ALT_RE = re.compile(r"^\s*(?:<[^>]+>\s*)*\(?([A-Ea-e])\s*\)\s*(?:</[^>]+>\s*)*(.*)$", re.S)
# The line of an ERRADO item that names the change: "🔁 metade → <b>1/3 (um terço)</b>"
TRAP_RE = re.compile(r"\U0001F501\ufe0f?\s*(.+?)\s*(?:→|->|⟶)\s*(.+?)(?:<br\s*/?>|</p>|</div>|$)", re.S | re.I)

LETTERS = "ABCDE"


@dataclass
class ParsedCard:
    mode: str  # "ce", "mc" or "basic"
    css: str = ""
    front: str = ""  # what is shown before answering
    back: str = ""  # the back side alone (explanation)
    answer_full: str = ""  # the whole answer side, for normal cards
    correct: str | None = None  # "CERTO", "ERRADO" or a letter
    options: list[tuple[str, str]] = field(default_factory=list)
    trap: tuple[str, str] | None = None  # (as written in the statement, what the law says)

    def check(self, choice: str) -> bool:
        return self.correct is not None and choice.strip().upper() == self.correct


def text_of(fragment: str) -> str:
    """Plain text of an HTML fragment, for reading the gabarito."""
    text = BR_RE.sub("\n", fragment)
    text = TAG_RE.sub(" ", text)
    return re.sub(r"[ \t ]+", " ", _html.unescape(text)).strip()


def split_styles(rendered: str) -> tuple[str, str]:
    """Separates the note type's <style> blocks from the card content."""
    styles = "".join(STYLE_RE.findall(rendered))
    return styles, STYLE_RE.sub("", rendered).strip()


def clean(rendered: str) -> str:
    """Removes Anki's audio markers and type-in fields, which this interface draws itself."""
    return TYPE_ANS_RE.sub("", AV_REF_RE.sub("", rendered))


def trap_of(back_html: str) -> tuple[str, str] | None:
    """The "🔁 X → Y" line of an ERRADO item: X as written in the statement, Y as in the law."""
    match = TRAP_RE.search(back_html or "")
    if not match:
        return None
    wrong, right = text_of(match.group(1)), text_of(match.group(2))
    return (wrong, right) if wrong and right else None


def gabarito_of(back_html: str) -> str | None:
    """"CERTO", "ERRADO" or the letter of a question, read from the back of a card."""
    text = text_of(back_html or "")
    ce = CE_ANSWER_RE.match(text)
    if ce:
        return ce.group(1).upper()
    mc = MC_ANSWER_RE.search(text[:200])
    return mc.group(1).upper() if mc else None


def back_part(answer_body: str) -> str:
    parts = ANSWER_SPLIT_RE.split(answer_body, maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else answer_body


def _segments(body: str) -> list[str]:
    return BR_RE.split(BLOCK_RE.sub("<br>", body))


def parse_alternatives(front_body: str) -> tuple[str, list[tuple[str, str]]] | None:
    """Finds a run of alternatives A), B), ... at the end of the front.

    Returns the question without the alternatives, plus the alternatives, or None.
    """
    segs = _segments(front_body)
    # last non-empty segment index
    end = len(segs)
    while end and not text_of(segs[end - 1]):
        end -= 1
    found: list[tuple[str, str]] = []
    start = end
    expected = None
    i = end - 1
    while i >= 0:
        seg = segs[i]
        if not text_of(seg):
            i -= 1
            continue
        m = ALT_RE.match(seg)
        if not m:
            break
        letter = m.group(1).upper()
        if expected is not None and letter != expected:
            break
        found.insert(0, (letter, m.group(2).strip()))
        start = i
        if letter == "A":
            break
        expected = LETTERS[LETTERS.index(letter) - 1]
        i -= 1
    if len(found) < 2 or found[0][0] != "A":
        return None
    stem_segs = segs[:start]
    while stem_segs and not text_of(stem_segs[-1]):
        stem_segs.pop()
    return "<br>".join(stem_segs), found


def parse(question_html: str, answer_html: str) -> ParsedCard:
    """Decides how a card is studied, from Anki's rendered question and answer."""
    css, q_body = split_styles(clean(question_html))
    _css2, a_body = split_styles(clean(answer_html))
    back = back_part(a_body)
    back_text = text_of(back)

    has_ce_line = bool(CE_LINE_RE.search(q_body))
    alternatives = parse_alternatives(q_body)
    ce = CE_ANSWER_RE.match(back_text)
    if ce and (has_ce_line or not alternatives):
        front = CE_LINE_RE.sub("", q_body).strip()
        return ParsedCard(
            mode="ce",
            css=css,
            front=front,
            back=back,
            answer_full=CE_LINE_RE.sub("", a_body),
            correct=ce.group(1).upper(),
            trap=trap_of(back) if ce.group(1).upper() == "ERRADO" else None,
        )

    mc = MC_ANSWER_RE.search(back_text[:200])
    if alternatives and mc:
        stem, options = alternatives
        letter = mc.group(1).upper()
        if letter in {opt[0] for opt in options}:
            return ParsedCard(
                mode="mc",
                css=css,
                front=stem,
                back=back,
                answer_full=a_body,
                correct=letter,
                options=options,
            )

    return ParsedCard(mode="basic", css=css, front=q_body, back=back, answer_full=a_body)
