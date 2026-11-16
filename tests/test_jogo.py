"""The study game's rules: XP, levels, floors and conquistas."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1] / "painel_estudos"
spec = importlib.util.spec_from_file_location("jogo", ROOT / "jogo.py")
jogo = importlib.util.module_from_spec(spec)
sys.modules["jogo"] = jogo
spec.loader.exec_module(jogo)


def test_every_card_counts_and_right_ones_count_more():
    assert jogo.xp_total(right=3, wrong=2, bonus=7) == 30 + 4 + 7
    assert jogo.xp_total(right=0, wrong=0, bonus=-5) == 0


def test_levels_get_longer_as_they_go():
    assert jogo.level_of(0) == {"level": 1, "into": 0, "need": 500, "xp": 0}
    assert jogo.level_of(499)["level"] == 1
    assert jogo.level_of(500) == {"level": 2, "into": 0, "need": 850, "xp": 500}
    assert jogo.level_of(500 + 850 + 30)["level"] == 3
    # the roof (level 25) takes about 108,600 XP: some 11,000 right answers, months of study
    assert jogo.level_of(108_599)["level"] == 24 and jogo.level_of(108_600)["level"] == 25


def test_combos_pay_a_little_extra():
    assert [jogo.combo_bonus(n) for n in (1, 4, 5, 9, 10, 40)] == [0, 0, 2, 2, 5, 5]


def test_floors_open_every_two_levels_and_fill_by_learned_cards():
    assert [jogo.unlock_level(i) for i in range(12)] == [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23]
    assert jogo.ROOF_LEVEL == 25
    assert jogo.stage(0, 0) == 0
    assert [jogo.stage(n, 100) for n in (0, 19, 20, 45, 79, 80, 100)] == [1, 1, 2, 3, 4, 5, 5]


def test_conquistas_come_once_and_in_order():
    ctx = {"best_day": 120, "best_combo": 12, "level": 11, "answers": 1500, "best_floor": 0.55}
    found = jogo.new_badges(ctx, {})
    assert found == ["cem-no-dia", "combo-10", "mil", "nivel-10", "andar-mobiliado"]
    assert jogo.new_badges(ctx, {b: 1 for b in found}) == []
    names = {b["id"]: b for b in jogo.badge_list({"mil": 123})}
    assert names["mil"]["at"] == 123 and names["telhado"]["at"] is None


def test_saved_data_is_cleaned():
    j = jogo.clean({"bonus": "40", "badges": {"mil": 5, "inventada": 3}, "records": {"combo": -2, "session_acc": 3}})
    assert j["bonus"] == 40 and j["badges"] == {"mil": 5}
    assert j["records"] == {"combo": 0, "session_acc": 1.0, "day_told": 0}
    assert jogo.clean(None)["seeded"] is False
