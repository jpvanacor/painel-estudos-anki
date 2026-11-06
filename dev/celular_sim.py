"""Plays the phone part (celular/celular.js) in pages shaped like AnkiDroid's card page.

Real cards from the test profile are rendered by Anki with the phone block in their note type.
Each side goes in a page like AnkiDroid's: <html class="mobile android linux js">, the card in
<div id="content"> inside <body class="card">, and showAnswer() and buttonAnswerEase1() to 4()
as global functions, the names AnkiDroid's own card.js gives them. Here showAnswer() opens the
answer page (same origin, so sessionStorage carries over, as in AnkiDroid's reviewer) and the
answer functions record the ease. AnkiDroidJS is a stand-in for AnkiDroid's js-api.js, declared the
same way (a class at the top level of a script, so not a property of window): it writes down what
the Modo voz says and when it listens, and the test answers like AnkiDroid does, by calling
window.ankiSttResult. Chromium (Playwright) taps through at phone size and takes screenshots.

Usage: python3 dev/celular_sim.py <work folder>
"""

from __future__ import annotations

import functools
import html
import http.server
import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path

from anki.collection import Collection
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
WORK = Path(sys.argv[1]).resolve()
PAGES = WORK / "pages"
SHOTS = WORK / "shots"

# mobile.py loaded by path: importing the package would start the add-on, which needs Anki running
_spec = importlib.util.spec_from_file_location("mobile", REPO / "painel_estudos" / "mobile.py")
mobile = importlib.util.module_from_spec(_spec)
sys.modules["mobile"] = mobile
_spec.loader.exec_module(mobile)

# AnkiDroid's speech functions, as the card sees them; the log survives the flip (sessionStorage).
STUB = """<script>
function simLog() {
  var l = JSON.parse(sessionStorage.getItem("__simlog") || "[]");
  l.push(Array.prototype.slice.call(arguments));
  sessionStorage.setItem("__simlog", JSON.stringify(l));
}
class AnkiDroidJS {
  constructor(o) { simLog("init", o && o.version); }
  ok(v) { return Promise.resolve({ success: true, value: v }); }
  ankiTtsSetLanguage(l) { simLog("ttsLang", l); return this.ok(2); }
  ankiTtsSetSpeechRate(r) { simLog("rate", Number(r)); return this.ok(0); }
  ankiTtsSpeak(t, q) { simLog("say", t, q); window.__speakUntil = Date.now() + 300; return this.ok(0); }
  ankiTtsIsSpeaking() { return this.ok(Date.now() < (window.__speakUntil || 0)); }
  ankiTtsStop() { window.__speakUntil = 0; return this.ok(true); }
  ankiSttSetLanguage(l) { simLog("sttLang", l); return this.ok(true); }
  ankiSttStart() { simLog("listen"); window.__listens = (window.__listens || 0) + 1; return this.ok(true); }
  ankiSttStop() { return this.ok(true); }
  ankiShowAnswer() { showAnswer(); return this.ok(true); }
}
</script>"""

PAGE = """<!doctype html>
<html class="mobile android linux js">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body {{ margin: 0; padding: 12px 16px 24px; font-family: Roboto, Arial, sans-serif; }}
body.night_mode {{ background: #121212; color: #e0e0e0; }}</style>
{stub}
<script>
function showAnswer() {{ location.href = {answer}; }}
function buttonAnswerEase1() {{ window.__done(1); }}
function buttonAnswerEase2() {{ window.__done(2); }}
function buttonAnswerEase3() {{ window.__done(3); }}
function buttonAnswerEase4() {{ window.__done(4); }}
{extra}
</script>
</head>
<body class="{body}"><div id="content" dir="auto">
{content}
</div></body></html>
"""
NEW_SCREEN = "window.ankidroid = { waitForZoomReset: function () {} };"


def make_profile() -> Path:
    base = WORK / "base"
    if base.exists():
        subprocess.run(["rm", "-rf", str(base)], check=True)
    subprocess.run([sys.executable, str(REPO / "dev" / "make_test_profile.py"), str(base)], check=True, capture_output=True)
    return base / "Teste" / "collection.anki2"


def enable_phone(col: Collection) -> list[str]:
    script, style = mobile.assets(REPO / "painel_estudos" / "celular")
    names = []
    for mid, _n in col.db.all(mobile.COUNT_SQL):
        nt = col.models.get(mid)
        if not mobile.eligible(nt["tmpls"]):
            continue
        for tmpl in nt["tmpls"]:
            tmpl["qfmt"] = mobile.apply(tmpl["qfmt"], "q", script, style)
            tmpl["afmt"] = mobile.apply(tmpl["afmt"], "a", script, style)
        col.models.update_dict(nt)
        names.append(nt["name"])
    return names


def card_starting(col: Collection, start: str):
    nid = next(nid for nid, flds in col.db.all("select id, flds from notes") if flds.startswith(start) or flds.split("\x1f")[0].find(start) >= 0)
    return col.get_note(nid).cards()[0]


def write_pages(name: str, card, body: str = "card", extra: str = "", desktop: bool = False) -> tuple[str, str]:
    q, a = card.question(), card.answer()
    qname, aname = f"{name}_q.html", f"{name}_a.html"
    for fname, content, target in ((qname, q, aname), (aname, a, aname)):
        page = PAGE.format(answer=json.dumps(target), extra=extra, body=html.escape(body), content=content, stub="" if desktop else STUB)
        if desktop:
            page = page.replace('<html class="mobile android linux js">', "<html>")
        (PAGES / fname).write_text(page, encoding="utf-8")
    return qname, aname


def serve() -> int:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(PAGES))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


def main() -> None:
    PAGES.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    col = Collection(str(make_profile()))
    cloze = next(m for m in col.models.all() if m["type"] == 1 and mobile.eligible(m["tmpls"]))  # Omissão de Palavras
    note = col.new_note(cloze)
    note.fields[0] = "Comete furto quem {{c1::subtrai::verbo}} coisa alheia móvel, para si ou para outrem.<br>Pena: {{c2::reclusão, de um a quatro anos, e multa}}."
    col.add_note(note, col.decks.id("Teste::Omissão"))
    print("phone block in:", enable_phone(col))
    cards = {
        "ce_errado": card_starting(col, "[Art. 155, §1º]"),
        "ce_certo": card_starting(col, "[Art. 155, caput]"),
        "mc": card_starting(col, "<b>Direito Administrativo — Licitações</b>"),
        "basico": card_starting(col, "Qual é o prazo prescricional geral"),
        "omissao": note.cards()[0],
    }
    pages = {
        "ce_errado": write_pages("ce_errado", cards["ce_errado"]),
        "ce_certo": write_pages("ce_certo", cards["ce_certo"]),
        "mc": write_pages("mc", cards["mc"]),
        "basico": write_pages("basico", cards["basico"]),
        "omissao": write_pages("omissao", cards["omissao"]),
        "noturno": write_pages("noturno", cards["ce_errado"], body="card night_mode"),
        "tela_nova": write_pages("tela_nova", cards["ce_certo"], extra=NEW_SCREEN),
        "computador": write_pages("computador", cards["ce_errado"], desktop=True),
    }
    col.close()
    port = serve()
    url = lambda name: f"http://127.0.0.1:{port}/{name}"  # noqa: E731
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        eases: list[int] = []
        errors: list[str] = []
        page.expose_function("__done", lambda n: eases.append(n))
        page.on("pageerror", lambda e: errors.append(str(e)))

        def state() -> dict:
            return page.evaluate(
                """() => ({
                  options: [...document.querySelectorAll('.pe-opt')].map(b => b.dataset.v + (b.classList.contains('pe-chosen') ? '*' : '') + (b.classList.contains('pe-wrongpick') ? '!' : '') + (b.classList.contains('pe-correct') ? '+' : '')),
                  ceLineLeft: /\\(\\s*\\)\\s*Certo/.test(document.body.innerText),
                  verdict: (document.querySelector('.pe-verdict') || {}).innerText || null,
                  trap: (document.querySelector('.pe-trap') || {}).textContent || null,
                  fix: (document.querySelector('.pe-fix') || {}).textContent || null,
                  grade: [...document.querySelectorAll('.pe-g')].map(b => b.innerText.replace(/\\s+/g, ' ')),
                  hint: (document.querySelector('.pe-hint') || {}).innerText || null,
                  voice: (document.querySelector('.pe-voz') || {getAttribute: () => null}).getAttribute('data-state'),
                  voiceMsg: (document.querySelector('.pe-voz-msg') || {}).textContent || null,
                })"""
            )

        def sim_log(clear: bool = False) -> list:
            log = page.evaluate("JSON.parse(sessionStorage.getItem('__simlog') || '[]')")
            if clear:
                page.evaluate("sessionStorage.removeItem('__simlog')")
            return log

        def reply(words=None, error=None) -> None:
            """Waits until the card asks AnkiDroid to listen, then answers as AnkiDroid does."""
            page.wait_for_function("window.__listens >= 1", timeout=8000)
            value = json.dumps(words, ensure_ascii=False) if words is not None else error
            payload = json.dumps({"success": words is not None, "value": value}, ensure_ascii=False)
            page.evaluate("p => { window.__listens = 0; window.ankiSttResult(p); }", payload)

        def said(log: list) -> list:
            return [entry[1] for entry in log if entry[0] == "say"]

        def run(name: str, choice: str | None, ease_click: str | None) -> None:
            qname, aname = pages[name]
            eases.clear()
            page.goto(url(qname))
            page.wait_for_load_state("load")
            page.screenshot(path=str(SHOTS / f"{name}_1_frente.png"))
            front = state()
            if choice:
                page.tap(f'.pe-opt[data-v="{choice}"]')
                page.wait_for_url(url(aname), timeout=5000)
            else:
                page.goto(url(aname))
            page.wait_for_load_state("load")
            page.screenshot(path=str(SHOTS / f"{name}_2_verso.png"), full_page=True)
            back = state()
            if ease_click:
                page.tap(f'.pe-g[data-ease="{ease_click}"]')
                page.wait_for_timeout(200)
            results[name] = {"front": front, "back": back, "eases": list(eases)}

        run("ce_errado", "CERTO", "1")
        run("ce_certo", "CERTO", "3")
        run("mc", "B", "1")
        run("basico", None, None)
        run("noturno", "CERTO", None)
        run("tela_nova", "CERTO", None)
        # turned without choosing: the gabarito is marked, nothing else
        page.goto(url(pages["ce_certo"][1]))
        page.wait_for_load_state("load")
        page.screenshot(path=str(SHOTS / "sem_escolha_2_verso.png"), full_page=True)
        results["sem_escolha"] = {"back": state()}
        # desktop Anki (a page without AnkiDroid's marks): nothing changes
        page.goto(url(pages["computador"][0]))
        page.wait_for_load_state("load")
        results["computador"] = {"front": state()}

        # ---- Modo voz
        def voice_run(name: str, script) -> None:
            eases.clear()
            sim_log(clear=True)
            out = {"steps": []}
            script(out)
            out["log"] = sim_log()
            out["said"] = said(out["log"])
            out["eases"] = list(eases)
            results[name] = out

        def ce_errado(out):  # turned on with the button; "certo" is wrong here; then "continuar"
            page.goto(url(pages["ce_errado"][0]))
            page.wait_for_load_state("load")
            out["steps"].append(state())
            page.tap(".pe-voz-btn")
            page.wait_for_function("window.__listens >= 1", timeout=8000)
            page.screenshot(path=str(SHOTS / "voz_1_frente_ouvindo.png"))
            out["steps"].append(state())
            reply(["serto", "certo"])
            page.wait_for_url(url(pages["ce_errado"][1]), timeout=5000)
            page.wait_for_function("window.__listens >= 1", timeout=8000)
            page.screenshot(path=str(SHOTS / "voz_2_verso_ouvindo.png"), full_page=True)
            out["steps"].append(state())
            reply(["continuar"])
            page.wait_for_timeout(300)

        def ce_certo(out):  # still on from the card before; "repete", then "certo", then "fácil"
            page.goto(url(pages["ce_certo"][0]))
            reply(["repete"])
            reply(["certo"])
            page.wait_for_url(url(pages["ce_certo"][1]), timeout=5000)
            reply(["Fácil"])
            page.wait_for_timeout(300)

        def mc(out):  # a letter the card doesn't have, "a segunda", then "explica", then "próximo"
            page.goto(url(pages["mc"][0]))
            reply(["letra F"])
            reply(["a segunda", "à segunda"])
            page.wait_for_url(url(pages["mc"][1]), timeout=5000)
            reply(["explica"])
            reply(["próximo"])
            page.wait_for_timeout(300)

        def basico(out):  # a card without options: "mostrar", then "bom"
            page.goto(url(pages["basico"][0]))
            reply(["mostrar"])
            page.wait_for_url(url(pages["basico"][1]), timeout=5000)
            out["steps"].append(state())
            reply(["bom"])
            page.wait_for_timeout(300)

        def omissao(out):  # cloze: the blank said as "lacuna"; the back has no line between the sides
            page.goto(url(pages["omissao"][0]))
            reply(["mostrar"])
            page.wait_for_url(url(pages["omissao"][1]), timeout=5000)
            out["steps"].append(state())
            reply(["difícil"])
            page.wait_for_timeout(300)

        paused = "document.querySelector('.pe-voz-msg').textContent.indexOf('Toque em Continuar') >= 0"

        def nao_entendi(out):  # three answers that mean nothing here pause it (silence in between doesn't count)
            page.goto(url(pages["ce_certo"][0]))
            reply(["banana"])
            reply(error="No match found")
            reply(["abacaxi"])
            reply(["laranja", "a laranja"])
            page.wait_for_function(paused, timeout=5000)
            page.screenshot(path=str(SHOTS / "voz_3_pausado.png"))
            out["steps"].append(state())
            page.tap(".pe-voz-btn")  # Continuar
            reply(["errado"])
            page.wait_for_url(url(pages["ce_certo"][1]), timeout=5000)
            out["steps"].append(state())

        def silencio(out):  # silence: it keeps listening ten times, then pauses; no network: three tries
            page.goto(url(pages["ce_certo"][0]))
            for _ in range(10):
                reply(error="Speech timeout")
            page.wait_for_function(paused, timeout=5000)
            out["steps"].append(state())
            page.tap(".pe-voz-btn")
            for _ in range(3):
                reply(error="Network error")
            page.wait_for_function(paused, timeout=8000)
            out["steps"].append(state())
            page.tap(".pe-voz-btn")
            reply(["certo"])
            page.wait_for_url(url(pages["ce_certo"][1]), timeout=5000)

        def ritmo_parar(out):  # faster, then "parar": off for the next cards
            page.goto(url(pages["ce_certo"][0]))
            reply(["mais rápido"])
            reply(["parar"])
            page.wait_for_timeout(300)
            out["steps"].append(state())
            out["rate"] = page.evaluate("sessionStorage.getItem('painelEstudosVozRitmo')")
            out["flag"] = page.evaluate("sessionStorage.getItem('painelEstudosVoz')")
            page.goto(url(pages["mc"][0]))
            page.wait_for_timeout(600)
            out["steps"].append(state())

        def sem_permissao(out):  # AnkiDroid without the microphone permission
            page.evaluate("sessionStorage.setItem('painelEstudosVoz', '1')")
            page.goto(url(pages["ce_errado"][0]))
            reply(error="Record audio permission not granted.")
            page.wait_for_timeout(300)
            page.screenshot(path=str(SHOTS / "voz_4_sem_permissao.png"))
            out["steps"].append(state())

        def tela_nova(out):  # the new study screen can't take the grade: no Modo voz there
            page.evaluate("sessionStorage.setItem('painelEstudosVoz', '1')")
            page.goto(url(pages["tela_nova"][0]))
            page.wait_for_timeout(600)
            out["steps"].append(state())
            page.evaluate("sessionStorage.removeItem('painelEstudosVoz')")

        voice_run("voz_ce_errado", ce_errado)
        voice_run("voz_ce_certo", ce_certo)
        voice_run("voz_mc", mc)
        voice_run("voz_basico", basico)
        voice_run("voz_omissao", omissao)
        voice_run("voz_nao_entendi", nao_entendi)
        voice_run("voz_silencio", silencio)
        voice_run("voz_ritmo_parar", ritmo_parar)
        voice_run("voz_sem_permissao", sem_permissao)
        voice_run("voz_tela_nova", tela_nova)
        browser.close()
    results["errors"] = errors
    (WORK / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
