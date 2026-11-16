"""The study game: XP and levels, the building, records and conquistas.

The building has one floor per matéria of the cronograma, in its order. Levels open the floors
(the first at level 1, then one every two levels, the roof at 25). How much of a matéria's cards
is learned (out of learning: review cards) decides how furnished its floor is.

XP comes from the whole review history (10 for a right answer, 2 for a wrong one: every card
counts, nothing is taken away), so reviews made on the phone or in Anki's own screens count
too, plus a bonus the panel saves when it sees combos and the matéria do dia. Pure rules: api.py
feeds them numbers from the collection.
"""

from __future__ import annotations

import time
from typing import Any

XP_RIGHT = 10
XP_WRONG = 2
DAILY_BONUS = 3  # right answer in the matéria do dia
COMBO_STEPS = (5, 10, 25, 50, 100)  # combos worth a moment
ROOF_LEVEL = 25
COMPLETE = 0.9  # share of learned cards that puts a plaque on the floor


def combo_bonus(combo: int) -> int:
    """Extra XP for a right answer that makes the combo this long."""
    if combo >= 10:
        return 5
    if combo >= 5:
        return 2
    return 0


def xp_total(right: int, wrong: int, bonus: int) -> int:
    return XP_RIGHT * max(0, right) + XP_WRONG * max(0, wrong) + max(0, bonus)


def need(level: int) -> int:
    """XP from this level to the next: about a session for the first, a week near the roof."""
    return 500 + 350 * (max(1, level) - 1)


def level_of(xp: int) -> dict[str, int]:
    level, rest = 1, max(0, int(xp))
    while rest >= need(level):
        rest -= need(level)
        level += 1
    return {"level": level, "into": rest, "need": need(level), "xp": int(xp)}


def unlock_level(i: int) -> int:
    """The level that opens floor i (0 = the first matéria of the cronograma)."""
    return 1 + 2 * i


def stage(learned: int, total: int) -> int:
    """0: no cards; 1 to 5 as the share of learned cards grows (every 20%)."""
    if total <= 0:
        return 0
    return 1 + min(4, int(5 * learned / total))


def ordinal(i: int) -> str:
    return f"{i + 1}º andar"


# ---- conquistas: (id, name, what it takes, test on the context)
BADGES: list[tuple[str, str, str, Any]] = [
    ("primeira-sessao", "Primeira sessão", "Terminar uma sessão no painel.", lambda c: c.get("sessions", 0) >= 1),
    ("cem-no-dia", "Cem no dia", "100 cartões respondidos num dia.", lambda c: c.get("best_day", 0) >= 100),
    ("maratona", "Maratona", "300 cartões respondidos num dia.", lambda c: c.get("best_day", 0) >= 300),
    ("combo-10", "Embalado", "10 acertos seguidos.", lambda c: c.get("best_combo", 0) >= 10),
    ("combo-25", "Imparável", "25 acertos seguidos.", lambda c: c.get("best_combo", 0) >= 25),
    ("combo-50", "Gabaritando", "50 acertos seguidos.", lambda c: c.get("best_combo", 0) >= 50),
    ("sessao-limpa", "Sessão limpa", "Uma sessão de 20 cartões ou mais sem nenhum erro.", lambda c: c.get("perfect", False)),
    ("semana-firme", "Uma semana firme", "7 dias seguidos batendo a meta.", lambda c: c.get("streak", 0) >= 7),
    ("mes-firme", "Um mês firme", "30 dias seguidos batendo a meta.", lambda c: c.get("streak", 0) >= 30),
    ("semana-cumprida", "Semana cumprida", "A matéria do dia estudada nos 6 dias de uma semana do cronograma.", lambda c: c.get("week_done", False)),
    ("olho-de-banca", "Olho de banca", "25 itens ERRADO com troca da lei acertados no painel.", lambda c: c.get("traps", 0) >= 25),
    ("mil", "Mil respostas", "1.000 cartões respondidos no total.", lambda c: c.get("answers", 0) >= 1000),
    ("dez-mil", "Dez mil respostas", "10.000 cartões respondidos no total.", lambda c: c.get("answers", 0) >= 10000),
    ("nivel-10", "Nível 10", "Chegar ao nível 10.", lambda c: c.get("level", 1) >= 10),
    ("telhado", "No telhado", f"Chegar ao nível {ROOF_LEVEL}: o prédio inteiro aberto, com o telhado.", lambda c: c.get("level", 1) >= ROOF_LEVEL),
    ("nivel-50", "Nível 50", "Chegar ao nível 50.", lambda c: c.get("level", 1) >= 50),
    ("andar-mobiliado", "Andar mobiliado", "Uma matéria com metade dos cartões aprendidos.", lambda c: c.get("best_floor", 0.0) >= 0.5),
    ("andar-completo", "Andar completo", f"Uma matéria com {round(COMPLETE * 100)}% dos cartões aprendidos.", lambda c: c.get("best_floor", 0.0) >= COMPLETE),
]
BADGE_NAMES = {b[0]: b[1] for b in BADGES}
BADGE_DESCS = {b[0]: b[2] for b in BADGES}


def new_badges(ctx: dict[str, Any], have: dict[str, Any]) -> list[str]:
    """Conquistas the context earns that are not in have yet, in list order."""
    return [bid for bid, _name, _desc, test in BADGES if bid not in have and test(ctx)]


def badge_list(have: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"id": bid, "name": name, "desc": desc, "at": have.get(bid)} for bid, name, desc, _t in BADGES]


# ---- the game's own saved data (inside the panel's data, so it syncs)
def clean(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}

    def num(v: Any, kind=int) -> Any:
        try:
            return max(0, kind(v))
        except (TypeError, ValueError):
            return kind(0)

    badges = raw.get("badges") if isinstance(raw.get("badges"), dict) else {}
    records = raw.get("records") if isinstance(raw.get("records"), dict) else {}
    return {
        "bonus": num(raw.get("bonus")),
        "traps": num(raw.get("traps")),
        "sessions": num(raw.get("sessions")),
        "badges": {k: num(v) for k, v in badges.items() if k in BADGE_NAMES},
        "records": {
            "combo": num(records.get("combo")),
            "session_acc": min(1.0, num(records.get("session_acc"), float)),
            "day_told": num(records.get("day_told")),
        },
        "seeded": bool(raw.get("seeded")),
    }


def now_s() -> int:
    return int(time.time())
