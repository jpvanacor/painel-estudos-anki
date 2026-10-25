"""The Roleta inside the panel: import formats, backups, cycles and editing, as in Roleta v2."""

import importlib.util
import json
import random
import sys
from pathlib import Path

import pytest

# Loaded by path: importing the package would start the add-on, which needs a running Anki.
_spec = importlib.util.spec_from_file_location("roleta", Path(__file__).parents[1] / "painel_estudos" / "roleta.py")
ro = importlib.util.module_from_spec(_spec)
sys.modules["roleta"] = ro
_spec.loader.exec_module(ro)

MIXED = """Bloco pronto: 7 tópicos.
```json
{
  "Legislação Complementar": {
    "Lei de Licitações (14.133/21)": ["Princípios", "Modalidades"],
    "Lei de Improbidade (8.429/92)": ["Sujeitos", "Sanções"],
  },
  "Português": ["Concordância verbal", "Regência", "Crase"]
}
```"""


def loaded(text: str = MIXED) -> dict:
    state = ro.empty()
    ro.import_text(state, text)
    return state


def names(state):
    return {c["name"]: {s["name"]: [t["t"] for t in s["topics"]] for s in c["subs"]} for c in state["cats"]}


# ------------------------------------------------------------------ import
def test_lenient_json_with_fence_prose_and_trailing_comma():
    state = loaded()
    assert names(state) == {
        "Legislação Complementar": {
            "Lei de Licitações (14.133/21)": ["Princípios", "Modalidades"],
            "Lei de Improbidade (8.429/92)": ["Sujeitos", "Sanções"],
        },
        "Português": {"": ["Concordância verbal", "Regência", "Crase"]},
    }


def test_separators_and_three_levels():
    state = loaded('{"Português > Fonética": ["Vogais"], "Português › Morfologia": ["Verbo"], "Direito » Civil": {"Parte geral": {"Pessoas": ["Capacidade"]}}}')
    tree = names(state)
    assert tree["Português"] == {"Fonética": ["Vogais"], "Morfologia": ["Verbo"]}
    assert tree["Direito"] == {"Civil › Parte geral › Pessoas": ["Capacidade"]}


def test_merge_ignores_repeats_with_other_accents_or_case():
    state = loaded()
    result = ro.import_text(state, '{"portugues": ["CRASE", "Pontuação"]}')
    assert result["added"] == 1 and result["dup"] == 1
    assert names(state)["Português"][""][-1] == "Pontuação"


def test_nothing_new_is_an_error_and_changes_nothing():
    state = loaded()
    before = json.dumps(state, sort_keys=True)
    with pytest.raises(ro.RoletaError, match="Nada novo"):
        ro.import_text(state, '{"Português": ["Crase"]}')
    assert json.dumps(state, sort_keys=True) == before


def test_plain_lines_go_to_the_current_selection_without_bullets():
    state = loaded()
    portugues = next(c for c in state["cats"] if c["name"] == "Português")
    ro.select(state, portugues["id"])
    result = ro.import_text(state, "1. Pontuação;\n- Ortografia\n2.3 Acentuação gráfica.\n\n")
    assert result["kind"] == "lines" and result["added"] == 3
    assert names(state)["Português"][""][-3:] == ["Pontuação", "Ortografia", "Acentuação gráfica"]


@pytest.mark.parametrize("bad", ['{"a": [1,', "[1, 2]", '"so texto"'])
def test_bad_blocks_explain_the_problem(bad):
    with pytest.raises(ro.RoletaError):
        ro.import_text(loaded(), bad)


# ------------------------------------------------------------------ backups
def test_backup_round_trip_keeps_ids_seen_and_notes():
    state = loaded()
    tid = state["cats"][1]["subs"][0]["topics"][0]["id"]
    ro.set_note(state, tid, "Ver súmula 7")
    ro.spin(state, state["cats"][1]["id"], rng=random.Random(1), now=111)
    text = ro.backup_json(state)
    data = json.loads(text)
    assert data["_roleta"] == 2 and "exportedAt" in data
    other = ro.empty()
    assert ro.inspect_import(text) == {"kind": "backup", "cats": 2, "topics": 7}
    ro.import_text(other, text)
    assert other["cats"] == state["cats"]


def test_roleta_app_v2_backup_imports_as_is():
    app_backup = {
        "_roleta": 2,
        "exportedAt": "2026-09-26T17:00:00.000Z",
        "cats": [{"id": "c1", "name": "Constitucional", "sel": "_all", "subs": [
            {"id": "s1", "name": "Título II", "topics": [
                {"id": "t1", "t": "Direitos sociais", "seen": 1790000000000, "note": "art. 6º"},
                {"id": "t2", "t": "Nacionalidade", "seen": None, "note": ""}]},
            {"id": "s2", "name": "Título III", "topics": [{"id": "t3", "t": "União", "seen": None, "note": ""}]}]}],
    }
    state = ro.empty()
    ro.import_text(state, json.dumps(app_backup))
    cat = state["cats"][0]
    assert cat["id"] == "c1" and cat["sel"] == "_all" and cat["deck"] is None
    t1 = cat["subs"][0]["topics"][0]
    assert (t1["seen"], t1["note"], t1["times"]) == (1790000000000, "art. 6º", 0)


def test_roleta_v1_backup_is_migrated():
    v1 = {"_backup": True, "subjects": {"Penal": ["Furto", "Roubo", "Dano"], "Civil": {"Contratos": ["Compra e venda", "Doação"]}},
          "seen": {"Penal": [2, 0], "Civil": {"_all": [1]}}}
    state = ro.empty()
    ro.import_text(state, json.dumps(v1))
    penal = {t["t"]: t["seen"] for t in state["cats"][0]["subs"][0]["topics"]}
    civil = {t["t"]: t["seen"] for t in state["cats"][1]["subs"][0]["topics"]}
    assert penal == {"Furto": 2, "Roubo": None, "Dano": 1}
    assert civil == {"Compra e venda": None, "Doação": 1}


def test_topics_json_reimports_to_the_same_tree():
    state = loaded()
    again = loaded(ro.topics_json(state))
    assert names(again) == names(state)


# ------------------------------------------------------------------ the draw
def test_no_repeats_until_the_cycle_ends_then_everything_returns():
    state = loaded()
    cat = state["cats"][0]  # two subcategories: the scope is all of them
    rng = random.Random(3)
    picks = [ro.spin(state, cat["id"], rng=rng) for _ in range(4)]
    assert len({p["id"] for p in picks}) == 4
    assert [p["cycle_done"] for p in picks] == [False, False, False, True]
    nxt = ro.spin(state, cat["id"], rng=rng)
    assert nxt["reset"] == 4
    assert ro.counts(cat["subs"])["seen"] == 1


def test_scope_follows_the_selected_subcategory():
    state = loaded()
    cat = state["cats"][0]
    improbidade = cat["subs"][1]
    ro.select(state, cat["id"], improbidade["id"])
    for _ in range(6):
        pick = ro.spin(state, rng=random.Random(5))
        assert ro.find_topic(state, pick["id"])[1] is improbidade
        assert pick["n"] == 2


def test_sortear_outro_excludes_the_topic_and_keeps_its_count():
    state = loaded()
    cat = state["cats"][1]
    first = ro.spin(state, cat["id"], rng=random.Random(2))
    second = ro.again(state, first["id"], rng=random.Random(2))
    assert second["id"] != first["id"]
    topic = ro.find_topic(state, first["id"])[2]
    assert topic["seen"] is None and topic["times"] == 0


def test_toggle_and_reset_scope():
    state = loaded()
    cat = state["cats"][1]
    tid = cat["subs"][0]["topics"][0]["id"]
    assert ro.toggle_seen(state, tid, now=5) is True
    assert ro.toggle_seen(state, tid) is False
    ro.spin(state, cat["id"])
    ro.spin(state, cat["id"])
    assert ro.reset_scope(state, cat["id"]) == 2
    assert ro.counts(cat["subs"])["seen"] == 0


def test_errors_for_empty_wheel():
    with pytest.raises(ro.RoletaError):
        ro.spin(ro.empty())
    state = ro.empty()
    ro.save_cat(state, None, "Nova", [{"id": None, "name": ""}])
    with pytest.raises(ro.RoletaError, match="Adicione tópicos"):
        ro.spin(state)


# ------------------------------------------------------------------ editing
def test_rename_add_remove_with_duplicate_checks():
    state = loaded()
    cat = state["cats"][1]
    sub = cat["subs"][0]
    tid = sub["topics"][0]["id"]
    with pytest.raises(ro.RoletaError, match="Já existe"):
        ro.rename_topic(state, tid, "regencia")
    assert ro.rename_topic(state, tid, "  Concordância   nominal ") == "Concordância nominal"
    with pytest.raises(ro.RoletaError, match="já existe"):
        ro.add_topic(state, cat["id"], sub["id"], "CRASE")
    topic = ro.add_topic(state, cat["id"], sub["id"], "Colocação pronominal")
    assert ro.remove_topic(state, topic["id"]) == "Colocação pronominal"


def test_organizer_renames_adds_and_deletes_subcategories():
    state = loaded()
    cat = state["cats"][0]
    licit, improb = cat["subs"]
    result = ro.save_cat(state, cat["id"], "Legislação", [{"id": licit["id"], "name": "Licitações"}, {"id": None, "name": "LINDB"}])
    assert result["removed"] == 2  # Improbidade and its two topics
    assert [s["name"] for s in cat["subs"]] == ["Licitações", "LINDB"]
    assert cat["subs"][0]["topics"][0]["t"] == "Princípios"
    lindb = cat["subs"][1]
    with pytest.raises(ro.RoletaError, match="Só uma subcategoria"):
        ro.save_cat(state, cat["id"], "Legislação", [{"id": lindb["id"], "name": ""}, {"id": licit["id"], "name": ""}])
    # a new row left blank is ignored, as in the Roleta
    ro.save_cat(state, cat["id"], "Legislação", [{"id": licit["id"], "name": "Licitações"}, {"id": lindb["id"], "name": "LINDB"}, {"id": None, "name": ""}])
    assert len(cat["subs"]) == 2
    with pytest.raises(ro.RoletaError, match="Já existe uma matéria"):
        ro.save_cat(state, cat["id"], "português", [{"id": licit["id"], "name": "Licitações"}])
    assert ro.delete_cat(state, cat["id"]) == 2
    assert state["ui"]["cat"] == state["cats"][0]["id"]


def test_deck_links_by_name_unless_set_by_hand():
    state = loaded()
    assert ro.auto_map(state, [("Concurso::Portugues", 11), ("Legislacao complementar", 12)]) is True
    assert [c["deck"] for c in state["cats"]] == [12, 11]
    ro.link_deck(state, state["cats"][0]["id"], None)
    ro.auto_map(state, [("Legislacao complementar", 12)])
    assert state["cats"][0]["deck"] is None


def test_painel_01_edital_is_converted():
    old = {
        "cycle": 2,
        "current": "a1",
        "materias": [{"name": "Penal", "deck": 7, "deck_manual": True, "groups": [{"name": None, "topics": [
            {"id": "a1", "name": "Furto", "drawn": 2, "done": 0, "times": 3, "last": None},
            {"id": "a2", "name": "Roubo", "drawn": 2, "done": 2, "times": 1, "last": 1700000000},
            {"id": "a3", "name": "Dano", "drawn": 1, "done": 1, "times": 1, "last": 1600000000}]}]}],
    }
    state = ro.from_edital(old)
    topics = {t["t"]: t for t in state["cats"][0]["subs"][0]["topics"]}
    assert topics["Roubo"]["seen"] == 1700000000000 and topics["Furto"]["seen"] and topics["Dano"]["seen"] is None
    assert topics["Furto"]["times"] == 3 and state["last"] == "a1"
    assert state["cats"][0]["deck"] == 7 and state["cats"][0]["deck_manual"] is True
