"""Edital import and the Roleta-style draw, using the block formats of the exportar-roleta skill."""

import importlib.util
import random
import sys
from pathlib import Path

import pytest

# Loaded by path: importing the package would start the add-on, which needs a running Anki.
_spec = importlib.util.spec_from_file_location("edital", Path(__file__).parents[1] / "painel_estudos" / "edital.py")
ed = importlib.util.module_from_spec(_spec)
sys.modules["edital"] = ed
_spec.loader.exec_module(ed)

MIXED = """Bloco pronto: 7 tópicos.
```json
{
  "Legislação Complementar": {
    "Lei de Licitações (14.133/21)": ["Princípios", "Modalidades"],
    "Lei de Improbidade (8.429/92)": ["Sujeitos", "Sanções"]
  },
  "Português": ["Concordância verbal", "Regência", "Crase"]
}
```"""

ARROW = '{"Português > Fonética": ["Vogais"], "Português > Morfologia": ["Substantivo", "Verbo"]}'


def loaded(text: str = MIXED) -> dict:
    data = ed.empty()
    ed.merge(data, ed.parse_block(text))
    return data


def test_parse_mixed_block_with_fence_and_prose():
    entries = ed.parse_block(MIXED)
    assert ("Português", None, ["Concordância verbal", "Regência", "Crase"]) in entries
    assert ("Legislação Complementar", "Lei de Licitações (14.133/21)", ["Princípios", "Modalidades"]) in entries


def test_parse_arrow_keys_group_into_one_materia():
    data = loaded(ARROW)
    assert [m["name"] for m in data["materias"]] == ["Português"]
    assert [g["name"] for g in data["materias"][0]["groups"]] == ["Fonética", "Morfologia"]


def test_merge_twice_adds_nothing_and_keeps_status():
    data = loaded()
    tid = data["materias"][1]["groups"][0]["topics"][0]["id"]
    ed.mark_done(data, tid, now=1)
    assert ed.merge(data, ed.parse_block(MIXED)) == 0
    assert ed.find(data, tid)[2]["done"] == 1


def test_draw_never_repeats_inside_a_cycle():
    data = loaded()
    rng = random.Random(7)
    seen = []
    while (topic := ed.draw(data, rng=rng)) is not None:
        seen.append(topic["id"])
        ed.mark_done(data, topic["id"], now=1)
    assert len(seen) == len(set(seen)) == 7
    assert ed.counts(data) == {"total": 7, "done": 7, "left": 0}
    ed.new_cycle(data)
    assert data["cycle"] == 2
    assert ed.counts(data) == {"total": 7, "done": 0, "left": 7}


def test_skip_returns_topic_to_pool_and_next_draw_is_different():
    data = loaded()
    first = ed.draw(data, rng=random.Random(1))
    ed.skip(data, first["id"])
    assert ed.counts(data)["left"] == 7
    second = ed.draw(data, exclude=first["id"], rng=random.Random(1))
    assert second["id"] != first["id"]


def test_scope_limits_draw_to_one_materia_or_group():
    data = loaded()
    for _ in range(3):
        topic = ed.draw(data, {"materia": "portugues"}, rng=random.Random(3))
        assert ed.find(data, topic["id"])[0]["name"] == "Português"
    assert ed.draw(data, {"materia": "Português"}) is None
    group_scope = {"materia": "Legislação Complementar", "group": "Lei de Improbidade (8.429/92)"}
    assert ed.counts(data, group_scope)["left"] == 2


def test_unmark_done_returns_topic():
    data = loaded()
    tid = data["materias"][1]["groups"][0]["topics"][2]["id"]
    ed.mark_done(data, tid, now=5)
    ed.unmark_done(data, tid)
    assert ed.counts(data)["done"] == 0 and ed.counts(data)["left"] == 7


def test_auto_map_ignores_accents_and_deck_paths():
    data = loaded()
    ed.auto_map(data, [("Concurso::Portugues", 11), ("Legislacao complementar", 12)])
    assert [m["deck"] for m in data["materias"]] == [12, 11]
    data["materias"][0]["deck"] = None
    data["materias"][0]["deck_manual"] = True
    ed.auto_map(data, [("Legislacao complementar", 12)])
    assert data["materias"][0]["deck"] is None


@pytest.mark.parametrize("bad", ["sem json aqui", '{"Português": "Crase"}', "[1, 2]", '{"a": [1,'])
def test_bad_blocks_explain_the_problem(bad):
    with pytest.raises(ValueError) as err:
        ed.parse_block(bad)
    assert str(err.value)
