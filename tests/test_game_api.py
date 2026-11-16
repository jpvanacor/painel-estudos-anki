"""The study game inside a real study session (the panel's calls, without Anki's window).

Skipped where Anki (aqt) isn't installed.
"""

import os
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("aqt")
from anki.collection import Collection  # noqa: E402  (first, so aqt's imports don't go in a circle)
import aqt  # noqa: E402

REPO = Path(__file__).parents[1]


@pytest.fixture
def api(tmp_path):
    base = tmp_path / "base"
    subprocess.run([sys.executable, str(REPO / "dev" / "make_test_profile.py"), str(base)], check=True, capture_output=True)
    col = Collection(str(base / "Teste" / "collection.anki2"))
    aqt.mw = SimpleNamespace(col=col, pm=SimpleNamespace(name="Teste", reduce_motion=lambda: False), serverURL=lambda: "http://x/", update_undo_actions=lambda: None)
    # the package without its __init__, which needs a running Anki
    for name in [m for m in sys.modules if m == "painel_estudos" or m.startswith("painel_estudos.")]:
        del sys.modules[name]
    pkg = types.ModuleType("painel_estudos")
    pkg.__path__ = [str(REPO / "painel_estudos")]
    sys.modules["painel_estudos"] = pkg
    from painel_estudos import api as api_mod

    api_mod.mw = aqt.mw
    a = api_mod.Api(SimpleNamespace(addon="x"))
    files = tmp_path / "user_files"

    def user_files(*parts):
        path = os.path.join(files, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    a._user_files = user_files
    a.boot()
    yield a
    col.close()


def answer(a, res, right=True):
    if res["mode"] in ("ce", "mc"):
        correct = a.parsed.correct
        if right:
            a.choose(correct)
        else:
            a.choose(("CERTO" if correct == "ERRADO" else "ERRADO") if res["mode"] == "ce" else ("A" if correct != "A" else "B"))
        return a.answer(3)
    a.reveal()
    return a.answer(3 if right else 1)


def test_a_session_earns_xp_combos_and_a_summary(api):
    res = api.start()
    game = res["game"]
    assert game["floor"]["name"] and len(game["tower"]) == 12
    xp0 = game["level"]["xp"]
    res = answer(api, res, right=True)
    ev = {e["type"]: e for e in res["game"]["events"]}
    assert ev["xp"]["n"] >= 10 and res["game"]["session"]["combo"] == 1
    res = answer(api, res, right=False)
    ev = {e["type"]: e for e in res["game"]["events"]}
    assert ev["xp"]["n"] == 2 and res["game"]["session"]["combo"] == 0
    assert res["game"]["level"]["xp"] == xp0 + res["game"]["session"]["gain"]
    # undo takes the XP and the combo back
    res = answer(api, res, right=True)
    before = api.session["game"]["xp"]
    res = api.undo()
    assert api.session["game"]["xp"] < before and api.session["game"]["combo"] == 0
    done = api.stop(summary=True)
    assert done["view"] == "done" and done["ended"]
    g = done["game"]
    assert g["gain"] == 12 and g["acc"] == 0.5
    assert "Primeira sessão" in [b["name"] for b in g["new_badges"]]
    assert "Mil respostas" in [b["name"] for b in g["found"]]  # the test profile has 1,500 answers
    saved = api.col.get_config("painelEstudos")["jogo"]
    assert saved["seeded"] and saved["sessions"] == 1 and "primeira-sessao" in saved["badges"]


def test_combo_bonus_and_level_up(api):
    res = api.start()
    from painel_estudos import jogo

    g = api.session["game"]
    lv = jogo.level_of(g["xp"])
    g["xp"] += lv["need"] - lv["into"] - 1  # one point short of the next level
    kinds = []
    for _ in range(6):
        if res.get("view") != "card":
            break
        res = answer(api, res, right=True)
        kinds += [e["type"] for e in (res.get("game") or {}).get("events", [])]
    assert "level" in kinds and "combo" in kinds  # the fifth right answer in a row is a combo moment
    assert api.session is None or api.session["game"]["j"]["bonus"] >= 2


def test_the_game_can_be_switched_off(api):
    api.set_fx(game=False)
    res = api.start()
    assert res["game"] is None
    res = answer(api, res, right=True)
    assert res.get("game") is None and "game" not in api.session
