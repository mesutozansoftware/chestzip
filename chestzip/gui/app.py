"""Grafik arayüzün giriş noktası."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication

from .. import APP_NAME, APP_ID
from ..i18n import set_language
from ..settings import Settings
from .icons import icon
from .theme import apply_theme


class _FileOpenFilter(QObject):
    """macOS'ta Finder'dan çift tıklanan dosyalar argüman olarak değil,
    FileOpen olayıyla gelir."""

    def __init__(self, state: dict) -> None:
        super().__init__()
        self.state = state

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.FileOpen:
            path = event.file()
            if path:
                win = self.state.get("win")
                if win is None:
                    self.state.setdefault("pending", []).append(path)
                else:
                    _handle_paths(win, [Path(path)])
                return True
        return False


def run(paths: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(icon("app"))
    settings = Settings.load()
    state: dict = {}
    file_filter = _FileOpenFilter(state)
    app.installEventFilter(file_filter)

    def build() -> None:
        from .main_window import MainWindow
        set_language(settings.language)
        apply_theme(app, settings.theme)
        old = state.get("win")
        win = MainWindow(settings, restart_cb=lambda: QTimer.singleShot(0, build))
        if old is not None:
            win.resize(old.size())
            win.move(old.pos())
            old.close()
        elif len(settings.window) == 2:
            win.resize(*settings.window)
        state["win"] = win
        win.show()

    build()
    _handle_paths(state["win"], [Path(p) for p in (paths or [])])
    for p in state.pop("pending", []):
        _handle_paths(state["win"], [Path(p)])
    return app.exec()


def _handle_paths(win, paths: list[Path]) -> None:
    if not paths:
        return
    if len(paths) == 1:
        p = paths[0]
        if p.is_dir():
            win.navigate_fs(p)
            return
        if p.is_file() and win._looks_like_archive(p):
            win.navigate_fs(p.parent, select=p.name)
            win.open_archive(p)
            return
    win.navigate_fs(paths[0].parent)
    win._create_archive(paths)


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
