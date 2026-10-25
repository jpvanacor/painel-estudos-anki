"""What the page can ask for. Each public method answers one call from the page."""

from __future__ import annotations

import copy
import time
from typing import Any, Callable

from anki.cards import Card
from anki.collection import SearchNode
from anki.scheduler.v3 import CardAnswer
from aqt import dialogs, mw
from aqt.qt import QApplication, QFileDialog
from aqt.sound import av_player
from aqt.theme import theme_manager

from . import cards as cardfmt
from . import roleta as ro
from . import stats, store

VERSION = "0.2.0"
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
        self.goal_flag = False
        self.ro_undo: dict | None = None  # the Roleta before its last destructive change

    @property
    def col(self):
        return mw.col

    # ------------------------------------------------------------------ general
    def boot(self) -> dict:
        data = self._data()
        return {
            "base": mw.serverURL(),
            "night": theme_manager.night_mode,
            "version": VERSION,
            "profile": mw.pm.name,
            "fx": data["fx"],
            "reduce_motion": bool(getattr(mw.pm, "reduce_motion", lambda: False)()),
        }

    def _data(self) -> dict:
        data = store.load(self.col)
        if data.pop("_converted", False):
            self._save(data)  # the 0.1 edital becomes the Roleta once
        return data

    def _save(self, data: dict) -> None:
        store.save(self.col, data)

    def _matters(self, data: dict) -> list[tuple[str, int]]:
        return stats.matter_decks(self.col, data.get("root"))

    def _mapped_roleta(self, data: dict) -> dict:
        state = data["roleta"]
        if ro.auto_map(state, [(self.col.decks.name(did), did) for _n, did in self._matters(data)]):
            self._save(data)
        return state

    @staticmethod
    def _date_label() -> str:
        now = time.localtime()
        return f"{WEEKDAYS[now.tm_wday]}, {now.tm_mday} de {MONTHS[now.tm_mon - 1]}"

    @staticmethod
    def _cat_counts(state: dict) -> dict[int, dict]:
        return {c["deck"]: {**ro.counts(c["subs"]), "cat": c["id"], "name": c["name"]} for c in state["cats"] if c.get("deck")}

    # ------------------------------------------------------------------ hoje
    def home(self) -> dict:
        data = self._data()
        goal = data["goal"]
        progress = stats.goal(self.col, goal["unit"], float(goal["value"]))
        plan = stats.plan(self.col, data.get("root"))
        due = sum(row["due"] for row in plan)
        state = self._mapped_roleta(data)
        by_deck = self._cat_counts(state)
        for row in plan:
            row["roleta"] = by_deck.get(row["did"])
        return {
            "date": self._date_label(),
            "goal": progress,
            "plan": plan,
            "due": due,
            "eta_min": round(due * progress["avg_secs"] / 60),
            "roleta": self._roleta_summary(state),
        }

    @staticmethod
    def _roleta_summary(state: dict) -> dict:
        cat = ro.cur_cat(state)
        found = ro.find_topic(state, state.get("last"))
        last = None
        if found:
            c, sub, topic, _i = found
            last = {"t": topic["t"], "path": ro.path_of(c, sub), "note": topic.get("note") or "", "seen": topic.get("seen"), "deck": c.get("deck"), "cat": c["id"]}
        return {
            "has": bool(state["cats"]),
            "cat": cat["name"] if cat else None,
            "scope": ro.scope_name(cat) if cat else None,
            "counts": ro.counts(ro.scope_of(cat)[0]) if cat else None,
            "last": last,
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

    def _goal_done(self, goal: dict) -> float:
        cards, minutes = stats.today(self.col)
        return cards if goal["unit"] == "cards" else minutes

    def _session_info(self) -> dict:
        s = self.session or {}
        goal = self._data()["goal"]
        done = self._goal_done(goal)
        info = {
            "answered": s.get("answered", 0),
            "right": s.get("right", 0),
            "goal_done": round(done),
            "goal_value": goal["value"],
            "goal_unit": goal["unit"],
            "goal_reached": self.goal_flag,
        }
        self.goal_flag = False
        return info

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
        self.parsed = cardfmt.parse(self._prep(self.card.question(reload=True)), self._prep(self.card.answer()))
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
        goal = self._data()["goal"]
        before = self._goal_done(goal)
        answer = self.col.sched.build_answer(card=self.card, states=self.states, rating=RATINGS[rating])
        self.col.sched.answer_card(answer)
        after = self._goal_done(goal)
        self.goal_flag = before < goal["value"] <= after
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
        by_deck = self._cat_counts(self._mapped_roleta(data))
        nodes = stats.due_nodes(self.col)
        rows = []
        for name, did in self._matters(data):
            dids = stats.subtree(self.col, did)
            node = nodes.get(did)
            acc, answers = stats.accuracy(self.col, dids, 30)
            rows.append(
                {
                    "did": did,
                    "name": name,
                    "due": (node.new_count + node.learn_count + node.review_count) if node else 0,
                    "acc": acc,
                    "answers": answers,
                    "maturity": stats.maturity(self.col, dids),
                    "roleta": by_deck.get(did),
                }
            )
        return {"rows": rows}

    def materia(self, did: int) -> dict:
        did = int(did)
        if not self.col.decks.get(did, default=False):
            raise UserError("Esse baralho não existe mais.")
        data = self._data()
        state = self._mapped_roleta(data)
        dids = stats.subtree(self.col, did)
        node = stats.due_nodes(self.col).get(did)
        acc30, n30 = stats.accuracy(self.col, dids, 30)
        acc7, n7 = stats.accuracy(self.col, dids, 7)
        cat = next((c for c in state["cats"] if c.get("deck") == did), None)
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
            "roleta": {"cat": cat, "counts": ro.counts(cat["subs"]), "named": ro.has_named_subs(cat)} if cat else None,
        }

    # ------------------------------------------------------------------ roleta
    def _roleta_view(self, data: dict, extra: dict | None = None) -> dict:
        view = {
            "state": data["roleta"],
            "decks": [{"id": did, "name": name} for name, did in self._matters(data)],
            "can_undo": self.ro_undo is not None,
            "fx": data["fx"],
        }
        if extra:
            view.update(extra)
        return view

    def _ro_change(self, fn: Callable[[dict], Any], undoable: bool = False) -> dict:
        data = self._data()
        self._mapped_roleta(data)
        snapshot = copy.deepcopy(data["roleta"]) if undoable else None
        try:
            extra = fn(data["roleta"])
        except ro.RoletaError as err:
            raise UserError(str(err)) from err
        if undoable:
            self.ro_undo = snapshot
        self._save(data)
        return self._roleta_view(data, extra if isinstance(extra, dict) else None)

    def roleta(self) -> dict:
        data = self._data()
        self._mapped_roleta(data)
        return self._roleta_view(data)

    def roleta_select(self, cat: str, sel: str | None = None) -> dict:
        return self._ro_change(lambda s: ro.select(s, cat, sel))

    def roleta_spin(self, cat: str | None = None) -> dict:
        return self._ro_change(lambda s: {"pick": ro.spin(s, cat)})

    def roleta_again(self, tid: str) -> dict:
        return self._ro_change(lambda s: {"pick": ro.again(s, tid)})

    def roleta_toggle(self, tid: str) -> dict:
        return self._ro_change(lambda s: {"seen": ro.toggle_seen(s, tid)})

    def roleta_unsee(self, tid: str) -> dict:
        def run(s: dict) -> dict:
            found = ro.find_topic(s, tid)
            if found and found[2]["seen"]:
                ro.toggle_seen(s, tid)
            return {"toast": f"Voltou ao sorteio: {found[2]['t']}" if found else ""}

        return self._ro_change(run, undoable=True)

    def roleta_reset(self, cat: str | None = None) -> dict:
        return self._ro_change(lambda s: {"reset": ro.reset_scope(s, cat)}, undoable=True)

    def roleta_note(self, tid: str, note: str) -> dict:
        return self._ro_change(lambda s: ro.set_note(s, tid, note))

    def roleta_rename(self, tid: str, name: str) -> dict:
        return self._ro_change(lambda s: {"name": ro.rename_topic(s, tid, name)})

    def roleta_remove(self, tid: str) -> dict:
        return self._ro_change(lambda s: {"toast": f"Removido: {ro.remove_topic(s, tid)}"}, undoable=True)

    def roleta_add(self, cat: str, name: str, sub: str | None = None) -> dict:
        return self._ro_change(lambda s: {"added": ro.add_topic(s, cat, sub, name)["id"]})

    def roleta_save_cat(self, name: str, subs: list, cat: str | None = None, deck: Any = "keep") -> dict:
        """deck: a deck id, None to unlink, or "keep" to leave the link (or the automatic match) as is."""

        def run(s: dict) -> dict:
            result = ro.save_cat(s, cat, name, subs)
            if deck != "keep":
                ro.link_deck(s, result["cat"], deck)
            return result

        return self._ro_change(run, undoable=cat is not None)

    def roleta_delete_cat(self, cat: str) -> dict:
        return self._ro_change(lambda s: {"deleted": ro.delete_cat(s, cat)}, undoable=True)

    def roleta_inspect(self, text: str) -> dict:
        try:
            return ro.inspect_import(text)
        except ro.RoletaError as err:
            raise UserError(str(err)) from err

    def roleta_import(self, text: str) -> dict:
        return self._ro_change(lambda s: {"imported": ro.import_text(s, text)}, undoable=True)

    def roleta_file(self) -> dict:
        path, _filter = QFileDialog.getOpenFileName(mw, "Importar na Roleta", "", "JSON ou texto (*.json *.txt);;Todos os arquivos (*)")
        if not path:
            return {"cancel": True}
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
        return {"text": text, "inspect": self.roleta_inspect(text)}

    def roleta_save_backup(self) -> dict:
        data = self._data()
        stamp = time.strftime("%Y-%m-%d_%Hh%M")
        path, _filter = QFileDialog.getSaveFileName(mw, "Salvar backup da Roleta", f"roleta-backup-{stamp}.json", "JSON (*.json)")
        if not path:
            return {"cancel": True}
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(ro.backup_json(data["roleta"]))
        return {"saved": path}

    def roleta_copy(self, what: str = "backup") -> dict:
        state = self._data()["roleta"]
        QApplication.clipboard().setText(ro.backup_json(state) if what == "backup" else ro.topics_json(state))
        return {"ok": True}

    def roleta_clear(self) -> dict:
        def run(s: dict) -> None:
            s.update(ro.empty())

        return self._ro_change(run, undoable=True)

    def roleta_undo(self) -> dict:
        if self.ro_undo is None:
            raise UserError("Não há nada para desfazer na Roleta.")
        data = self._data()
        data["roleta"] = self.ro_undo
        self.ro_undo = None
        self._save(data)
        return self._roleta_view(data, {"toast": "Desfeito."})

    # ------------------------------------------------------------------ ajustes
    def settings(self) -> dict:
        data = self._data()
        decks = self.col.decks.all_names_and_ids(skip_empty_default=True, include_filtered=False)
        return {
            "goal": data["goal"],
            "root": data.get("root"),
            "fx": data["fx"],
            "parents": [{"id": int(d.id), "name": d.name} for d in decks if self.col.decks.children(d.id)],
            "matters": [name for name, _did in self._matters(data)],
            "version": VERSION,
            "profile": mw.pm.name,
        }

    def save_settings(self, goal: dict | None = None, root: int | None = None, fx: dict | None = None) -> dict:
        data = self._data()
        if goal:
            unit = "minutes" if goal.get("unit") == "minutes" else "cards"
            value = max(1, min(2000, int(float(goal.get("value") or 0))))
            data["goal"] = {"unit": unit, "value": value}
        data["root"] = int(root) if root else None
        if fx:
            data["fx"] = self._clean_fx({**data["fx"], **fx})
        self._save(data)
        return self.settings()

    def set_fx(self, **changes: Any) -> dict:
        data = self._data()
        data["fx"] = self._clean_fx({**data["fx"], **changes})
        self._save(data)
        return {"fx": data["fx"]}

    @staticmethod
    def _clean_fx(fx: dict) -> dict:
        volume = fx.get("volume", 0.7)
        try:
            volume = max(0.0, min(1.0, float(volume)))
        except (TypeError, ValueError):
            volume = 0.7
        return {"sound": bool(fx.get("sound", True)), "volume": round(volume, 2), "motion": bool(fx.get("motion", True))}

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
        else:
            raise UserError(f"Ação desconhecida: {what}")
        return {"ok": True}
