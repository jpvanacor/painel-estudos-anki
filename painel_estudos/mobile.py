"""The phone part: a script and its styles that go inside the note type's templates.

AnkiDroid doesn't run add-ons, but it runs the scripts in card templates, and the templates sync
with the collection. So the panel puts celular/celular.js and celular.css at the end of the front
and back templates of the note types that hold Certo/Errado items and questions. The block sits
between two HTML comments, so it can be updated or taken out without touching the rest of the
template. Changing a template's text is not a schema change: it goes to the phone in a normal
sync, not a full one.

No Anki imports here, so this module is tested on its own.
"""

from __future__ import annotations

import re
from pathlib import Path

VERSION = 1
HERE = Path(__file__).parent / "celular"
START_RE = re.compile(r"<!-- painel-estudos:celular v(\d+) -->")
BLOCK_RE = re.compile(r"(?:\n\n)?<!-- painel-estudos:celular v\d+ -->.*?<!-- /painel-estudos:celular -->", re.S)
# Notes that make a note type worth the block: Certo/Errado items and questions with a gabarito.
NOTES_SQL = "select mid, count() from notes where flds like '%( ) Certo%' or flds like '%Gabarito:%' group by mid"


def assets(folder: Path = HERE) -> tuple[str, str]:
    script = (folder / "celular.js").read_text(encoding="utf-8")
    style = (folder / "celular.css").read_text(encoding="utf-8")
    check(script, style)
    return script, style


def check(script: str, style: str) -> None:
    """Anki reads "{{" as a field, and a closing tag would end the block early."""
    for text in (script, style):
        if "{{" in text or "}}" in text:
            raise ValueError("O código do celular não pode ter chaves duplas.")
        if re.search(r"</(?:script|style)", text, re.I) or "<!-- /painel-estudos" in text:
            raise ValueError("O código do celular não pode fechar o próprio bloco.")


def block(side: str, script: str, style: str) -> str:
    return (
        f"\n\n<!-- painel-estudos:celular v{VERSION} -->\n"
        f'<div class="pe-m" data-side="{side}" hidden></div>\n'
        f"<style>\n{style}</style>\n"
        f"<script>\n{script}</script>\n"
        "<!-- /painel-estudos:celular -->"
    )


def version_of(template: str) -> int | None:
    match = START_RE.search(template or "")
    return int(match.group(1)) if match else None


def strip(template: str) -> str:
    return BLOCK_RE.sub("", template or "")


def apply(template: str, side: str, script: str, style: str) -> str:
    """The template with the current block at its end, replacing an older one."""
    return strip(template) + block(side, script, style)


def state_of(templates: list[dict]) -> str:
    """ "on" (current block everywhere), "old" (a block from another version) or "off"."""
    versions = set()
    for tmpl in templates:
        versions.add(version_of(tmpl.get("qfmt", "")))
        versions.add(version_of(tmpl.get("afmt", "")))
    if versions == {VERSION}:
        return "on"
    return "old" if versions - {None} else "off"
