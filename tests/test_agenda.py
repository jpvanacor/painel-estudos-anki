"""The two-week schedule: which matéria falls on which day, and which deck each name means."""

import datetime as dt
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1] / "painel_estudos"
spec = importlib.util.spec_from_file_location("agenda", ROOT / "agenda.py")
agenda = importlib.util.module_from_spec(spec)
sys.modules["agenda"] = agenda
spec.loader.exec_module(agenda)

PLAN = agenda.clean(agenda.DEFAULT)
D = dt.date


def test_twelve_days_then_it_repeats():
    assert PLAN["start"] == "2026-11-16" and D(2026, 11, 16).weekday() == 0
    names = [PLAN["days"][agenda.slot(PLAN, D(2026, 11, 16) + dt.timedelta(days=i))] for i in range(14) if (D(2026, 11, 16) + dt.timedelta(days=i)).weekday() != 6]
    assert names == PLAN["days"]
    assert agenda.slot(PLAN, D(2026, 11, 16)) == 0  # first Monday: Constitucional
    assert PLAN["days"][0] == "Direito Constitucional"
    assert agenda.slot(PLAN, D(2026, 11, 22)) is None  # Sunday
    assert agenda.slot(PLAN, D(2026, 11, 23)) == 6  # Monday of week 2
    assert agenda.slot(PLAN, D(2026, 11, 30)) == 0  # back to week 1
    assert agenda.slot(PLAN, D(2026, 11, 9)) == 6  # the week before the start is a week 2


def test_law_and_the_rest_alternate_where_they_can():
    other = {"Língua Portuguesa", "Informática", "Redação"}
    spots = [i for i, n in enumerate(PLAN["days"]) if n in other]
    assert spots == [2, 6, 10]  # every fourth day, also across the turn of the cycle
    assert len(set(PLAN["days"])) == 12


def test_clean_moves_the_start_to_monday_and_keeps_twelve_days():
    plan = agenda.clean({"start": "2026-11-19", "days": ["  Direito   Penal ", None]})
    assert plan["start"] == "2026-11-16"
    assert plan["days"][:2] == ["Direito Penal", ""] and len(plan["days"]) == 12
    assert agenda.clean({"start": "nada"})["start"] == agenda.DEFAULT["start"]
    assert agenda.clean(None) == PLAN


def test_names_find_their_decks():
    decks = [
        ("Constitucional", 1),
        ("Direito Civil", 2),
        ("Direito Processual Civil", 3),
        ("Português", 4),
        ("Concurso::Direito Institucional do MP", 5),
        ("Legislação Especial", 6),
        ("Informática", 7),
    ]
    assert agenda.match("Direito Constitucional", decks) == 1
    assert agenda.match("Direito Civil", decks) == 2
    assert agenda.match("Direito Processual Civil", decks) == 3
    assert agenda.match("Língua Portuguesa", decks) == 4
    assert agenda.match("Direito Institucional do Ministério Público", decks) == 5
    assert agenda.match("Legislação Especial (Legislação Penal Especial, ECA)", decks) == 6
    assert agenda.match("Informatica", decks) == 7
    assert agenda.match("Redação", decks) is None
    assert agenda.match("Civil", [("Direito Civil", 2), ("Civil", 9)]) == 9  # two decks: the very same name
    assert agenda.match("Penal", [("Direito Penal", 2), ("Direito Penal (CP)", 9)]) is None  # no guess


def test_view_marks_today_and_says_what_comes_next():
    v = agenda.view(PLAN, D(2026, 11, 21), [])  # Saturday, week 1
    assert v["today"]["name"] == "Direito Processual Penal" and v["week"] == 1
    assert v["next"]["name"] == "Informática" and v["next_when"] == "segunda"
    assert [c["today"] for c in v["weeks"][0]] == [False] * 5 + [True]
    sunday = agenda.view(PLAN, D(2026, 11, 22), [])
    assert sunday["sunday"] and sunday["today"] is None and sunday["week"] == 1
    assert sunday["next"]["name"] == "Informática" and sunday["next_when"] == "amanhã"
