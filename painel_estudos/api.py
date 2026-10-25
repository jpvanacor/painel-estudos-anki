"""What the page can ask for. Each public method answers one call from the page."""

from __future__ import annotations

import copy
import time
from collections import Counter
from typing import Any, Callable

from anki.cards import Card
from anki.collection import SearchNode
from anki.decks import DeckId, FilteredDeckConfig
from anki.errors import FilteredDeckError
from anki.scheduler.v3 import CardAnswer
from anki.utils import ids2str
from aqt import dialogs, mw
from aqt.qt import QApplication, QFileDialog
from aqt.sound import av_player
from aqt.theme import theme_manager

from . import cards as cardfmt
from . import mobile
from . import roleta as ro
from . import stats, store, topics

VERSION = "0.4.0"
RATINGS = {1: CardAnswer.AGAIN, 2: CardAnswer.HARD, 3: CardAnswer.GOOD, 4: CardAnswer.EASY}
# Topic and error sessions run in a filtered deck of their own, emptied and removed at the end.
TEMP_DECK = "Painel de Estudos (sessão)"
ORDER = FilteredDeckConfig.SearchTerm.Order
ERROR_DAYS = (1, 7, 30)
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
        self._home_deck: int | None = None  # Anki's current deck before a topic or error session

    @property
    def col(self):
        return mw.col

    # ------------------------------------------------------------------ general
    def boot(self) -> dict:
        data = self._data()
        self.session = None
        self.card = None
        self._drop_temp()  # left over if Anki closed during a topic or error session
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
            "roleta": self._roleta_summary(data),
            "erros7": self._missed_cards(7),
        }

    def _missed_cards(self, days: int) -> int:
        since = (int(self.col.sched.day_cutoff) - days * stats.DAY) * 1000
        return int(self.col.db.scalar("select count(distinct cid) from revlog where ease = 1 and id >= ?", since) or 0)

    def _roleta_summary(self, data: dict) -> dict:
        state = data["roleta"]
        cat = ro.cur_cat(state)
        found = ro.find_topic(state, state.get("last"))
        last = None
        if found:
            c, sub, topic, _i = found
            last = {
                "id": topic["id"],
                "t": topic["t"],
                "path": ro.path_of(c, sub),
                "note": topic.get("note") or "",
                "seen": topic.get("seen"),
                "deck": c.get("deck"),
                "cat": c["id"],
                "cards": self._topic_info(data, topic["id"]),
            }
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
        self._drop_temp()
        if did:
            decks = [int(did)]
        else:
            decks = [row["did"] for row in stats.plan(self.col, data.get("root")) if row["due"] > 0]
        self.session = self._new_session(decks, single=bool(did))
        return self._next()

    @staticmethod
    def _new_session(decks: list[int], single: bool, **extra: Any) -> dict:
        return {
            "decks": decks,
            "i": 0,
            "single": single,
            "answered": 0,
            "right": 0,
            "started": time.time(),
            "actions": [],
            "title": None,  # shown instead of the deck name (topic and error sessions)
            "kind": None,  # None, "topic" or "errors"
            **extra,
        }

    def stop(self) -> dict:
        av_player.stop_and_clear_queue()
        self.session = None
        self.card = None
        try:
            self._drop_temp()
        except Exception:  # the collection may be closing
            pass
        return {"ok": True}

    # ------------------------------------------------------------------ sessions on chosen cards
    def _drop_temp(self) -> None:
        """Empties and removes the panel's filtered deck; its cards go back to their decks."""
        did = self.col.decks.id_for_name(TEMP_DECK)
        if not did or not self.col.decks.is_filtered(did):
            return
        self.col.sched.empty_filtered_deck(did)
        self.col.decks.remove([did])
        home = self._home_deck
        self._home_deck = None
        if home and self.col.decks.get(home, default=False):
            self.col.decks.select(DeckId(home))

    def _build_temp(self, search: str, limit: int, order: int) -> int:
        self._drop_temp()
        current = int(self.col.decks.get_current_id())
        self._home_deck = None if self.col.decks.is_filtered(current) else current
        deck = self.col.sched.get_or_create_filtered_deck(deck_id=DeckId(0))
        deck.name = TEMP_DECK
        deck.config.reschedule = True  # answers count as normal reviews
        del deck.config.search_terms[:]
        deck.config.search_terms.append(FilteredDeckConfig.SearchTerm(search=search, limit=max(1, min(int(limit), 9999)), order=order))
        try:
            return int(self.col.sched.add_or_update_filtered_deck(deck).id)
        except FilteredDeckError as err:
            self._home_deck = None
            raise UserError("Nenhum desses cartões pode ser estudado agora: estão suspensos, enterrados ou em outro baralho filtrado.") from err

    def _start_temp(self, search: str, limit: int, order: int, title: str, kind: str, **extra: Any) -> dict:
        av_player.stop_and_clear_queue()
        self.session = None
        self.card = None
        did = self._build_temp(search, limit, order)
        self.session = self._new_session([did], single=True, title=title, kind=kind, **extra)
        return self._next()

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
        if self.session and self.session.get("title"):
            return self.session["title"]
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
        trap = self.parsed.trap
        return {
            "right": self.result["right"],
            "choice": self.result["choice"],
            "correct": self.parsed.correct,
            "back": self.parsed.back,
            "labels": self._labels(),
            "trap": {"from": trap[0], "to": trap[1]} if trap else None,
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

    def answer(self, rating: int, reason: str | None = None) -> dict:
        """reason: why a Certo/Errado or question card was missed (store.REASONS), optional."""
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
        data = self._data()
        goal = data["goal"]
        before = self._goal_done(goal)
        cid = self.card.id
        answer = self.col.sched.build_answer(card=self.card, states=self.states, rating=RATINGS[rating])
        self.col.sched.answer_card(answer)
        after = self._goal_done(goal)
        self.goal_flag = before < goal["value"] <= after
        action = {"kind": "answer", "right": right, "cid": cid, "i": self.session["i"]}
        if not right and reason in store.REASONS:
            rid = self.col.db.scalar("select max(id) from revlog where cid = ?", cid)
            if rid:
                data["reasons"][str(rid)] = reason
                self._save(data)
                action["rid"] = str(rid)
        self.session["answered"] += 1
        self.session["right"] += int(right)
        self.session["actions"].append(action)
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
            if action.get("rid"):
                data = self._data()
                if data["reasons"].pop(action["rid"], None):
                    self._save(data)
        session["i"] = action["i"]
        return self._next(prefer_card=action["cid"])

    def replay(self) -> dict:
        if self.card:
            tags = self.card.question_av_tags() if self.phase == "question" else self.card.answer_av_tags()
            av_player.play_tags(tags or self.card.question_av_tags())
        return {"ok": True}

    def edit(self, cid: int | None = None) -> dict:
        target = int(cid) if cid else (self.card.id if self.card else None)
        if target:
            dialogs.open("Browser", mw, search=(f"cid:{target}",))
        return {"ok": True}

    def _finish(self) -> dict:
        session = self.session or {}
        self.card = None
        minutes = (time.time() - session.get("started", time.time())) / 60
        name = session.get("title")
        if not name and session.get("single") and session.get("decks"):
            name = stats.leaf(self.col.decks.name(session["decks"][0]))
        if session.get("kind"):
            self._drop_temp()
        return {
            "view": "done",
            "answered": session.get("answered", 0),
            "right": session.get("right", 0),
            "minutes": round(minutes),
            "deck": name,
            "kind": session.get("kind"),
            "days": session.get("days"),
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

    # ------------------------------------------------------------------ caderno de erros
    def erros(self, days: int = 7) -> dict:
        """Cards answered wrong (De novo) in the last days, by matéria and law."""
        days = int(days) if int(days) in ERROR_DAYS else 7
        since = (int(self.col.sched.day_cutoff) - days * stats.DAY) * 1000
        data = self._data()
        reasons = data["reasons"]
        misses: dict[int, dict] = {}
        tally: Counter = Counter()
        for rid, cid in self.col.db.all("select id, cid from revlog where ease = 1 and id >= ? order by id", since):
            entry = misses.setdefault(cid, {"n": 0, "last": 0, "reason": None})
            entry["n"] += 1
            entry["last"] = rid
            reason = reasons.get(str(rid))
            if reason:
                entry["reason"] = reason
            tally[reason or "none"] += 1
        temp = self.col.decks.id_for_name(TEMP_DECK)
        home_of: dict[int, tuple[int, str]] = {}
        for name, mdid in self._matters(data):
            for did in stats.subtree(self.col, mdid):
                home_of[did] = (mdid, name)
        groups: dict[int, dict] = {}
        available = 0
        if misses:
            rows = self.col.db.all(
                "select c.id, c.did, c.odid, c.queue, n.flds, n.tags from cards c join notes n on n.id = c.nid "
                f"where c.id in {ids2str(misses)}"
            )
            for cid, did, odid, queue, flds, tags in rows:
                fields = flds.split("\x1f")
                front, back = fields[0], (fields[1] if len(fields) > 1 else "")
                mdid, mname = home_of.get(odid or did, (0, "Outros baralhos"))
                law = topics.law_of_tags(tags)
                arts = topics.card_articles(front)
                trap = cardfmt.trap_of(back)
                ok = queue >= 0 and (not odid or did == temp)
                available += int(ok)
                miss = misses[cid]
                group = groups.setdefault(mdid, {"did": mdid, "name": mname, "items": [], "available": 0})
                group["available"] += int(ok)
                group["items"].append(
                    {
                        "cid": cid,
                        "text": topics.statement(front)[:400],
                        "n": miss["n"],
                        "last": miss["last"],
                        "reason": miss["reason"],
                        "law": law[1] if law else "",
                        "art": arts[0][0] if arts else None,
                        "correct": cardfmt.gabarito_of(back),
                        "trap": {"from": trap[0], "to": trap[1]} if trap else None,
                        "ok": ok,
                        "suspended": queue == -1,
                    }
                )
        for group in groups.values():
            group["items"].sort(key=lambda it: (it["law"].lower(), it["art"] if it["art"] is not None else 10**9, -it["n"]))
        ordered = sorted(groups.values(), key=lambda g: (g["did"] == 0, -len(g["items"]), g["name"].lower()))
        return {
            "days": days,
            "misses": sum(m["n"] for m in misses.values()),
            "cards": len(misses),
            "available": available,
            "reasons": [{"code": code, "label": label, "n": tally.get(code, 0)} for code, label in store.REASONS.items()],
            "no_reason": tally.get("none", 0),
            "groups": ordered,
        }

    def erro_card(self, cid: int) -> dict:
        """A missed card as Anki draws it, for reading the explanation again."""
        card = self.col.get_card(int(cid))
        parsed = cardfmt.parse(self._prep(card.question()), self._prep(card.answer()))
        return {"mode": parsed.mode, "css": parsed.css, "front": parsed.front, "back": parsed.back}

    def study_errors(self, days: int = 7, did: int | None = None) -> dict:
        days = int(days) if int(days) in ERROR_DAYS else 7
        nodes = [SearchNode(rated=SearchNode.Rated(days=days, rating=SearchNode.RATING_AGAIN))]
        period = "de hoje" if days == 1 else f"dos últimos {days} dias"
        title = f"Erros {period}"
        if did:
            name = self.col.decks.name(int(did))
            nodes.append(SearchNode(deck=name))
            title = f"Erros {period}, {stats.leaf(name)}"
        search = self.col.build_search_string(*nodes)
        return self._start_temp(search, 9999, ORDER.RANDOM, title=title, kind="errors", days=days)

    # ------------------------------------------------------------------ roleta: the cards of a topic
    def _card_entries(self, did: int) -> list[dict]:
        """Each card of a deck (and subdecks) with the article it starts with and its law."""
        ids = ids2str(stats.subtree(self.col, did))
        rows = self.col.db.all(
            "select c.id, c.queue, substr(n.flds, 1, 300), n.tags from cards c join notes n on n.id = c.nid "
            f"where c.did in {ids} or c.odid in {ids}"
        )
        entries = []
        for cid, queue, start, tags in rows:
            law = topics.law_of_tags(tags)
            entries.append(
                {
                    "cid": cid,
                    "ok": queue >= 0,
                    "arts": topics.card_articles(start.split("\x1f", 1)[0]),
                    "law": law[0] if law else None,
                    "law_label": law[1] if law else None,
                    "tags": topics.content_tags(tags),
                }
            )
        return entries

    def _topic_lookup(self, data: dict, tid: str) -> tuple[dict, dict, dict, int | None]:
        found = ro.find_topic(data["roleta"], tid)
        if not found:
            raise UserError("Esse tópico não existe mais.")
        cat, sub, topic, _i = found
        did = cat.get("deck")
        if did and not self.col.decks.get(did, default=False):
            did = None
        return cat, sub, topic, did

    def _topic_match(self, cat: dict, sub: dict, topic: dict, did: int, entries: list[dict] | None = None) -> dict:
        names = [sub.get("name") or "", cat["name"], self.col.decks.name(did)]
        return topics.topic_cards(topic["t"], topic.get("cards"), entries if entries is not None else self._card_entries(did), names)

    def _topic_info(self, data: dict, tid: str, with_tags: bool = False) -> dict:
        cat, sub, topic, did = self._topic_lookup(data, tid)
        if not did:
            return {"tid": tid, "mode": "nodeck", "count": 0}
        entries = self._card_entries(did)
        info = self._topic_match(cat, sub, topic, did, entries)
        out = {k: v for k, v in info.items() if k not in ("cids", "ranges")}
        out.update({"tid": tid, "deck": did, "deck_name": stats.leaf(self.col.decks.name(did)), "count": len(info["cids"])})
        if info["mode"] == "tag":
            out["tag_label"] = topics.tag_label(info["tag"])
        if with_tags or info["mode"] == "none" or (info["mode"] == "articles" and not info["cids"] and not info["ambiguous"]):
            counts = topics.tag_counts(entries)
            suggestion = topics.suggest_tag(topic["t"], counts)
            if suggestion:
                out["suggest"] = {"tag": suggestion, "label": topics.tag_label(suggestion), "n": counts[suggestion]}
            if with_tags:
                out["tags"] = [{"tag": t, "label": topics.tag_label(t), "n": n} for t, n in sorted(counts.items(), key=lambda kv: kv[0].lower())]
        return out

    def roleta_topic_cards(self, tid: str, tags: bool = False) -> dict:
        return self._topic_info(self._data(), tid, with_tags=bool(tags))

    def roleta_link(self, tid: str, link: Any = None) -> dict:
        """link: None to go back to the articles of the name, {"law": key} or {"tag": tag}."""
        view = self._ro_change(lambda s: ro.set_cards_link(s, tid, link))
        view["cards"] = self._topic_info(self._data(), tid, with_tags=True)
        return view

    def roleta_card_counts(self, cat: str) -> dict:
        """How many cards each topic of a matéria has, for topics whose cards can be found."""
        data = self._data()
        c = ro.find_cat(data["roleta"], cat)
        did = c.get("deck") if c else None
        if not c or not did or not self.col.decks.get(did, default=False):
            return {"cat": cat, "counts": {}}
        entries = self._card_entries(did)
        counts = {}
        for sub in c["subs"]:
            for topic in sub["topics"]:
                info = self._topic_match(c, sub, topic, did, entries)
                if info["mode"] != "none":
                    counts[topic["id"]] = {"n": len(info["cids"]), "ambiguous": bool(info.get("ambiguous"))}
        return {"cat": cat, "counts": counts}

    def study_topic(self, tid: str) -> dict:
        data = self._data()
        cat, sub, topic, did = self._topic_lookup(data, tid)
        if not did:
            raise UserError("Ligue esta matéria a um baralho em Organizar para estudar os cartões dos tópicos.")
        info = self._topic_match(cat, sub, topic, did)
        if info.get("ambiguous"):
            raise UserError("Escolha antes a lei deste tópico.")
        cids = info["cids"]
        if not cids:
            raise UserError("Nenhum cartão deste tópico para estudar.")
        # in the order they were added, which follows the law for cards made by the skill
        return self._start_temp(f"cid:{','.join(map(str, cids))}", len(cids), ORDER.ADDED, title=topic["t"], kind="topic", tid=tid)

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
            "mobile": self.mobile_status(),
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

    # ------------------------------------------------------------------ celular (AnkiDroid)
    def mobile_status(self) -> dict:
        """The note types with Certo/Errado items or questions, and whether the phone block is in them."""
        counts = dict(self.col.db.all(mobile.NOTES_SQL))
        types = []
        for nt in self.col.models.all():
            state = mobile.state_of(nt["tmpls"])
            notes = counts.get(nt["id"], 0)
            if notes or state != "off":
                types.append({"id": nt["id"], "name": nt["name"], "notes": notes, "state": state})
        types.sort(key=lambda t: -t["notes"])
        return {"types": types, "version": mobile.VERSION}

    def mobile_enable(self) -> dict:
        script, style = mobile.assets()
        changed = 0
        for t in self.mobile_status()["types"]:
            if not t["notes"]:
                continue
            nt = self.col.models.get(t["id"])
            for tmpl in nt["tmpls"]:
                tmpl["qfmt"] = mobile.apply(tmpl["qfmt"], "q", script, style)
                tmpl["afmt"] = mobile.apply(tmpl["afmt"], "a", script, style)
            self.col.models.update_dict(nt)
            changed += 1
        if not changed:
            raise UserError("Nenhum modelo de cartão com itens Certo/Errado ou questões foi encontrado.")
        return self.mobile_status()

    def mobile_disable(self) -> dict:
        for nt in self.col.models.all():
            if mobile.state_of(nt["tmpls"]) == "off":
                continue
            for tmpl in nt["tmpls"]:
                tmpl["qfmt"] = mobile.strip(tmpl["qfmt"])
                tmpl["afmt"] = mobile.strip(tmpl["afmt"])
            self.col.models.update_dict(nt)
        return self.mobile_status()

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
