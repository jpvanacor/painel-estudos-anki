"""Which decks are the matérias, with a real Anki collection (skipped where Anki isn't installed)."""

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("anki")
from anki.collection import Collection  # noqa: E402

_spec = importlib.util.spec_from_file_location("stats", Path(__file__).parents[1] / "painel_estudos" / "stats.py")
stats = importlib.util.module_from_spec(_spec)
sys.modules["stats"] = stats
_spec.loader.exec_module(stats)


@pytest.fixture
def col(tmp_path):
    c = Collection(str(tmp_path / "test.anki2"))
    yield c
    c.close()


def add_card(col, deck):
    note = col.new_note(col.models.all()[0])
    note.fields[0] = deck
    col.add_note(note, col.decks.id(deck))


def names(rows):
    return [name for name, _did in rows]


def test_topic_decks_inside_matters_are_not_matters(col):
    for deck in ("Direito Penal", "Direito Civil", "Direito Penal::Parte especial::Furto"):
        add_card(col, deck)
    assert sorted(names(stats.matter_decks(col))) == ["Direito Civil", "Direito Penal"]


def test_root_lists_only_the_decks_right_under_it(col):
    for deck in ("Concurso::Penal", "Concurso::Civil", "Concurso::Penal::Parte especial::Furto"):
        add_card(col, deck)
    # a single top-level deck holding the matérias works as the root
    assert sorted(names(stats.matter_decks(col))) == ["Civil", "Penal"]
    root = col.decks.id_for_name("Concurso")
    assert sorted(names(stats.matter_decks(col, root))) == ["Civil", "Penal"]


def test_lone_matter_with_panel_made_decks_stays_a_matter(col):
    add_card(col, "Direito Penal")
    sub = col.decks.id("Direito Penal::Parte especial")
    topic = col.decks.id("Direito Penal::Parte especial::Furto")
    assert names(stats.matter_decks(col, None, [sub, topic])) == ["Direito Penal"]
    # without knowing who made them, a lone top-level deck with subdecks is read as the root
    assert names(stats.matter_decks(col)) == ["Parte especial"]
