"""What the page can ask for. Each public method answers one call from the page."""

from __future__ import annotations

import time
from typing import Any

from anki.cards import Card
from anki.collection import SearchNode
from anki.scheduler.v3 import CardAnswer
from aqt import dialogs, mw
from aqt.sound import av_player
from aqt.theme import theme_manager

from . import cards as cardfmt
from . import edital as ed
from . import stats, store

VERSION = "0.1.0"
RATINGS = {1: CardAnswer.AGAIN, 2: CardAnswer.HARD, 3: CardAnswer.GOOD, 4: CardAnswer.EASY}
_BIDI = dict.fromkeys(map(ord, "⁨⁩"), None)
WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


class UserError(Exception):
    """A problem the page shows to the person as is."""


class Api:
    def __init__(self, shell: Any) -> None:
        self.shell = shell
        self.session: dict[str, Any] | None = None
        self.card: Card | None = None
        self.states: Any = None
        self.parsed: cardfmt.ParsedCard | None = None
        self.phase = ""  # "question", "answer" (normal cards) or "result" (after choosing)
        self.result: dict[str, Any] | None = None
        self.queue_counts = (0, 0, 0)

    @property
    def col(self):
        return mw.col

    # ------------------------------------------------------------------ general
    def boot(self) -> dict:
        return {"base": mw.serverURL(), "night": theme_manager.night_mode, "version": VERSION, "profile": mw.pm.name}

    def _data(self) -> dict:
        return store.load(self.col)

    def _save(self, data: dict) -> None:
        store.save(self.col, data)

    def _matters(self, data: dict) -> list[tuple[str, int]]:
        return stats.matter_decks(self.col, data.get("root"))

    def _mapped_edital(self, data: dict) -> dict:
        edital = data["edital"]
        before = [(m.get("deck"), m.get("deck_manual")) for m in edital["materias"]]
        ed.auto_map(edital, [(self.col.decks.name(did), did) for _n, did in self._matters(data)])
        if before != [(m.get("deck"), m.get("deck_manual")) for m in edital["materias"]]:
            self._save(data)
        return edital

    @staticmethod
    def _date_label() -> str:
        now = time.localtime()
        return f"{WEEKDAYS[now.tm_wday]}, {now.tm_mday} de {MONTHS[now.tm_mon - 1]}"

    # ------------------------------------------------------------------ hoje
    def home(self) -> dict:
        data = self._data()
        goal = data["goal"]
        progress = stats.goal(self.col, goal["unit"], float(goal["value"]))
        plan = stats.plan(self.col, data.get("root"))
        due = sum(row["due"] for row in plan)
        edital = self._mapped_edital(data)
        by_deck = {m.get("deck"): m["name"] for m in edital["materias"] if m.get("deck")}
        for row in plan:
            name = by_deck.get(row["did"])
            row["topics"] = ed.counts(edital, {"materia": name}) if name else None
        return {
            "date": self._date_label(),
            "goal": progress,
            "plan": plan,
            "due": due,
            "eta_min": round(due * progress["avg_secs"] / 60),
            "draw": self._draw_state(data),
        }

    # ------------------------------------------------------------------ estudo
    def start(self, did: int | None = None) -> dict:
        data = self._data()
        if did:
            decks = [int(did)]
        else:
            decks = [row["did"] for row in stats.plan(self.col, data.get("root")) if row["due"] > 0]
        self.session = {
            "decks": decks,
            "i": 0,
            "single": bool(did),
            "answered": 0,
            "right": 0,
            "started": time.time(),
            "actions": [],
        }
        return self._next()

    def stop(self) -> dict:
        av_player.stop_and_clear_queue()
        self.session = None
        self.card = None
        return {"ok": True}

    def _prep(self, rendered: str) -> str:
        return self.col.media.escape_media_filenames(rendered)

    def _load_card(self, queued_card: Any) -> None:
        self.card = Card(self.col, backend_card=queued_card.card)
        self.card.start_timer()
        self.states = queued_card.states
        self.parsed = cardfmt.parse(self._prep(self.card.question()), self._prep(self.card.answer()))
        self.phase = "question"
        self.result = None

    def _next(self, prefer_card: int | None = None) -> dict:
        av_player.stop_and_clear_queue()
        session = self.session
        if not session:
            return {"view": "home"}
        while session["i"] < len(session["decks"]):
            self.col.decks.select(session["decks"][session["i"]])
            queued = self.col.sched.get_queued_cards(fetch_limit=50 if prefer_card else 1)
            if queued.cards:
                chosen = queued.cards[0]
                if prefer_card:
                    chosen = next((qc for qc in queued.cards if qc.card.id == prefer_card), chosen)
                self.queue_counts = (queued.new_count, queued.learning_count, queued.review_count)
                self._load_card(chosen)
                self._autoplay("q")
                return self._card_payload()
            session["i"] += 1
        return self._finish()

    def _deck_label(self) -> str:
        assert self.card
        name = self.col.decks.name(self.card.current_deck_id())
        session_root = self.col.decks.name(self.session["decks"][self.session["i"]]) if self.session else name
        root_leaf = stats.leaf(session_root)
        return root_leaf if name == session_root else f"{root_leaf} › {stats.leaf(name)}"

    def _session_info(self) -> dict:
        s = self.session or {}
        goal = self._data()["goal"]
        cards, minutes = stats.today(self.col)
        done = cards if goal["unit"] == "cards" else round(minutes)
        return {
            "answered": s.get("answered", 0),
            "right": s.get("right", 0),
            "goal_done": done,
            "goal_value": goal["value"],
            "goal_unit": goal["unit"],
        }

    def _labels(self) -> list[str]:
        return [label.translate(_BIDI) for label in self.col.sched.describe_next_states(self.states)]

    def _card_payload(self) -> dict:
        assert self.card and self.parsed
        new, learn, review = self.queue_counts
        return {
            "view": "card",
            "id": self.card.id,
            "deck": self._deck_label(),
            "mode": self.parsed.mode,
            "css": self.parsed.css,
            "front": self.parsed.front,
            "options": [{"letter": letter, "html": html} for letter, html in self.parsed.options],
            "audio": bool(self.card.question_av_tags() or self.card.answer_av_tags()),
            "counts": {"new": new, "learn": learn, "review": review},
            "session": self._session_info(),
            "can_undo": bool(self.session and self.session["actions"]),
        }

    def _autoplay(self, side: str) -> None:
        if not self.card or not self.card.autoplay():
            return
        tags = self.card.question_av_tags() if side == "q" else self.card.answer_av_tags()
        if tags:
            av_player.play_tags(tags)

    def current(self) -> dict:
        """Draws the current card again, e.g. after it was edited in the browser."""
        if not self.card or not self.session:
            return {"view": "home"}
        started = self.card.timer_started
        self.card.load()
        self.card.timer_started = started
        phase, result = self.phase, self.result
        self.parsed = cardfmt.parse(
            self._prep(self.card.question(reload=True)), self._prep(self.card.answer())
        )
        payload = self._card_payload()
        self.phase, self.result = phase, result
        if phase == "answer":
            payload["answer"] = self._answer_payload()
        elif phase == "result" and result:
            payload["result"] = self._result_payload()
        return payload

    def _answer_payload(self) -> dict:
        assert self.parsed
        return {"html": self.parsed.answer_full, "labels": self._labels()}

    def _result_payload(self) -> dict:
        assert self.parsed and self.result
        return {
            "right": self.result["right"],
            "choice": self.result["choice"],
            "correct": self.parsed.correct,
            "back": self.parsed.back,
            "labels": self._labels(),
        }

    def reveal(self) -> dict:
        if not self.card or not self.parsed:
            return self._next()
        self.phase = "answer"
        self._autoplay("a")
        return self._answer_payload()

    def choose(self, choice: str) -> dict:
        if not self.card or not self.parsed or self.parsed.mode not in ("ce", "mc"):
            raise UserError("Este cartão não tem alternativas para escolher.")
        if self.phase != "result":
            self.result = {"right": self.parsed.check(choice), "choice": choice.strip().upper()}
            self.phase = "result"
            self._autoplay("a")
        return self._result_payload()

    def answer(self, rating: int) -> dict:
        if not self.card or not self.parsed or not self.session:
            return self._next()
        rating = int(rating)
        if self.parsed.mode in ("ce", "mc"):
            if self.phase != "result" or not self.result:
                raise UserError("Escolha uma resposta antes.")
            right = bool(self.result["right"])
            rating = 1 if not right else min(4, max(2, rating))
        else:
            if self.phase != "answer":
                raise UserError("Mostre a resposta antes.")
            right = rating > 1
        answer = self.col.sched.build_answer(card=self.card, states=self.states, rating=RATINGS[rating])
        self.col.sched.answer_card(answer)
        self.session["answered"] += 1
        self.session["right"] += int(right)
        self.session["actions"].append({"kind": "answer", "right": right, "cid": self.card.id, "i": self.session["i"]})
        self.card = None
        return self._next()

    def bury(self) -> dict:
        return self._set_aside("bury")

    def suspend(self) -> dict:
        return self._set_aside("suspend")

    def _set_aside(self, kind: str) -> dict:
        if not self.card or not self.session:
            return self._next()
        if kind == "bury":
            self.col.sched.bury_cards([self.card.id])
        else:
            self.col.sched.suspend_cards([self.card.id])
        self.session["actions"].append({"kind": kind, "cid": self.card.id, "i": self.session["i"]})
        self.card = None
        return self._next()

    def undo(self) -> dict:
        session = self.session
        if not session or not session["actions"] or not self.col.undo_status().undo:
            raise UserError("Não há nada desta sessão para desfazer.")
        self.col.undo()
        action = session["actions"].pop()
        if action["kind"] == "answer":
            session["answered"] -= 1
            session["right"] -= int(action["right"])
        session["i"] = action["i"]
        return self._next(prefer_card=action["cid"])

    def replay(self) -> dict:
        if self.card:
            tags = self.card.question_av_tags() if self.phase == "question" else self.card.answer_av_tags()
            av_player.play_tags(tags or self.card.question_av_tags())
        return {"ok": True}

    def edit(self) -> dict:
        if self.card:
            dialogs.open("Browser", mw, search=(f"cid:{self.card.id}",))
        return {"ok": True}

    def _finish(self) -> dict:
        session = self.session or {}
        self.card = None
        minutes = (time.time() - session.get("started", time.time())) / 60
        name = None
        if session.get("single") and session.get("decks"):
            name = stats.leaf(self.col.decks.name(session["decks"][0]))
        return {
            "view": "done",
            "answered": session.get("answered", 0),
            "right": session.get("right", 0),
            "minutes": round(minutes),
            "deck": name,
            "results": [a["right"] for a in session.get("actions", []) if a["kind"] == "answer"],
            "session": self._session_info(),
        }

    # ------------------------------------------------------------------ matérias
    def materias(self) -> dict:
        data = self._data()
        edital = self._mapped_edital(data)
        by_deck = {m.get("deck"): m["name"] for m in edital["materias"] if m.get("deck")}
        nodes = stats.due_nodes(self.col)
        rows = []
        for name, did in self._matters(data):
            dids = stats.subtree(self.col, did)
            node = nodes.get(did)
            acc, answers = stats.accuracy(self.col, dids, 30)
            edital_name = by_deck.get(did)
            rows.append(
                {
                    "did": did,
                    "name": name,
                    "due": (node.new_count + node.learn_count + node.review_count) if node else 0,
                    "acc": acc,
                    "answers": answers,
                    "maturity": stats.maturity(self.col, dids),
                    "topics": ed.counts(edital, {"materia": edital_name}) if edital_name else None,
                }
            )
        return {"rows": rows}

    def materia(self, did: int) -> dict:
        did = int(did)
        if not self.col.decks.get(did, default=False):
            raise UserError("Esse baralho não existe mais.")
        data = self._data()
        edital = self._mapped_edital(data)
        dids = stats.subtree(self.col, did)
        nodes = stats.due_nodes(self.col)
        node = nodes.get(did)
        acc30, n30 = stats.accuracy(self.col, dids, 30)
        acc7, n7 = stats.accuracy(self.col, dids, 7)
        materia = next((m for m in edital["materias"] if m.get("deck") == did), None)
        return {
            "did": did,
            "name": stats.leaf(self.col.decks.name(did)),
            "counts": {
                "new": node.new_count if node else 0,
                "learn": node.learn_count if node else 0,
                "review": node.review_count if node else 0,
            },
            "acc30": acc30,
            "n30": n30,
            "acc7": acc7,
            "n7": n7,
            "maturity": stats.maturity(self.col, dids),
            "weak": stats.weak_tags(self.col, dids),
            "edital": self._edital_materia(edital, materia) if materia else None,
        }

    # ------------------------------------------------------------------ edital
    @staticmethod
    def _topic(edital: dict, tid: str | None) -> dict | None:
        found = ed.find(edital, tid)
        if not found:
            return None
        materia, group, topic = found
        return {
            "id": topic["id"],
            "name": topic["name"],
            "materia": materia["name"],
            "group": group["name"],
            "times": topic.get("times", 0),
            "last": topic.get("last"),
        }

    def _draw_state(self, data: dict) -> dict:
        edital = data["edital"]
        scope = data.get("scope")
        return {
            "has_edital": bool(edital["materias"]),
            "cycle": edital["cycle"],
            "current": self._topic(edital, edital.get("current")),
            "scope": scope,
            "scopes": [
                {"materia": m["name"], "groups": [g["name"] for g in m["groups"] if g["name"]]}
                for m in edital["materias"]
            ],
            "counts": ed.counts(edital, scope),
            "all": ed.counts(edital),
        }

    def _edital_materia(self, edital: dict, materia: dict) -> dict:
        cycle = edital["cycle"]
        return {
            "name": materia["name"],
            "deck": materia.get("deck"),
            "counts": ed.counts(edital, {"materia": materia["name"]}),
            "groups": [
                {
                    "name": group["name"],
                    "topics": [
                        {
                            "id": t["id"],
                            "name": t["name"],
                            "done": t["done"] == cycle,
                            "drawn": t["drawn"] == cycle,
                            "current": t["id"] == edital.get("current"),
                            "times": t.get("times", 0),
                            "last": t.get("last"),
                        }
                        for t in group["topics"]
                    ],
                }
                for group in materia["groups"]
            ],
        }

    def edital(self) -> dict:
        data = self._data()
        edital = self._mapped_edital(data)
        return {
            "draw": self._draw_state(data),
            "materias": [self._edital_materia(edital, m) for m in edital["materias"]],
            "decks": [{"id": did, "name": name} for name, did in self._matters(data)],
        }

    def edital_import(self, text: str) -> dict:
        try:
            entries = ed.parse_block(text or "")
        except ValueError as err:
            raise UserError(str(err)) from err
        data = self._data()
        added = ed.merge(data["edital"], entries)
        self._save(data)
        result = self.edital()
        result["added"] = added
        return result

    def edital_clear(self) -> dict:
        data = self._data()
        data["edital"] = ed.empty()
        data["scope"] = None
        self._save(data)
        return self.edital()

    def edital_link(self, materia: str, did: int | None) -> dict:
        data = self._data()
        for m in data["edital"]["materias"]:
            if m["name"] == materia:
                m["deck"] = int(did) if did else None
                m["deck_manual"] = True
        self._save(data)
        return self.edital()

    def topic_toggle(self, tid: str) -> dict:
        data = self._data()
        edital = data["edital"]
        found = ed.find(edital, tid)
        if not found:
            raise UserError("Esse tópico não está mais no edital.")
        if found[2]["done"] == edital["cycle"]:
            ed.unmark_done(edital, tid)
        else:
            ed.mark_done(edital, tid, int(time.time()))
        self._save(data)
        return {"ok": True}

    def draw(self, scope: dict | None = None) -> dict:
        data = self._data()
        data["scope"] = scope or None
        edital = data["edital"]
        if edital.get("current"):
            ed.skip(edital, edital["current"])
        ed.draw(edital, data["scope"])
        self._save(data)
        return self._draw_state(data)

    def set_scope(self, scope: dict | None = None) -> dict:
        data = self._data()
        data["scope"] = scope or None
        self._save(data)
        return {"ok": True}

    def topic_done(self) -> dict:
        data = self._data()
        edital = data["edital"]
        if edital.get("current"):
            ed.mark_done(edital, edital["current"], int(time.time()))
        self._save(data)
        return self._draw_state(data)

    def topic_skip(self) -> dict:
        data = self._data()
        edital = data["edital"]
        current = edital.get("current")
        if current:
            ed.skip(edital, current)
            ed.draw(edital, data.get("scope"), exclude=current)
        self._save(data)
        return self._draw_state(data)

    def new_cycle(self) -> dict:
        data = self._data()
        ed.new_cycle(data["edital"])
        self._save(data)
        return self._draw_state(data)

    # ------------------------------------------------------------------ ajustes
    def settings(self) -> dict:
        data = self._data()
        decks = self.col.decks.all_names_and_ids(skip_empty_default=True, include_filtered=False)
        return {
            "goal": data["goal"],
            "root": data.get("root"),
            "parents": [{"id": int(d.id), "name": d.name} for d in decks if self.col.decks.children(d.id)],
            "matters": [name for name, _did in self._matters(data)],
            "version": VERSION,
            "profile": mw.pm.name,
        }

    def save_settings(self, goal: dict | None = None, root: int | None = None) -> dict:
        data = self._data()
        if goal:
            unit = "minutes" if goal.get("unit") == "minutes" else "cards"
            value = max(1, min(2000, int(float(goal.get("value") or 0))))
            data["goal"] = {"unit": unit, "value": value}
        data["root"] = int(root) if root else None
        self._save(data)
        return self.settings()

    # ------------------------------------------------------------------ janelas do Anki
    def open(self, what: str, did: int | None = None) -> dict:
        if did:
            self.col.decks.select(int(did))
        if what == "add":
            mw.onAddCard()
        elif what == "browse":
            query = self.col.build_search_string(SearchNode(deck=self.col.decks.name(int(did)))) if did else ""
            dialogs.open("Browser", mw, search=(query,) if query else None)
        elif what == "stats":
            mw.onStats()
        elif what == "options":
            from aqt.deckoptions import display_options_for_deck_id

            display_options_for_deck_id(int(did) if did else self.col.decks.get_current_id())
        elif what == "import":
            mw.onImport()
        elif what == "sync":
            mw.on_sync_button_clicked()
        elif what == "prefs":
            mw.onPrefs()
        elif what == "profiles":
            mw.unloadProfileAndShowProfileManager()
        elif what == "anki":
            self.shell.show_anki_ui()
        else:
            raise UserError(f"Ação desconhecida: {what}")
        return {"ok": True}
