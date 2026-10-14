"""Ana pencere: dosya sistemi ve arşiv içi gezgin."""

from __future__ import annotations

import os
import shutil
import string
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import (QAbstractTableModel, QMimeData, QModelIndex, QSize, Qt, QTimer,
                            QUrl, Signal)
from PySide6.QtGui import QAction, QDesktopServices, QDrag, QIcon, QKeySequence
from PySide6.QtCore import QFile, QItemSelectionModel
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QToolBar, QToolButton, QTreeView, QVBoxLayout, QWidget)

from .. import APP_NAME
from ..api import Archive, OperationResult, create_archive
from ..backends import ARCHIVE_EXTENSIONS, detect_format
from ..errors import (ArchiveError, Cancelled, PasswordRequired, SafetyError,
                      UnsupportedFormat, WrongPassword)
from ..i18n import t
from ..safety import MiB, human_size
from ..settings import Settings
from . import dialogs
from .icons import icon, pixmap
from .workers import Task, connect_ask

IS_WINDOWS = sys.platform.startswith("win")
COLUMNS = ["name", "size", "packed", "ratio", "type", "modified", "crc"]
ARCHIVE_ONLY_COLUMNS = {"packed", "ratio", "crc"}


@dataclass
class Row:
    name: str
    is_dir: bool
    key: str                      # dosya sistemi yolu veya arşiv içi ad
    size: Optional[int] = None
    packed: Optional[int] = None
    mtime: Optional[datetime] = None
    crc: Optional[int] = None
    encrypted: bool = False
    kind: str = "file"            # file | dir | archive | link | drive

    @property
    def ext(self) -> str:
        n = self.name.lower()
        for e in sorted(ARCHIVE_EXTENSIONS, key=len, reverse=True):
            if n.endswith(e):
                return e[1:].upper()
        return Path(self.name).suffix[1:].upper()

    def type_text(self) -> str:
        if self.kind == "drive":
            return ""
        if self.is_dir:
            return t("type.folder")
        if self.kind == "archive":
            return t("type.archive", fmt=self.ext)
        if self.kind == "link":
            return t("type.link")
        return t("type.file", ext=self.ext) if self.ext else t("type.file_plain")

    def icon_name(self) -> str:
        if self.is_dir:
            return "folder"
        return {"archive": "archive", "link": "link"}.get(self.kind, "file")


def is_archive_name(name: str) -> bool:
    return name.lower().endswith(ARCHIVE_EXTENSIONS)


# --------------------------------------------------------------------------

class FileModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[Row] = []
        self.archive_mode = False
        self._sort = (0, Qt.SortOrder.AscendingOrder)

    def set_rows(self, rows: list[Row], archive_mode: bool) -> None:
        self.beginResetModel()
        self.rows = rows
        self.archive_mode = archive_mode
        self._apply_sort()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return t(f"col.{COLUMNS[section]}")
        if role == Qt.ItemDataRole.TextAlignmentRole and COLUMNS[section] in ("size", "packed",
                                                                                "ratio"):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = COLUMNS[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if col == "name":
                return row.name + (" *" if row.encrypted and not row.is_dir else "")
            if col == "size":
                if row.size is None or (row.is_dir and not self.archive_mode):
                    return ""
                return f"{row.size:,}".replace(",", ".")
            if col == "packed":
                return "" if row.packed is None else f"{row.packed:,}".replace(",", ".")
            if col == "ratio":
                if row.packed is None or not row.size:
                    return ""
                return f"{min(row.packed / row.size, 9.99) * 100:.0f}%"
            if col == "type":
                return row.type_text()
            if col == "modified":
                return row.mtime.strftime("%Y-%m-%d %H:%M") if row.mtime else ""
            if col == "crc":
                return f"{row.crc:08X}" if row.crc is not None and not row.is_dir else ""
        if role == Qt.ItemDataRole.DecorationRole and col == "name":
            return icon(row.icon_name())
        if role == Qt.ItemDataRole.TextAlignmentRole and col in ("size", "packed", "ratio"):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and col == "name":
            return row.name
        return None

    def flags(self, index):
        f = super().flags(index)
        return f | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else f

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        self._sort = (column, order)
        self.layoutAboutToBeChanged.emit()
        self._apply_sort()
        self.layoutChanged.emit()

    def _apply_sort(self) -> None:
        column, order = self._sort
        col = COLUMNS[column]
        rev = order == Qt.SortOrder.DescendingOrder

        def key(r: Row):
            if col == "size":
                return r.size or 0
            if col == "packed":
                return r.packed or 0
            if col == "ratio":
                return (r.packed / r.size) if r.packed is not None and r.size else 0
            if col == "type":
                return r.type_text().lower()
            if col == "modified":
                return r.mtime.timestamp() if r.mtime else 0
            if col == "crc":
                return r.crc or 0
            return r.name.lower()

        dirs = sorted([r for r in self.rows if r.is_dir], key=key, reverse=rev)
        files = sorted([r for r in self.rows if not r.is_dir], key=key, reverse=rev)
        self.rows = dirs + files  # klasörler her zaman üstte


class FileView(QTreeView):
    files_dropped = Signal(list)

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.win = window
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setIconSize(QSize(20, 20))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    # Dışarıdan bırakma -------------------------------------------------------
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls() and e.source() is not self:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasUrls() and e.source() is not self:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e) -> None:
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            e.acceptProposedAction()
            self.files_dropped.emit(paths)

    # Dışarı sürükleme ------------------------------------------------------
    def startDrag(self, actions) -> None:
        paths = self.win.paths_for_drag()
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(pixmap("archive" if self.win.archive else "file", 32))
        drag.exec(Qt.DropAction.CopyAction)


# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, restart_cb: Callable[[], None]) -> None:
        super().__init__()
        self.settings = settings
        self.restart_cb = restart_cb
        self.archive: Optional[Archive] = None
        self.inner = ""
        self.fs_dir: Optional[Path] = None
        self.tree: dict[str, dict[str, Row]] = {}
        self._tasks: list[Task] = []
        self._temp_dirs: list[Path] = []

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon("app"))
        self.resize(1000, 640)
        self._build_actions()
        self._build_ui()
        start = Path(settings.last_dir) if settings.last_dir else Path.home()
        self.navigate_fs(start if start.is_dir() else Path.home())

    # ---------------------------------------------------------------- arayüz
    def _act(self, key: str, icon_name: Optional[str], slot, shortcut=None) -> QAction:
        a = QAction(icon(icon_name) if icon_name else QIcon(), t(key), self)
        a.triggered.connect(slot)
        if isinstance(shortcut, (list, tuple)):
            a.setShortcuts([QKeySequence(s) for s in shortcut])
        elif shortcut:
            a.setShortcut(QKeySequence(shortcut))
        return a

    def _build_actions(self) -> None:
        self.a_add = self._act("act.add", "add", self.on_add, "Alt+A")
        self.a_extract = self._act("act.extract", "extract", self.on_extract, "Alt+E")
        self.a_extract_here = self._act("act.extract_here", "extract", self.on_extract_here,
                                        "Alt+W")
        self.a_test = self._act("act.test", "test", self.on_test, "Alt+T")
        self.a_view = self._act("act.view", "view", self.on_view, "Alt+V")
        self.a_delete = self._act("act.delete", "delete", self.on_delete, ["Delete", "Ctrl+Backspace"])
        self.a_info = self._act("act.info", "info", self.on_info, "Alt+I")
        self.a_settings = self._act("act.settings", "settings", self.on_settings, "Ctrl+,")
        self.a_up = self._act("act.up", "up", self.go_up, ["Backspace", "Alt+Up"])
        self.a_open = self._act("act.open", "archive", self.on_open_dialog, "Ctrl+O")
        self.a_folder = self._act("act.open_folder", "folder", self.on_open_folder, "Ctrl+G")
        self.a_quit = self._act("act.quit", None, self.close, "Ctrl+Q")
        self.a_about = self._act("act.about", "app", lambda: dialogs.show_about(self))
        self.a_refresh = self._act("act.open", None, self.refresh, "F5")
        self.addAction(self.a_refresh)

    def _build_ui(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu(t("menu.file"))
        for a in (self.a_open, self.a_folder):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_quit)
        m = mb.addMenu(t("menu.commands"))
        for a in (self.a_add, self.a_extract, self.a_extract_here, self.a_test, self.a_view,
                  self.a_delete, self.a_info):
            m.addAction(a)
        m = mb.addMenu(t("menu.options"))
        m.addAction(self.a_settings)
        m = mb.addMenu(t("menu.help"))
        m.addAction(self.a_about)

        tb = QToolBar()
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(36, 36))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for a in (self.a_add, self.a_extract, self.a_test, self.a_view, self.a_delete):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.a_info)
        tb.addAction(self.a_settings)
        self.addToolBar(tb)

        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        nav = QWidget()
        nav.setObjectName("navBar")
        h = QHBoxLayout(nav)
        h.setContentsMargins(6, 5, 6, 5)
        up = QToolButton()
        up.setDefaultAction(self.a_up)
        up.setIconSize(QSize(18, 18))
        up.setAutoRaise(True)
        h.addWidget(up)
        self.path_icon = QLabel()
        h.addWidget(self.path_icon)
        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self.on_path_entered)
        h.addWidget(self.path_edit, 1)
        self.badge = QLabel()
        self.badge.setObjectName("badge")
        h.addWidget(self.badge)
        v.addWidget(nav)

        self.model = FileModel()
        self.view = FileView(self)
        self.view.setModel(self.model)
        self.view.doubleClicked.connect(self.on_activate)
        self.view.files_dropped.connect(self.on_files_dropped)
        self.view.customContextMenuRequested.connect(self.on_context_menu)
        self.view.selectionModel().selectionChanged.connect(self.update_status)
        self.view.selectionModel().currentChanged.connect(self.update_status)
        hdr = self.view.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, w in enumerate([0, 110, 110, 64, 150, 130, 84]):
            if i:
                self.view.setColumnWidth(i, w)
        hdr.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        v.addWidget(self.view, 1)
        self.setCentralWidget(central)

        sb = self.statusBar()
        self.status_left = QLabel()
        sb.addWidget(self.status_left, 1)
        self.lock_label = QLabel(t("status.encrypted"))
        sb.addPermanentWidget(self.lock_label)
        self.safety_label = QLabel()
        sb.addPermanentWidget(self.safety_label)
        self.update_safety_label()

        enter = QAction(self)
        enter.setShortcuts([QKeySequence(Qt.Key.Key_Return), QKeySequence(Qt.Key.Key_Enter)])
        enter.triggered.connect(lambda: self.on_activate(self.view.currentIndex()))
        self.view.addAction(enter)
        self.setAcceptDrops(False)

    def update_safety_label(self) -> None:
        on = self.settings.limits.enabled
        self.safety_label.setText(t("status.safety_on") if on else t("status.safety_off"))
        self.safety_label.setObjectName("safetyOn" if on else "safetyOff")
        self.safety_label.style().unpolish(self.safety_label)
        self.safety_label.style().polish(self.safety_label)

    # ------------------------------------------------------------- gezinme
    def navigate_fs(self, path: Optional[Path], select: Optional[str] = None) -> None:
        rows: list[Row] = []
        if path is None:  # Windows "Bilgisayar" görünümü: sürücüler
            for letter in string.ascii_uppercase:
                d = Path(f"{letter}:\\")
                if d.exists():
                    rows.append(Row(f"{letter}:", True, str(d), kind="drive"))
        else:
            path = path.resolve()
            try:
                with os.scandir(path) as it:
                    for de in it:
                        if de.name.startswith("."):
                            continue
                        try:
                            is_dir = de.is_dir()
                            st = de.stat()
                        except OSError:
                            continue
                        kind = "dir" if is_dir else ("archive" if is_archive_name(de.name)
                                                     else ("link" if de.is_symlink() else "file"))
                        rows.append(Row(de.name, is_dir, de.path, None if is_dir else st.st_size,
                                        mtime=_ts(st.st_mtime), kind=kind))
            except OSError as e:
                self.show_error(e)
                return
        self._close_archive()
        self.fs_dir = path
        self.model.set_rows(rows, archive_mode=False)
        self._after_navigate(select)

    def _close_archive(self) -> None:
        if self.archive is not None:
            self.archive.close()
        self.archive = None
        self.inner = ""

    def set_archive(self, archive: Archive) -> None:
        self._close_archive()
        self.archive = archive
        self.fs_dir = archive.path.parent
        self.build_tree()
        self.navigate_inner("")

    def build_tree(self) -> None:
        tree: dict[str, dict[str, Row]] = {"": {}}

        def ensure_dir(parts: list[str]) -> Row:
            path = "/".join(parts)
            parent = "/".join(parts[:-1])
            if parent not in tree:
                ensure_dir(parts[:-1])
            siblings = tree[parent]
            row = siblings.get(parts[-1])
            if row is None or not row.is_dir:
                row = Row(parts[-1], True, path, 0, 0, kind="dir")
                siblings[parts[-1]] = row
                tree.setdefault(path, {})
            return row

        for e in self.archive.entries():
            parts = ["‥" if p == ".." else p for p in e.name.split("/") if p]
            if not parts:
                continue
            if e.is_dir:
                r = ensure_dir(parts)
                r.mtime = r.mtime or e.mtime
                continue
            parent = "/".join(parts[:-1])
            if parts[:-1]:
                ensure_dir(parts[:-1])
            kind = "archive" if is_archive_name(parts[-1]) else (
                "link" if e.kind in ("symlink", "hardlink") else "file")
            tree[parent][parts[-1]] = Row(parts[-1], False, e.name, e.size, e.packed, e.mtime,
                                          e.crc, e.encrypted, kind)

        def total(path: str) -> tuple[int, Optional[int]]:
            s, p, unknown = 0, 0, False
            for row in tree.get(path, {}).values():
                if row.is_dir:
                    row.size, row.packed = total(row.key)
                if row.packed is None:
                    unknown = True
                s += row.size or 0
                p += row.packed or 0
            return s, None if unknown else p

        total("")
        self.tree = tree

    def navigate_inner(self, inner: str, select: Optional[str] = None) -> None:
        if inner not in self.tree:
            inner = ""
        self.inner = inner
        self.model.set_rows(list(self.tree[inner].values()), archive_mode=True)
        self._after_navigate(select)

    def _after_navigate(self, select: Optional[str]) -> None:
        archive_mode = self.archive is not None
        for i, col in enumerate(COLUMNS):
            self.view.setColumnHidden(i, col in ARCHIVE_ONLY_COLUMNS and not archive_mode)
        if archive_mode:
            shown = str(self.archive.path) + (os.sep + self.inner.replace("/", os.sep)
                                              if self.inner else "")
            self.path_icon.setPixmap(pixmap("archive", 20))
            self.badge.setText(self.archive.format_name)
            self.badge.setVisible(True)
            self.setWindowTitle(f"{self.archive.path.name} — {APP_NAME}")
            self.lock_label.setVisible(any(e.encrypted for e in self.archive.entries()))
        else:
            shown = str(self.fs_dir) if self.fs_dir else ""
            self.path_icon.setPixmap(pixmap("folder", 20))
            self.badge.setVisible(False)
            self.setWindowTitle(APP_NAME)
            self.lock_label.setVisible(False)
            if self.fs_dir:
                self.settings.last_dir = str(self.fs_dir)
        self.path_edit.setText(shown)
        self.a_up.setEnabled(archive_mode or self.fs_dir is not None and (
            self.fs_dir.parent != self.fs_dir or IS_WINDOWS))
        # İmleç konumlanır ama seçim yapılmaz: seçim yoksa "Çıkart" her şeyi çıkartır.
        target = 0
        for i, r in enumerate(self.model.rows):
            if select and r.name == select:
                target = i
                break
        if self.model.rows:
            idx = self.model.index(target, 0)
            self.view.selectionModel().setCurrentIndex(
                idx, QItemSelectionModel.SelectionFlag.NoUpdate)
            self.view.scrollTo(idx)
        self.view.setFocus()
        self.update_status()

    def go_up(self) -> None:
        if self.archive is not None:
            if self.inner:
                parent, _, name = self.inner.rpartition("/")
                self.navigate_inner(parent, select=name)
            else:
                name = self.archive.path.name
                self.navigate_fs(self.archive.path.parent, select=name)
        elif self.fs_dir is not None:
            if self.fs_dir.parent != self.fs_dir:
                self.navigate_fs(self.fs_dir.parent, select=self.fs_dir.name)
            elif IS_WINDOWS:
                self.navigate_fs(None)

    def refresh(self) -> None:
        if self.archive is not None:
            cur = self.inner
            try:
                self.archive.reload()
                self.build_tree()
            except ArchiveError as e:
                self.show_error(e)
                return
            self.navigate_inner(cur)
        else:
            self.navigate_fs(self.fs_dir)

    def selected_rows(self) -> list[Row]:
        idx = self.view.selectionModel().selectedRows()
        return [self.model.rows[i.row()] for i in sorted(idx, key=lambda i: i.row())]

    def current_row(self) -> Optional[Row]:
        sel = self.selected_rows()
        if sel:
            return sel[0]
        idx = self.view.currentIndex()
        return self.model.rows[idx.row()] if idx.isValid() and idx.row() < len(
            self.model.rows) else None

    def update_status(self, *args) -> None:
        rows = self.model.rows
        dirs = sum(1 for r in rows if r.is_dir)
        files = len(rows) - dirs
        total = sum(r.size or 0 for r in rows if self.archive is not None or not r.is_dir)
        text = t("status.items", dirs=dirs, files=files, size=human_size(total))
        sel = self.selected_rows()
        if len(sel) > 1:
            text = t("status.selected", n=len(sel), size=human_size(
                sum(r.size or 0 for r in sel))) + "   |   " + text
        self.status_left.setText(text)
        self._update_actions(sel)

    def _update_actions(self, sel: list[Row]) -> None:
        in_arc = self.archive is not None
        arc_sel = [r for r in sel if r.kind == "archive"]
        self.a_extract.setEnabled(in_arc or bool(arc_sel))
        self.a_extract_here.setEnabled(in_arc or bool(arc_sel))
        self.a_test.setEnabled(in_arc or len(arc_sel) == 1)
        self.a_info.setEnabled(in_arc or len(arc_sel) == 1)
        cur = self.current_row()
        self.a_view.setEnabled(cur is not None and not cur.is_dir)
        self.a_add.setEnabled(not in_arc or self.archive.backend.can_add)
        self.a_delete.setEnabled(bool(sel) and (not in_arc or self.archive.backend.can_delete)
                                 and (in_arc or self.fs_dir is not None))

    # --------------------------------------------------------- görev altyapısı
    def run_task(self, fn, title: str, icon_name: str, on_success, on_error=None,
                 delay_ms: int = 0, ask_overwrite: bool = False) -> None:
        task = Task(fn, self)
        dlg = dialogs.ProgressDialog(self, title, icon_name)
        dlg.on_cancel = task.cancel.cancel
        task.progressed.connect(dlg.update_progress)
        if ask_overwrite:
            connect_ask(task, lambda p: dialogs.ask_overwrite(dlg if dlg.isVisible() else self, p))

        def cleanup() -> None:
            dlg.finish()
            if task in self._tasks:
                self._tasks.remove(task)
            QApplication.restoreOverrideCursor()

        def ok(result) -> None:
            cleanup()
            on_success(result)

        def fail(err) -> None:
            cleanup()
            if on_error is None or not on_error(err):
                self.show_error(err)

        task.succeeded.connect(ok)
        task.failed.connect(fail)
        self._tasks.append(task)
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        task.start()
        if delay_ms:
            QTimer.singleShot(delay_ms, lambda: task.isRunning() and dlg.show())
        else:
            dlg.show()

    def show_error(self, err: BaseException) -> None:
        if isinstance(err, Cancelled):
            self.statusBar().showMessage(t("err.cancelled"), 4000)
            return
        box = QMessageBox(self)
        if isinstance(err, SafetyError):
            box.setWindowTitle(t("set.safety"))
            box.setIconPixmap(pixmap("shield", 48))
            box.setText(f"<b>{err}</b>")
            box.setInformativeText(t("set.title") + " → " + t("set.safety"))
        else:
            box.setWindowTitle(t("dlg.error"))
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText(str(err) or type(err).__name__)
            tb = getattr(err, "__sandik_tb__", None)
            if tb and not isinstance(err, (ArchiveError, OSError)):
                box.setDetailedText(tb)
        box.exec()

    def show_result(self, title: str, text: str, warnings: list[str]) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIconPixmap(pixmap("warning" if warnings else "test", 48))
        box.setText(text)
        if warnings:
            box.setInformativeText(t("res.warnings") + f" ({len(warnings)})")
            box.setDetailedText("\n".join(warnings))
        box.exec()

    # --------------------------------------------------------- arşiv açma
    def open_archive(self, path: Path, then: Optional[Callable[[Archive], None]] = None,
                     password: Optional[str] = None) -> None:
        limits = self.settings.limits

        def work(progress, cancel, ask):
            a = Archive(path, password=password, limits=limits)
            a.entries()
            return a

        def done(a: Archive) -> None:
            if then:
                then(a)
            else:
                self.set_archive(a)

        def failed(err) -> bool:
            if isinstance(err, (PasswordRequired, WrongPassword)):
                if isinstance(err, WrongPassword):
                    self.show_error(err)
                pw = dialogs.ask_password(self, path.name)
                if pw:
                    self.open_archive(path, then, pw)
                return True
            return False

        self.run_task(work, t("prog.opening"), "archive", done, failed, delay_ms=350)

    def ensure_password(self, a: Archive) -> bool:
        if a.needs_password() and not a.password:
            pw = dialogs.ask_password(self, a.path.name)
            if not pw:
                return False
            a.set_password(pw)
            if a is self.archive:
                self.build_tree()
        return True

    # ------------------------------------------------------------- komutlar
    def on_activate(self, index) -> None:
        if not index.isValid():
            return
        row = self.model.rows[index.row()]
        if self.archive is not None:
            if row.is_dir:
                self.navigate_inner(row.key)
            else:
                self.view_archive_file(row)
        elif row.is_dir:
            self.navigate_fs(Path(row.key))
        elif self._looks_like_archive(Path(row.key)):
            self.open_archive(Path(row.key))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(row.key))

    @staticmethod
    def _looks_like_archive(path: Path) -> bool:
        try:
            detect_format(path)
            return True
        except (UnsupportedFormat, OSError):
            return False

    def on_path_entered(self) -> None:
        p = Path(self.path_edit.text().strip()).expanduser()
        if p.is_dir():
            self.navigate_fs(p)
        elif p.is_file() and self._looks_like_archive(p):
            self.open_archive(p)
        else:
            self._after_navigate(None)

    def on_open_dialog(self) -> None:
        patterns = " ".join(f"*{e}" for e in ARCHIVE_EXTENSIONS)
        path, _ = QFileDialog.getOpenFileName(
            self, t("act.open"), str(self.fs_dir or Path.home()),
            f"{t('filter.archives')} ({patterns});;{t('filter.all')} (*)")
        if path:
            self.open_archive(Path(path))

    def on_open_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, t("act.open_folder"),
                                                str(self.fs_dir or Path.home()))
        if path:
            self.navigate_fs(Path(path))

    def on_files_dropped(self, paths: list[Path]) -> None:
        if self.archive is not None:
            if self.archive.backend.can_add:
                self._add_to_archive(paths)
            return
        if len(paths) == 1 and paths[0].is_file() and self._looks_like_archive(paths[0]):
            self.open_archive(paths[0])
        else:
            self._create_archive(paths)

    # Ekle ---------------------------------------------------------------------
    def on_add(self) -> None:
        if self.archive is not None:
            files, _ = QFileDialog.getOpenFileNames(self, t("act.add"),
                                                    str(self.archive.path.parent))
            if files:
                self._add_to_archive([Path(f) for f in files])
            return
        sel = [Path(r.key) for r in self.selected_rows() if r.kind != "drive"]
        if not sel:
            files, _ = QFileDialog.getOpenFileNames(self, t("act.add"),
                                                    str(self.fs_dir or Path.home()))
            sel = [Path(f) for f in files]
        if sel:
            self._create_archive(sel)

    def _create_archive(self, paths: list[Path]) -> None:
        base = paths[0].parent
        stem = paths[0].name if len(paths) == 1 else (base.name or "arsiv")
        if len(paths) == 1 and paths[0].is_file():
            stem = paths[0].stem
        default_dir = self.fs_dir if self.fs_dir and os.access(self.fs_dir, os.W_OK) else base
        dlg = dialogs.AddDialog(self, paths, default_dir / stem, self.settings)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        out: Path = v["out"]
        if out.exists():
            if QMessageBox.question(self, t("dlg.overwrite_title"),
                                    t("dlg.overwrite_text", path=out)) != \
                    QMessageBox.StandardButton.Yes:
                return

        def work(progress, cancel, ask):
            return create_archive(out, paths, v["fmt"], v["level"], v["password"], progress,
                                  cancel)

        def done(result: Path) -> None:
            self.statusBar().showMessage(t("res.created", path=result), 6000)
            if self.archive is None and self.fs_dir == result.parent:
                self.navigate_fs(self.fs_dir, select=result.name)

        self.run_task(work, t("prog.adding"), "add", done)

    def _add_to_archive(self, paths: list[Path]) -> None:
        a = self.archive
        dlg = dialogs.AddDialog(self, paths, a.path, self.settings, fixed_archive=a.path)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        level = dlg.values()["level"]
        inner = self.inner

        def work(progress, cancel, ask):
            a.add(paths, level=level, prefix=inner, progress=progress, cancel=cancel)

        def done(_):
            self.build_tree()
            self.navigate_inner(inner)

        self.run_task(work, t("prog.adding"), "add", done)

    # Çıkart --------------------------------------------------------------------
    def _selected_archive_paths(self) -> list[Path]:
        return [Path(r.key) for r in self.selected_rows() if r.kind == "archive"]

    def on_extract(self, here: bool = False) -> None:
        if self.archive is not None:
            sel = self.selected_rows()
            if sel:
                names = [r.key for r in sel]
            else:  # seçim yoksa: bulunulan klasör ya da tüm arşiv
                names = [self.inner] if self.inner else None
            self._extract_archive(self.archive, names, here)
            return
        queue = self._selected_archive_paths()

        def next_one() -> None:
            if not queue:
                self.refresh()
                return
            path = queue.pop(0)
            self.open_archive(path, then=lambda a: self._extract_archive(
                a, None, here, after=next_one, refresh=False))

        next_one()

    def on_extract_here(self) -> None:
        self.on_extract(here=True)

    def _extract_archive(self, a: Archive, names: Optional[list[str]], here: bool,
                         after: Optional[Callable] = None, refresh: bool = True) -> None:
        if not self.ensure_password(a):
            return
        stem = a.path.name
        for ext in sorted(ARCHIVE_EXTENSIONS, key=len, reverse=True):
            if stem.lower().endswith(ext):
                stem = stem[: -len(ext)]
                break
        default = a.path.parent if here else a.path.parent / (stem or "extracted")
        overwrite = self.settings.overwrite
        if not here:
            dlg = dialogs.ExtractDialog(self, default, overwrite, len(names or []))
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            v = dlg.values()
            default, overwrite = v["dest"], v["overwrite"]
        dest = default

        def work(progress, cancel, ask):
            return a.extract(dest, names, overwrite=overwrite, ask_overwrite=ask,
                             progress=progress, cancel=cancel)

        def done(res: OperationResult) -> None:
            text = t("res.extracted", files=res.files, size=human_size(res.bytes))
            if res.skipped:
                text += "\n" + t("res.skipped", n=res.skipped)
            self.show_result(t("dlg.done"), text, res.warnings)
            if refresh and self.archive is None:
                self.refresh()
            if after:
                after()

        def failed(err) -> bool:
            if isinstance(err, WrongPassword):
                a.set_password(None)
            return False

        self.run_task(work, t("prog.extracting"), "extract", done, failed, ask_overwrite=True)

    # Test / Bilgi / Görüntüle / Sil ----------------------------------------------
    def _with_current_archive(self, fn: Callable[[Archive], None]) -> None:
        if self.archive is not None:
            fn(self.archive)
            return
        paths = self._selected_archive_paths()
        if paths:
            self.open_archive(paths[0], then=fn)

    def on_test(self) -> None:
        def go(a: Archive) -> None:
            if not self.ensure_password(a):
                return

            def done(res: OperationResult) -> None:
                self.show_result(t("dlg.done"), t("res.test_ok", files=res.files,
                                                  size=human_size(res.bytes)), res.warnings)

            def failed(err) -> bool:
                if isinstance(err, WrongPassword):
                    a.set_password(None)
                return False

            self.run_task(lambda p, c, ask: a.test(progress=p, cancel=c), t("prog.testing"),
                          "test", done, failed)

        self._with_current_archive(go)

    def on_info(self) -> None:
        self._with_current_archive(
            lambda a: dialogs.InfoDialog(self, a, a.analyze()).exec())

    def on_view(self) -> None:
        row = self.current_row()
        if row is None or row.is_dir:
            return
        if self.archive is not None:
            self.view_archive_file(row)
        else:
            self.on_activate(self.view.currentIndex())

    def view_archive_file(self, row: Row) -> None:
        a = self.archive
        if not self.ensure_password(a):
            return

        def work(progress, cancel, ask):
            return a.extract_to_temp(row.key, cancel=cancel)

        def done(path: Path) -> None:
            self._temp_dirs.append(path.parent)
            if is_archive_name(path.name):
                self.open_archive(path)  # iç içe arşiv: yalnızca kullanıcı isteyince açılır
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

        self.run_task(work, t("prog.extracting"), "view", done, delay_ms=300)

    def on_delete(self) -> None:
        sel = self.selected_rows()
        if not sel:
            return
        if QMessageBox.question(self, t("act.delete"), t("dlg.confirm_delete", n=len(sel))) != \
                QMessageBox.StandardButton.Yes:
            return
        if self.archive is None:
            for r in sel:  # dosya sisteminde: geri alınabilir şekilde çöpe taşı
                QFile.moveToTrash(r.key)
            self.refresh()
            return
        a = self.archive
        names = [r.key for r in sel]
        inner = self.inner

        def work(progress, cancel, ask):
            return a.delete(names, cancel=cancel)

        def done(n: int) -> None:
            self.build_tree()
            self.navigate_inner(inner)
            self.statusBar().showMessage(t("res.deleted", n=n), 5000)

        self.run_task(work, t("prog.deleting"), "delete", done)

    def on_settings(self) -> None:
        old_lang, old_theme = self.settings.language, self.settings.theme
        dlg = dialogs.SettingsDialog(self, self.settings)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        dlg.apply()
        if self.archive is not None:
            self.archive.limits = self.settings.limits
        self.update_safety_label()
        if self.settings.language != old_lang or self.settings.theme != old_theme:
            self.restart_cb()

    # --------------------------------------------------------- sağ tık menüsü
    def on_context_menu(self, pos) -> None:
        menu = QMenu(self)
        sel = self.selected_rows()
        if sel:
            menu.addAction(self.a_view)
        menu.addSeparator()
        for a in (self.a_extract, self.a_extract_here, self.a_test, self.a_add):
            if a.isEnabled():
                menu.addAction(a)
        menu.addSeparator()
        for a in (self.a_delete, self.a_info):
            if a.isEnabled():
                menu.addAction(a)
        menu.exec(self.view.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------- sürükleme
    def paths_for_drag(self) -> list[Path]:
        sel = self.selected_rows()
        if self.archive is None:
            return [Path(r.key) for r in sel if r.kind != "drive"]
        total = sum(r.size or 0 for r in sel)
        if not sel or total > 512 * MiB or (self.archive.needs_password()
                                            and not self.archive.password):
            return []
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="sandik-drag-"))
        self._temp_dirs.append(tmp)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.archive.extract(tmp, [r.key for r in sel], overwrite="always")
        except ArchiveError as e:
            QApplication.restoreOverrideCursor()
            self.show_error(e)
            return []
        QApplication.restoreOverrideCursor()
        base = tmp.joinpath(*self.inner.split("/")) if self.inner else tmp
        return [base / r.name for r in sel if (base / r.name).exists()]

    # ------------------------------------------------------------------ kapanış
    def closeEvent(self, e) -> None:
        for task in list(self._tasks):
            task.cancel.cancel()
            task.wait(3000)
        for d in self._temp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        self.settings.window = [self.width(), self.height()]
        self.settings.save()
        super().closeEvent(e)


def _ts(ts: float) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(ts)
    except (OverflowError, OSError, ValueError):
        return None
