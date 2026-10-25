"""Plays the phone part (celular/celular.js) in pages shaped like AnkiDroid's card page.

Real cards from the test profile are rendered by Anki with the phone block in their note type.
Each side goes in a page like AnkiDroid's: <html class="mobile android linux js">, the card in
<div id="content"> inside <body class="card">, and showAnswer() and buttonAnswerEase1() to 4()
as global functions, the names AnkiDroid's own card.js gives them. Here showAnswer() opens the
answer page (same origin, so sessionStorage carries over, as in AnkiDroid's reviewer) and the
answer functions record the ease. Chromium (Playwright) taps through at phone size and takes
screenshots.

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

PAGE = """<!doctype html>
<html class="mobile android linux js">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body {{ margin: 0; padding: 12px 16px 24px; font-family: Roboto, Arial, sans-serif; }}
body.night_mode {{ background: #121212; color: #e0e0e0; }}</style>
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
    for mid, _n in col.db.all(mobile.NOTES_SQL):
        nt = col.models.get(mid)
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
        page = PAGE.format(answer=json.dumps(target), extra=extra, body=html.escape(body), content=content)
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
    print("phone block in:", enable_phone(col))
    cards = {
        "ce_errado": card_starting(col, "[Art. 155, §1º]"),
        "ce_certo": card_starting(col, "[Art. 155, caput]"),
        "mc": card_starting(col, "<b>Direito Administrativo — Licitações</b>"),
        "basico": card_starting(col, "Qual é o prazo prescricional geral"),
    }
    pages = {
        "ce_errado": write_pages("ce_errado", cards["ce_errado"]),
        "ce_certo": write_pages("ce_certo", cards["ce_certo"]),
        "mc": write_pages("mc", cards["mc"]),
        "basico": write_pages("basico", cards["basico"]),
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
                })"""
            )

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
        browser.close()
    results["errors"] = errors
    (WORK / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
