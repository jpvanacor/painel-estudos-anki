"""Test-only add-on: clicks through the Painel de Estudos like a person and saves screenshots.

Installed only in the throwaway test profile made by dev/make_test_profile.py.
Screenshots go to the folder in PAINEL_SHOTS; PAINEL_FIXTURE points to a Roleta backup to import.
"""

import json
import os

from aqt import gui_hooks, mw
from aqt.qt import QGuiApplication, QTimer
from aqt.theme import Theme

SHOTS = os.environ.get("PAINEL_SHOTS", "")
FIXTURE = os.environ.get("PAINEL_FIXTURE", "")


def log(msg):
    print(f"[demo] {msg}", flush=True)


def shot(name):
    QGuiApplication.primaryScreen().grabWindow(0).save(os.path.join(SHOTS, name + ".png"))
    log(f"shot {name}")


def js(code):
    mw.painel_estudos.web.eval(code)


def click(selector):
    js(f"(function(){{var el=document.querySelector({json.dumps(selector)}); if(el) el.click(); else console.log('demo: missing ' + {json.dumps(selector)});}})()")


def key(k, **mods):
    opts = {"key": k, "bubbles": True, **mods}
    js(f"document.dispatchEvent(new KeyboardEvent('keydown', {json.dumps(opts)}))")


def report(label, expr="JSON.stringify(window.PE && PE.state())"):
    mw.painel_estudos.web.evalWithCallback(expr, lambda r: log(f"{label}: {r}"))


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
    api = mw.painel_estudos.api
    if not api.card:
        return
    if api.parsed.mode == "basic":
        key(" " if api.phase == "question" else "4")
    elif api.phase == "question":
        answer(True)
    else:
        key("4")


def study_deck(name):
    js(
        "document.querySelectorAll('tr [data-act=\"study\"][data-did]').forEach(function(b){"
        f" if (b.closest('tr').textContent.indexOf({json.dumps(name)}) >= 0) b.click(); }})"
    )


def open_row(name):
    js(
        "(function(){var rows=[].slice.call(document.querySelectorAll('tr[data-go]'));"
        f" var row=rows.filter(function(r){{return r.textContent.indexOf({json.dumps(name)})>=0;}})[0]; if(row) row.click();}})()"
    )


def paste_fixture():
    with open(FIXTURE, encoding="utf-8") as handle:
        text = handle.read()
    js(f"document.getElementById('ro-paste').value = {json.dumps(text)}")


def type_note(text):
    js(
        "(function(){var t=document.querySelector('textarea[data-note]'); if(!t) return;"
        f" t.value={json.dumps(text)}; t.dispatchEvent(new Event('input', {{bubbles:true}}));}})()"
    )


def roleta_state(label):
    state = mw.painel_estudos.api._data()["roleta"]
    cats = [(c["name"], c.get("deck"), sum(len(s["topics"]) for s in c["subs"]), sum(1 for s in c["subs"] for t in s["topics"] if t["seen"])) for c in state["cats"]]
    notes = [t["t"] for c in state["cats"] for s in c["subs"] for t in s["topics"] if t.get("note")]
    log(f"{label}: cats={cats} last={state.get('last')} notes={notes}")


def render_sounds():
    js("Promise.all(PE.sounds().map(function(n){return PE.renderSound(n, 3);})).then(function(r){window.__sfx=r;})")


STEPS = [
    (lambda: js("window.addEventListener('error', function(e){ console.error('STACK ' + (e.error && e.error.stack)); });"), 100),
    (lambda: report("motion", "JSON.stringify({reduced: matchMedia('(prefers-reduced-motion: reduce)').matches, noMotion: document.documentElement.classList.contains('no-motion')})"), 200),
    (lambda: roleta_state("converted from 0.1"), 300),
    (lambda: shot("01_hoje"), 300),
    (lambda: js("var m=document.getElementById('main'); m.scrollTop = m.scrollHeight;"), 500),
    (lambda: shot("01b_hoje_roleta"), 300),
    (lambda: js("document.getElementById('main').scrollTop = 0;"), 900),
    # study: Certo/Errado with animation, crossing the goal (39) on the second answer
    (lambda: click('[data-act="study"]'), 2200),
    (lambda: answer(False), 140),
    (lambda: shot("02_ce_errou_animando"), 1600),
    (lambda: shot("03_ce_errou"), 300),
    (lambda: key(" "), 1800),
    (lambda: answer(True), 1600),
    (lambda: shot("04_ce_acertou"), 300),
    (lambda: key("3"), 450),
    (lambda: shot("05_meta_cumprida"), 2600),
    (lambda: key("z", ctrlKey=True), 1800),
    (lambda: report("after undo"), 300),
    (lambda: click('[data-act="end"]'), 1800),
    # multiple choice
    (lambda: study_deck("Administrativo"), 2200),
    (lambda: answer(False), 1600),
    (lambda: shot("06_mc_errou"), 300),
    (lambda: key("enter"), 1800),
    (lambda: answer(True), 1600),
    (lambda: key("2"), 1800),
    (lambda: click('[data-act="end"]'), 1600),
    # normal cards until the deck is done
    (lambda: study_deck("Civil"), 2200),
    (lambda: key(" "), 1600),
    (lambda: key("4"), 1600),
    *[(advance, 1300) for _ in range(6)],
    (lambda: shot("07_fim_sessao_animando"), 900),
    (lambda: shot("08_fim_sessao"), 300),
    # the Roleta: the 0.1 edital became a matéria, then a Roleta backup replaces it
    (lambda: click('[data-go="roleta"]'), 1800),
    (lambda: shot("09_roleta_convertida"), 300),
    (lambda: click('[data-act="ro-import"]'), 900),
    (paste_fixture, 300),
    (lambda: shot("10_importar"), 300),
    (lambda: click('[data-act="ro-do-import"]'), 1200),
    (lambda: shot("11_confirmar_backup"), 300),
    (lambda: click('[data-act="ask-ok"]'), 1800),
    (lambda: roleta_state("after backup import"), 300),
    (lambda: shot("12_roleta_importada"), 300),
    # spin with Space; picture mid-spin and the result
    (lambda: key(" "), 1300),
    (lambda: report("spinning"), 200),
    (lambda: shot("13_girando"), 5200),
    (lambda: report("after spin"), 300),
    (lambda: shot("14_resultado"), 300),
    (lambda: type_note("Ler os arts. 13 a 25 antes dos cartões"), 900),
    (lambda: click('[data-act="ro-again"]'), 6600),
    (lambda: roleta_state("after sortear outro"), 300),
    (lambda: shot("15_sortear_outro"), 300),
    (lambda: key("Escape"), 900),
    (lambda: click('[data-act="ro-sel"][data-sel="s-pe"]'), 1200),
    (lambda: shot("16_subcategoria"), 300),
    (lambda: click('[data-act="ro-tab"][data-tab="list"]'), 900),
    (lambda: js("var s=document.getElementById('ro-search'); s.value='crimes'; s.dispatchEvent(new Event('input',{bubbles:true}));"), 900),
    (lambda: shot("17_topicos_busca"), 300),
    (lambda: click('[data-act="ro-remove"]'), 1000),
    (lambda: shot("18_remover_desfazer"), 300),
    (lambda: click(".toast-act"), 1200),
    (lambda: roleta_state("after remove and undo"), 300),
    (lambda: click('[data-act="ro-org"]'), 1000),
    (lambda: shot("19_organizar"), 300),
    (lambda: key("Escape"), 800),
    # sounds rendered offline and measured
    (render_sounds, 2500),
    (lambda: report("sounds", "JSON.stringify(window.__sfx)"), 600),
    # dark theme
    (lambda: theme(True), 2200),
    (lambda: key(" "), 6200),
    (lambda: shot("20_roleta_escura"), 300),
    (lambda: key("Escape"), 800),
    (lambda: shot("20b_roleta_escura_parada"), 300),
    (lambda: js("PE.go('home')"), 1800),
    (lambda: shot("21_hoje_escuro"), 300),
    (lambda: js("var m=document.getElementById('main'); m.scrollTop = m.scrollHeight;"), 500),
    (lambda: shot("21b_hoje_roleta_escuro"), 300),
    (lambda: theme(False), 2000),
    (lambda: click('[data-go="ajustes"]'), 1600),
    (lambda: js("window.scrollTo(0,0); var m=document.getElementById('main'); m.scrollTop = m.scrollHeight;"), 600),
    (lambda: shot("22_ajustes_sons"), 300),
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
