"""Puts the page in Anki's main window, and gives the window back to Anki on request."""

from __future__ import annotations

import json
import traceback
from typing import Any

from aqt import gui_hooks, mw
from aqt.qt import QAction, QShortcut, QTimer, QWidget, qconnect
from aqt.theme import theme_manager
from aqt.webview import AnkiWebView

from .api import Api, UserError

# Anki's single-key shortcuts for the main window. They would fire while typing in the page
# (for example "a" opens Add), so they are switched off while the panel is showing.
ANKI_KEYS = {"D", "S", "A", "B", "T", "Shift+T", "Y", "/"}

PUBLIC = {
    "boot", "home", "start", "stop", "current", "reveal", "choose", "answer", "bury", "suspend",
    "undo", "replay", "edit", "materias", "materia", "settings", "save_settings", "set_fx", "open",
    "roleta", "roleta_select", "roleta_spin", "roleta_again", "roleta_toggle", "roleta_unsee",
    "roleta_reset", "roleta_note", "roleta_rename", "roleta_remove", "roleta_add", "roleta_save_cat",
    "roleta_delete_cat", "roleta_inspect", "roleta_import", "roleta_file", "roleta_save_backup",
    "roleta_copy", "roleta_clear", "roleta_undo", "roleta_topic_cards", "roleta_link",
    "roleta_card_counts", "study_topic", "erros", "erro_card", "study_errors",
}


class Shell:
    def __init__(self, addon_folder: str) -> None:
        self.addon = addon_folder
        self.api = Api(self)
        self.active = False
        self.loaded = False
        # Anki's own panels are moved here while the panel shows. This widget is never shown.
        self.parking = QWidget()
        self.web = AnkiWebView(parent=mw, title="Painel de Estudos")
        self.web.set_bridge_command(self.on_bridge, self)
        self.web.hide()
        mw.mainLayout.addWidget(self.web)
        self.action = QAction("Abrir o Painel de Estudos", mw)
        qconnect(self.action.triggered, self.show_panel)
        mw.form.menuTools.addAction(self.action)
        self._install_hooks()

    # ------------------------------------------------------------------ window
    def show_panel(self) -> None:
        if self.active:
            self.send({"type": "refresh"})
            return
        for widget in (mw.toolbarWeb, mw.web, mw.bottomWeb):
            mw.mainLayout.removeWidget(widget)
            widget.setParent(self.parking)
        mw.form.menubar.hide()
        self.web.show()
        self.web.setFocus()
        self.active = True
        self._anki_shortcuts(False)
        if self.loaded:
            self.send({"type": "refresh"})
        else:
            self.load()

    def show_anki_ui(self) -> None:
        if not self.active:
            return
        self.api.stop()
        self.active = False
        self.web.hide()
        for index, widget in enumerate((mw.toolbarWeb, mw.web, mw.bottomWeb)):
            mw.mainLayout.insertWidget(index, widget)
            widget.show()
        mw.form.menubar.show()
        self._anki_shortcuts(True)
        mw.moveToState("deckBrowser")

    def _anki_shortcuts(self, enabled: bool) -> None:
        for shortcut in mw.findChildren(QShortcut):
            if shortcut.key().toString() in ANKI_KEYS:
                shortcut.setEnabled(enabled)
        for shortcut in list(getattr(mw, "stateShortcuts", []) or []):
            try:
                shortcut.setEnabled(enabled)
            except RuntimeError:
                pass

    def load(self) -> None:
        base = f"/_addons/{self.addon}/web"
        self.web.stdHtml(
            '<div id="app"></div>',
            css=[f"{base}/app.css"],
            js=[f"{base}/app.js"],
            context=self,
            default_css=False,
        )
        self.loaded = True

    def send(self, payload: dict[str, Any]) -> None:
        if self.loaded:
            self.web.eval(f"window.PE && window.PE.event({json.dumps(payload)});")

    # ------------------------------------------------------------------ messages from the page
    def on_bridge(self, cmd: str) -> Any:
        if not cmd.startswith("pe:"):
            return None
        try:
            request = json.loads(cmd[3:])
            method = request.get("m", "")
            if method not in PUBLIC:
                raise UserError(f"Comando desconhecido: {method}")
            if not mw.col:
                raise UserError("A coleção do Anki está fechada.")
            if method == "open" and (request.get("a") or {}).get("what") == "anki":
                QTimer.singleShot(0, self.show_anki_ui)
                return {"ok": True}
            return getattr(self.api, method)(**(request.get("a") or {}))
        except UserError as err:
            return {"error": str(err)}
        except Exception as err:  # shown in the page, details in Anki's console
            traceback.print_exc()
            return {"error": f"Algo deu errado: {err}"}

    # ------------------------------------------------------------------ Anki events
    def _install_hooks(self) -> None:
        gui_hooks.operation_did_execute.append(self._on_operation)
        gui_hooks.state_did_change.append(self._on_state)
        gui_hooks.state_shortcuts_will_change.append(self._on_state_shortcuts)
        gui_hooks.theme_did_change.append(self._on_theme)
        gui_hooks.sync_will_start.append(self._on_sync_start)
        gui_hooks.sync_did_finish.append(self._on_sync_done)
        gui_hooks.profile_will_close.append(self._on_profile_close)

    def _on_operation(self, changes: Any, handler: object | None) -> None:
        if not self.active or handler is self:
            return
        self.send(
            {
                "type": "changed",
                "note_text": bool(changes.note_text),
                "study_queues": bool(changes.study_queues),
                "deck": bool(changes.deck),
            }
        )

    def _on_state(self, new_state: str, _old_state: str) -> None:
        # Something in Anki asked for its own study screens; keep them closed behind the panel.
        if self.active and new_state in ("overview", "review"):
            QTimer.singleShot(0, lambda: mw.moveToState("deckBrowser"))
            self.send({"type": "refresh"})

    def _on_state_shortcuts(self, _state: str, shortcuts: list) -> None:
        if self.active:
            shortcuts.clear()

    def _on_theme(self) -> None:
        self.send({"type": "theme", "night": theme_manager.night_mode})

    def _on_sync_start(self) -> None:
        self.send({"type": "sync", "state": "start"})

    def _on_sync_done(self) -> None:
        self.send({"type": "sync", "state": "done"})

    def _on_profile_close(self) -> None:
        self.api.stop()
