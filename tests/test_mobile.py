"""The phone block in the note type's templates: added, updated and taken out cleanly."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "painel_estudos"


def load(name):
    # Loaded by path: importing the package would start the add-on, which needs a running Anki.
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mobile = load("mobile")
cards = load("cards")

FRONT = "{{Frente}}"
BACK = "{{FrontSide}}\n\n<hr id=answer>\n\n{{Verso}}"


def test_assets_are_safe_inside_a_template():
    script, style = mobile.assets()
    assert "{{" not in script and "}}" not in script and "{{" not in style and "}}" not in style
    assert "</script" not in script.lower()
    with pytest.raises(ValueError):
        mobile.check("var a = { b: { c: 1 }};", "")


def test_apply_and_strip_give_back_the_template():
    script, style = mobile.assets()
    front = mobile.apply(FRONT, "q", script, style)
    back = mobile.apply(BACK, "a", script, style)
    assert front.startswith(FRONT) and back.startswith(BACK)
    assert mobile.version_of(front) == mobile.VERSION
    assert mobile.strip(front) == FRONT and mobile.strip(back) == BACK
    # applying again keeps a single block
    again = mobile.apply(front, "q", script, style)
    assert again == front and again.count("painel-estudos:celular v") == 1


def test_older_block_is_replaced():
    script, style = mobile.assets()
    old = FRONT + "\n\n<!-- painel-estudos:celular v0 -->\n<script>velho</script>\n<!-- /painel-estudos:celular -->"
    assert mobile.state_of([{"qfmt": old, "afmt": BACK}]) == "old"
    new = mobile.apply(old, "q", script, style)
    assert "velho" not in new and mobile.version_of(new) == mobile.VERSION
    on = [{"qfmt": new, "afmt": mobile.apply(BACK, "a", script, style)}]
    assert mobile.state_of(on) == "on"
    assert mobile.state_of([{"qfmt": FRONT, "afmt": BACK}]) == "off"


def test_the_panel_reads_cards_that_carry_the_block():
    script, style = mobile.assets()
    block_q = mobile.block("q", script, style)
    block_a = mobile.block("a", script, style)
    style_tag = "<style>.card { font-family: arial; }</style>"
    mc_front = (
        "Segundo a Lei 14.133/2021, são modalidades de licitação:<br><br>A) pregão.<br>B) convite.<br>C) tomada de preços."
    )
    question = style_tag + mc_front + block_q
    answer = style_tag + mc_front + block_q + "\n\n<hr id=answer>\n\n<b>Gabarito: A</b><br>O art. 28..." + block_a
    parsed = cards.parse(question, answer)
    assert parsed.mode == "mc" and parsed.correct == "A" and [l for l, _ in parsed.options] == ["A", "B", "C"]
    assert "pe-m" not in parsed.front and "<script" not in parsed.back
    ce_front = "[Art. 155, §1º] A pena aumenta-se de metade.<br><br>( ) Certo &nbsp;&nbsp;&nbsp; ( ) Errado"
    parsed = cards.parse(style_tag + ce_front + block_q, style_tag + ce_front + block_q + "<hr id=answer><b>❌ ERRADO</b><br><br>🔁 metade → <b>1/3</b>" + block_a)
    assert parsed.mode == "ce" and parsed.correct == "ERRADO" and parsed.trap == ("metade", "1/3")
