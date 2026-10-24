"""Painel de Estudos: a study interface that takes over Anki's main window.

Anki keeps the cards, the scheduling, the sync and its own windows (Add, Browse, Stats,
deck options). This add-on only draws the screens and asks Anki for the data.
"""

from __future__ import annotations

from aqt import gui_hooks, mw

mw.addonManager.setWebExports(__name__, r"web/.*\.(css|js|woff2|svg|png)$")

from .shell import Shell  # noqa: E402

_shell: Shell | None = None


def _addon_folder() -> str:
    manager = mw.addonManager
    finder = getattr(manager, "addon_from_module", None) or manager.addonFromModule
    return finder(__name__)


def _on_profile_open() -> None:
    global _shell
    if _shell is None:
        _shell = Shell(_addon_folder())
        mw.painel_estudos = _shell  # lets a test harness reach the panel
    _shell.show_panel()


gui_hooks.profile_did_open.append(_on_profile_open)
