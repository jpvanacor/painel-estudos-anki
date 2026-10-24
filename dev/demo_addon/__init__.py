"""Test-only add-on: clicks through the Painel de Estudos like a person and saves screenshots.

Installed only in the throwaway test profile made by dev/make_test_profile.py.
Screenshots go to the folder in the PAINEL_SHOTS environment variable.
"""

import json
import os

from aqt import gui_hooks, mw
from aqt.qt import QGuiApplication, QTimer
from aqt.theme import Theme

SHOTS = os.environ.get("PAINEL_SHOTS", "")
EDITAL = {
    "Direito Penal": [
        "Crimes contra a pessoa (Arts. 121 a 154)",
        "Crimes contra o patrimônio (Arts. 155 a 183)",
        "Imputabilidade penal (Arts. 26 a 28)",
    ],
    "Direito Administrativo": {
        "Lei de Improbidade (8.429/92)": ["Sujeitos", "Atos de improbidade", "Sanções"],
        "Lei de Licitações (14.133/21)": ["Princípios", "Modalidades"],
    },
    "Processo Penal": ["Ação penal (Arts. 24 a 62)"],
    "Direito Civil": ["Prescrição e decadência (Arts. 189 a 211)"],
}


def log(msg):
    print(f"[demo] {msg}", flush=True)


def shot(name):
    QGuiApplication.primaryScreen().grabWindow(0).save(os.path.join(SHOTS, name + ".png"))
    log(f"shot {name}")


def js(code):
    mw.painel_estudos.web.eval(code)


def click(selector):
    js(f"(function(){{var el=document.querySelector({json.dumps(selector)}); if(el) el.click(); else console.log('demo: missing ' + {json.dumps(selector)});}})()")


def key(k):
    js(f"document.dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(k)}, bubbles: true}}))")


def report_state(label):
    mw.painel_estudos.web.evalWithCallback("JSON.stringify(window.PE && PE.state())", lambda r: log(f"{label}: {r}"))


def theme(dark):
    mw.set_theme(Theme.DARK if dark else Theme.LIGHT)


def answer(right):
    """Picks the right or a wrong choice on purpose, by asking the add-on for the gabarito."""
    parsed = mw.painel_estudos.api.parsed
    if not parsed or parsed.mode not in ("ce", "mc"):
        log(f"answer({right}): current card is {parsed and parsed.mode}")
        return
    if parsed.mode == "ce":
        choice = parsed.correct if right else ("ERRADO" if parsed.correct == "CERTO" else "CERTO")
        key("c" if choice == "CERTO" else "e")
    else:
        letters = [letter for letter, _ in parsed.options]
        choice = parsed.correct if right else next(l for l in letters if l != parsed.correct)
        key(choice.lower())
    log(f"answered {choice} (gabarito {parsed.correct})")


def advance():
    """Answers the current card (right, then Fácil) so the session moves toward its end."""
    api = mw.painel_estudos.api
    if not api.card:
        return
    if api.parsed.mode == "basic":
        key(" " if api.phase == "question" else "4")
    elif api.phase == "question":
        answer(True)
    else:
        key("4")


def undo_key():
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'z', ctrlKey: true, bubbles: true}))")


def study_deck(name):
    js(
        "document.querySelectorAll('[data-act=\"study\"][data-did]').forEach(function(b){"
        f" if (b.closest('tr').textContent.indexOf({json.dumps(name)}) >= 0) b.click(); }})"
    )


def open_row(name):
    js(
        "(function(){var rows=[].slice.call(document.querySelectorAll('tr[data-go]'));"
        f" var row=rows.filter(function(r){{return r.textContent.indexOf({json.dumps(name)})>=0;}})[0]; if(row) row.click();}})()"
    )


STEPS = [
    (lambda: shot("01_hoje"), 1500),
    (lambda: click('[data-go="edital"]'), 1500),
    (lambda: js(f"document.getElementById('paste').value = {json.dumps(json.dumps(EDITAL, ensure_ascii=False, indent=2))}"), 300),
    (lambda: click('[data-act="import"]'), 1800),
    (lambda: click('[data-act="draw"]'), 1500),
    (lambda: shot("02_edital"), 400),
    (lambda: click('[data-go="home"]'), 1800),
    (lambda: shot("03_hoje_com_topico"), 400),
    # Estudar tudo: the weakest matéria (Direito Penal) comes first
    (lambda: click('[data-act="study"]'), 2200),
    (lambda: report_state("first card"), 300),
    (lambda: shot("04_ce_pergunta"), 300),
    (lambda: answer(False), 1800),
    (lambda: shot("05_ce_errou"), 300),
    (lambda: key(" "), 2000),  # Continuar = De novo
    (lambda: report_state("second card"), 300),
    (lambda: answer(True), 1800),
    (lambda: shot("06_ce_acertou"), 300),
    (lambda: key("3"), 2000),  # Bom
    (lambda: report_state("third card"), 300),
    (lambda: undo_key(), 2000),  # Ctrl+Z: the card answered Bom comes back
    (lambda: report_state("after undo"), 300),
    (lambda: shot("06b_desfeito"), 300),
    (lambda: click('[data-act="end"]'), 1800),
    # matérias, then Direito Administrativo with multiple choice
    (lambda: click('[data-go="materias"]'), 1600),
    (lambda: shot("07_materias"), 300),
    (lambda: open_row("Direito Penal"), 1800),
    (lambda: shot("08_materia"), 300),
    (lambda: js("PE.go('home')"), 1600),
    (lambda: study_deck("Administrativo"), 2200),
    (lambda: shot("09_mc_pergunta"), 300),
    (lambda: answer(False), 1800),
    (lambda: shot("10_mc_errou"), 300),
    (lambda: key("enter"), 2000),
    (lambda: report_state("after mc"), 300),
    (lambda: answer(True), 1800),
    (lambda: shot("11_mc_acertou"), 300),
    (lambda: key("2"), 1800),  # Difícil
    (lambda: click('[data-act="end"]'), 1600),
    # Direito Civil: normal cards
    (lambda: study_deck("Civil"), 2200),
    (lambda: key(" "), 1800),
    (lambda: shot("12_normal_resposta"), 300),
    (lambda: key("4"), 1800),  # Fácil
    (lambda: key(" "), 1500),
    (lambda: key("3"), 1800),  # Bom: goes to learning and comes back, as in Anki
    *[(advance, 1400) for _ in range(6)],
    (lambda: shot("13_fim_sessao"), 300),
    (lambda: click('[data-go="ajustes"]'), 1600),
    (lambda: shot("14_ajustes"), 300),
    # dark theme
    (lambda: theme(True), 2200),
    (lambda: js("PE.go('home')"), 1800),
    (lambda: shot("15_hoje_escuro"), 300),
    (lambda: click('[data-act="study"]'), 2200),
    (lambda: answer(True), 1800),
    (lambda: shot("16_ce_escuro"), 300),
    (lambda: click('[data-act="end"]'), 1500),
    (lambda: theme(False), 2000),
    # back to Anki's own interface and to the panel again
    (lambda: click('[data-open="anki"]'), 2200),
    (lambda: shot("17_interface_anki"), 300),
    (lambda: mw.painel_estudos.action.trigger(), 2200),
    (lambda: shot("18_painel_de_volta"), 300),
    (lambda: mw.close(), 0),
]


def run(i=0):
    if i >= len(STEPS):
        return
    step, wait = STEPS[i]
    try:
        step()
    except Exception as err:  # keep going, but say what failed
        log(f"step {i} failed: {err!r}")
    QTimer.singleShot(wait, lambda: run(i + 1))


def start():
    if not SHOTS:
        return
    mw.move(0, 0)
    mw.resize(1280, 800)
    QTimer.singleShot(4000, run)


gui_hooks.profile_did_open.append(start)
