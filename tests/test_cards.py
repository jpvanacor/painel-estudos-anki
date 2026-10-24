"""Card formats, using the examples from the anki-lei-seca and questoes-concurso skills."""

import importlib.util
import sys
from pathlib import Path

# Loaded by path: importing the package would start the add-on, which needs a running Anki.
_spec = importlib.util.spec_from_file_location("cards", Path(__file__).parents[1] / "painel_estudos" / "cards.py")
cards = importlib.util.module_from_spec(_spec)
sys.modules["cards"] = cards
_spec.loader.exec_module(cards)

STYLE = "<style>.card { font-family: arial; font-size: 20px; text-align: center; }</style>"


def render(front: str, back: str) -> tuple[str, str]:
    """What Anki's Basic note type renders: the question, and FrontSide + <hr id=answer> + back."""
    return STYLE + front, STYLE + front + "\n\n<hr id=answer>\n\n" + back


CE_CERTO_FRONT = (
    "[Art. 155, caput] Quem subtrai coisa alheia móvel para si ou para outrem comete furto simples, "
    "punido com reclusão de 01 (um) a 04 (quatro) anos e multa.<br><br>( ) Certo &nbsp;&nbsp;&nbsp; ( ) Errado"
)
CE_CERTO_BACK = (
    "<b>✅ CERTO</b><br><br>É a regra do <b>furto simples</b>: pegar algo de outra pessoa sem violência nem ameaça."
    "<br><br>📎 Art. 155, caput, CP — <i>\"Subtrair, para si ou para outrem, coisa alheia móvel\"</i>"
)
CE_ERRADO_FRONT = (
    "[Art. 155, §1º] Se o furto é praticado durante o repouso noturno, a pena aumenta-se de metade."
    "<br><br>( ) Certo &nbsp;&nbsp;&nbsp; ( ) Errado"
)
CE_ERRADO_BACK = "<b>❌ ERRADO</b><br><br>🔁 metade → <b>1/3 (um terço)</b><br><br>O aumento é de 1/3 (um terço)."

MC_FRONT = (
    "<b>Direito Administrativo — Improbidade Administrativa</b><br>FUNDATEC — 2026 — Prefeitura de Pontão/RS — "
    "Técnico de Enfermagem<br><br>Giba, servidor público do Município de Pontão/RS, revelou propositalmente um fato "
    "de que teve ciência em razão das suas atribuições e que deveria permanecer em segredo. É correto afirmar que ele "
    "cometeu um ato de improbidade administrativa<br><br>"
    "A) decorrente de concessão ou aplicação indevida de benefício financeiro ou tributário.<br>"
    "B) que atenta contra os princípios da administração pública.<br>"
    "C) que causa prejuízo ao erário.<br>"
    "D) que importa enriquecimento ilícito."
)
MC_BACK = (
    "<b>Gabarito: B</b><br><br>A conduta de Giba configura ato que <b>atenta contra os princípios</b> (art. 11)."
    "<br><br><b>Por que as outras estão erradas:</b><br><br><b>A)</b> Nada a ver com revelação de segredo."
)


def test_certo_errado_certo():
    p = cards.parse(*render(CE_CERTO_FRONT, CE_CERTO_BACK))
    assert p.mode == "ce"
    assert p.correct == "CERTO"
    assert "( ) Certo" not in p.front
    assert p.front.startswith("[Art. 155, caput]")
    assert p.back.startswith("<b>✅ CERTO</b>")
    assert ".card" in p.css
    assert p.check("certo") and not p.check("ERRADO")


def test_certo_errado_errado():
    p = cards.parse(*render(CE_ERRADO_FRONT, CE_ERRADO_BACK))
    assert p.mode == "ce"
    assert p.correct == "ERRADO"
    assert p.front.endswith("aumenta-se de metade.")


def test_multiple_choice():
    p = cards.parse(*render(MC_FRONT, MC_BACK))
    assert p.mode == "mc"
    assert p.correct == "B"
    assert [letter for letter, _ in p.options] == ["A", "B", "C", "D"]
    assert p.options[1][1] == "que atenta contra os princípios da administração pública."
    assert p.front.startswith("<b>Direito Administrativo")
    assert p.front.endswith("improbidade administrativa")
    assert "A) decorrente" not in p.front
    assert p.back.startswith("<b>Gabarito: B</b>")
    assert p.check("b") and not p.check("A")


def test_multiple_choice_with_divs_and_five_options():
    front = (
        "<div>Assinale a alternativa correta.</div><div>A) um</div><div>B) dois</div>"
        "<div>C) três</div><div>D) quatro</div><div>E) cinco</div>"
    )
    p = cards.parse(*render(front, "<b>Gabarito: E</b><br>porque sim"))
    assert p.mode == "mc"
    assert p.correct == "E"
    assert [letter for letter, _ in p.options] == list("ABCDE")
    assert "Assinale" in p.front


def test_alternative_lines_inside_the_question_stay_in_the_stem():
    front = (
        "Considere:<br>A) primeira assertiva do enunciado<br>Agora responda.<br><br>"
        "A) só a primeira<br>B) só a segunda<br>C) ambas"
    )
    p = cards.parse(*render(front, "Gabarito: C"))
    assert p.mode == "mc"
    assert [letter for letter, _ in p.options] == ["A", "B", "C"]
    assert "primeira assertiva" in p.front and "Agora responda." in p.front


def test_cespe_question_with_gabarito_certo():
    front = "<b>Direito Penal</b><br>CESPE — 2024<br><br>Julgue o item: o furto de uso não é crime."
    p = cards.parse(*render(front, "<b>Gabarito: Certo</b><br><br>Explicação."))
    assert p.mode == "ce"
    assert p.correct == "CERTO"


def test_gabarito_letter_is_not_read_from_words():
    # "Errado" must not be read as the letter E. Alternatives plus a Certo/Errado gabarito is
    # inconsistent, so the card falls back to the normal flow.
    p = cards.parse(*render("Pergunta?<br>A) x<br>B) y", "Gabarito: Errado é a palavra"))
    assert p.mode == "basic"
    assert p.correct is None


def test_normal_card():
    p = cards.parse(*render("Qual é o prazo prescricional geral?", "10 anos (art. 205 do CC)"))
    assert p.mode == "basic"
    assert p.correct is None
    assert "<hr id=answer>" in p.answer_full
    assert p.back == "10 anos (art. 205 do CC)"


def test_audio_markers_and_type_fields_are_removed():
    q = STYLE + "Ouça [anki:play:q:0] e digite [[type:Back]]"
    p = cards.parse(q, q + "<hr id=answer>resposta")
    assert "[anki:play" not in p.front and "[[type:" not in p.front
