"""Diyalog pencereleri."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..backends import CREATE_FORMATS, ENCRYPTABLE
from ..i18n import t
from ..safety import GiB, MiB, Limits, SecurityReport, human_size
from ..settings import Settings
from .icons import icon, pixmap

LEVELS = [0, 1, 3, 5, 7, 9]
FORMAT_LABELS = {
    "chz": "CHZ (ChestZip)", "zip": "ZIP", "7z": "7Z", "tar": "TAR", "tar.gz": "TAR.GZ", "tar.bz2": "TAR.BZ2",
    "tar.xz": "TAR.XZ", "gz": "GZ", "bz2": "BZ2", "xz": "XZ",
}


def _header(title: str, icon_name: str, subtitle: str = "") -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 6)
    pic = QLabel()
    pic.setPixmap(pixmap(icon_name, 40))
    lay.addWidget(pic)
    col = QVBoxLayout()
    lbl = QLabel(f"<b style='font-size:15px'>{title}</b>")
    col.addWidget(lbl)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        col.addWidget(sub)
    lay.addLayout(col, 1)
    return w


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                           QDialogButtonBox.StandardButton.Cancel)
    box.button(QDialogButtonBox.StandardButton.Ok).setText(t("btn.ok"))
    box.button(QDialogButtonBox.StandardButton.Cancel).setText(t("btn.cancel"))
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


# --------------------------------------------------------------------------

class AddDialog(QDialog):
    """Arşiv oluşturma seçenekleri."""

    def __init__(self, parent, files: list[Path], default_out: Path, settings: Settings,
                 fixed_archive: Optional[Path] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("add.title"))
        self.setMinimumWidth(520)
        self.files = files
        lay = QVBoxLayout(self)
        lay.addWidget(_header(t("add.title"), "add", t("add.files", n=len(files))))

        form = QFormLayout()
        row = QHBoxLayout()
        self.name = QLineEdit(str(default_out))
        browse = QPushButton(t("btn.browse"))
        browse.clicked.connect(self._browse)
        row.addWidget(self.name, 1)
        row.addWidget(browse)
        form.addRow(t("add.name"), row)

        self.fmt = QComboBox()
        single = len(files) == 1 and files[0].is_file()
        for key, label in FORMAT_LABELS.items():
            if key in ("gz", "bz2", "xz") and not single:
                continue
            self.fmt.addItem(label, key)
        idx = self.fmt.findData(settings.default_format)
        self.fmt.setCurrentIndex(max(idx, 0))
        self.fmt.currentIndexChanged.connect(self._format_changed)
        form.addRow(t("add.format"), self.fmt)

        self.level = QComboBox()
        for lv in LEVELS:
            self.level.addItem(t(f"level.{lv}"), lv)
        self.level.setCurrentIndex(max(self.level.findData(settings.default_level), 0))
        form.addRow(t("add.level"), self.level)

        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        show = QCheckBox(t("dlg.show_password"))
        show.toggled.connect(lambda on: [w.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password)
            for w in (self.pw, self.pw2)])
        form.addRow(t("add.password"), self.pw)
        form.addRow(t("add.password2"), self.pw2)
        form.addRow("", show)
        self.enc_note = QLabel(t("add.encrypt_note"))
        self.enc_note.setObjectName("muted")
        form.addRow("", self.enc_note)
        lay.addLayout(form)
        lay.addWidget(_buttons(self))

        if fixed_archive is not None:  # var olan arşive ekleme
            self.name.setText(str(fixed_archive))
            self.name.setEnabled(False)
            browse.setEnabled(False)
            self.fmt.setEnabled(False)
            for w in (self.pw, self.pw2, show, self.enc_note):
                w.setVisible(False)
                form.labelForField(w) and form.labelForField(w).setVisible(False)
        self._format_changed()

    def _format_changed(self) -> None:
        key = self.fmt.currentData()
        enc = key in ENCRYPTABLE
        for w in (self.pw, self.pw2):
            w.setEnabled(enc)
            if not enc:
                w.clear()
        if self.name.isEnabled():
            text = self.name.text()
            for ext in sorted(CREATE_FORMATS.values(), key=len, reverse=True):
                if text.lower().endswith(ext):
                    text = text[: -len(ext)]
                    break
            self.name.setText(text + CREATE_FORMATS[key])

    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, t("add.title"), self.name.text())
        if path:
            self.name.setText(path)
            self._format_changed()

    def accept(self) -> None:
        if self.pw.text() != self.pw2.text():
            QMessageBox.warning(self, t("dlg.warning"), t("add.mismatch"))
            return
        super().accept()

    def values(self) -> dict:
        return {"out": Path(self.name.text()).expanduser(), "fmt": self.fmt.currentData(),
                "level": self.level.currentData(), "password": self.pw.text() or None}


class ExtractDialog(QDialog):
    def __init__(self, parent, default_dest: Path, overwrite: str,
                 selected: int = 0) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("ext.title"))
        self.setMinimumWidth(540)
        lay = QVBoxLayout(self)
        sub = t("ext.selected_only", n=selected) if selected else ""
        lay.addWidget(_header(t("ext.title"), "extract", sub))
        form = QFormLayout()
        row = QHBoxLayout()
        self.dest = QLineEdit(str(default_dest))
        browse = QPushButton(t("btn.browse"))
        browse.clicked.connect(self._browse)
        row.addWidget(self.dest, 1)
        row.addWidget(browse)
        form.addRow(t("ext.dest"), row)
        self.ow = QComboBox()
        for key in ("ask", "always", "never", "rename"):
            self.ow.addItem(t(f"ext.ow.{key}"), key)
        self.ow.setCurrentIndex(max(self.ow.findData(overwrite), 0))
        form.addRow(t("ext.overwrite"), self.ow)
        lay.addLayout(form)
        lay.addWidget(_buttons(self))

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, t("ext.dest"), self.dest.text())
        if path:
            self.dest.setText(path)

    def values(self) -> dict:
        return {"dest": Path(self.dest.text()).expanduser(), "overwrite": self.ow.currentData()}


def ask_password(parent, name: str) -> Optional[str]:
    dlg = QDialog(parent)
    dlg.setWindowTitle(t("dlg.password"))
    lay = QVBoxLayout(dlg)
    lay.addWidget(_header(t("dlg.password"), "lock", t("dlg.password_for", name=name)))
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    lay.addWidget(edit)
    show = QCheckBox(t("dlg.show_password"))
    show.toggled.connect(lambda on: edit.setEchoMode(
        QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
    lay.addWidget(show)
    lay.addWidget(_buttons(dlg))
    dlg.setMinimumWidth(380)
    if dlg.exec() == QDialog.DialogCode.Accepted and edit.text():
        return edit.text()
    return None


def ask_overwrite(parent, path: str) -> str:
    box = QMessageBox(parent)
    box.setWindowTitle(t("dlg.overwrite_title"))
    box.setIconPixmap(pixmap("warning", 40))
    box.setText(t("dlg.overwrite_text", path=path))
    buttons = {}
    for key, role in (("yes", QMessageBox.ButtonRole.YesRole),
                      ("all", QMessageBox.ButtonRole.YesRole),
                      ("no", QMessageBox.ButtonRole.NoRole),
                      ("none", QMessageBox.ButtonRole.NoRole),
                      ("rename", QMessageBox.ButtonRole.ActionRole),
                      ("cancel", QMessageBox.ButtonRole.RejectRole)):
        label = {"yes": "btn.yes", "all": "btn.yes_all", "no": "btn.no", "none": "btn.no_all",
                 "rename": "btn.rename", "cancel": "btn.cancel"}[key]
        buttons[box.addButton(t(label), role)] = key
    box.exec()
    return buttons.get(box.clickedButton(), "cancel")


class ProgressDialog(QDialog):
    """İlerleme çubuğu, hız ve iptal düğmesi."""

    def __init__(self, parent, title: str, icon_name: str = "app") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        lay = QVBoxLayout(self)
        lay.addWidget(_header(title, icon_name))
        self.name = QLabel(" ")
        self.name.setObjectName("muted")
        self.name.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.stats = QLabel(" ")
        self.stats.setObjectName("muted")
        lay.addWidget(self.name)
        lay.addWidget(self.bar)
        lay.addWidget(self.stats)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = QPushButton(t("btn.cancel"))
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self._start = time.monotonic()
        self.on_cancel = None
        self.cancel_btn.clicked.connect(self._cancel)

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        if self.on_cancel:
            self.on_cancel()

    def reject(self) -> None:  # Esc veya pencere kapatma = iptal
        self._cancel()

    def update_progress(self, done: int, total: int, name: str) -> None:
        metrics = self.name.fontMetrics()
        self.name.setText(metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, 440))
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, int(done * 1000 / total)))
        elapsed = max(time.monotonic() - self._start, 0.001)
        speed = done / elapsed
        text = f"{human_size(done)}"
        if total:
            text += f" / {human_size(total)}"
            if speed > 0 and done < total:
                text += f"  •  ~{int((total - done) / speed)} s"
        text += f"  •  {human_size(speed)}/s"
        self.stats.setText(text)

    def finish(self) -> None:
        self.done(0)


class SettingsDialog(QDialog):
    def __init__(self, parent, settings: Settings) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(t("set.title"))
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # Genel
        gen = QWidget()
        f = QFormLayout(gen)
        self.lang = QComboBox()
        self.lang.addItem("Türkçe", "tr")
        self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(max(self.lang.findData(settings.language), 0))
        f.addRow(t("act.language") + ":", self.lang)
        self.theme = QComboBox()
        self.theme.addItem(t("theme.light"), "light")
        self.theme.addItem(t("theme.dark"), "dark")
        self.theme.setCurrentIndex(max(self.theme.findData(settings.theme), 0))
        f.addRow(t("act.theme") + ":", self.theme)
        self.fmt = QComboBox()
        for key in ("chz", "zip", "7z", "tar", "tar.gz", "tar.bz2", "tar.xz"):
            self.fmt.addItem(FORMAT_LABELS[key], key)
        self.fmt.setCurrentIndex(max(self.fmt.findData(settings.default_format), 0))
        f.addRow(t("add.format"), self.fmt)
        self.level = QComboBox()
        for lv in LEVELS:
            self.level.addItem(t(f"level.{lv}"), lv)
        self.level.setCurrentIndex(max(self.level.findData(settings.default_level), 0))
        f.addRow(t("add.level"), self.level)
        self.ow = QComboBox()
        for key in ("ask", "always", "never", "rename"):
            self.ow.addItem(t(f"ext.ow.{key}"), key)
        self.ow.setCurrentIndex(max(self.ow.findData(settings.overwrite), 0))
        f.addRow(t("ext.overwrite"), self.ow)
        note = QLabel(t("set.restart"))
        note.setObjectName("muted")
        f.addRow("", note)
        tabs.addTab(gen, icon("settings"), t("set.general"))

        # Güvenlik
        sec = QWidget()
        v = QVBoxLayout(sec)
        lim = settings.limits
        self.enabled = QCheckBox(t("set.enabled"))
        self.enabled.setChecked(lim.enabled)
        v.addWidget(self.enabled)
        box = QGroupBox(t("set.safety"))
        g = QFormLayout(box)
        self.max_total = QDoubleSpinBox()
        self.max_total.setRange(0.1, 100000)
        self.max_total.setDecimals(1)
        self.max_total.setValue(lim.max_total_size / GiB)
        self.max_entries = QSpinBox()
        self.max_entries.setRange(10, 100_000_000)
        self.max_entries.setValue(lim.max_entries)
        self.max_ratio = QDoubleSpinBox()
        self.max_ratio.setRange(2, 1_000_000)
        self.max_ratio.setDecimals(0)
        self.max_ratio.setValue(lim.max_ratio)
        self.grace = QSpinBox()
        self.grace.setRange(1, 1_000_000)
        self.grace.setValue(lim.ratio_grace // MiB)
        self.reserve = QSpinBox()
        self.reserve.setRange(0, 10_000_000)
        self.reserve.setValue(lim.disk_reserve // MiB)
        g.addRow(t("set.max_total"), self.max_total)
        g.addRow(t("set.max_entries"), self.max_entries)
        g.addRow(t("set.max_ratio"), self.max_ratio)
        g.addRow(t("set.ratio_grace"), self.grace)
        g.addRow(t("set.disk_reserve"), self.reserve)
        v.addWidget(box)
        self.symlinks = QCheckBox(t("set.allow_symlinks"))
        self.symlinks.setChecked(lim.allow_symlinks)
        v.addWidget(self.symlinks)
        note = QLabel(t("set.note"))
        note.setObjectName("okBox")
        note.setWordWrap(True)
        v.addWidget(note)
        reset = QPushButton(t("btn.reset"))
        reset.clicked.connect(self._reset)
        v.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)
        v.addStretch(1)
        self.enabled.toggled.connect(box.setEnabled)
        box.setEnabled(lim.enabled)
        tabs.addTab(sec, icon("shield"), t("set.safety"))
        lay.addWidget(_buttons(self))

    def _reset(self) -> None:
        d = Limits()
        self.enabled.setChecked(d.enabled)
        self.max_total.setValue(d.max_total_size / GiB)
        self.max_entries.setValue(d.max_entries)
        self.max_ratio.setValue(d.max_ratio)
        self.grace.setValue(d.ratio_grace // MiB)
        self.reserve.setValue(d.disk_reserve // MiB)
        self.symlinks.setChecked(d.allow_symlinks)

    def apply(self) -> None:
        s = self.settings
        s.language = self.lang.currentData()
        s.theme = self.theme.currentData()
        s.default_format = self.fmt.currentData()
        s.default_level = self.level.currentData()
        s.overwrite = self.ow.currentData()
        s.limits = Limits(
            enabled=self.enabled.isChecked(),
            max_total_size=int(self.max_total.value() * GiB),
            max_entries=self.max_entries.value(),
            max_ratio=float(self.max_ratio.value()),
            ratio_grace=self.grace.value() * MiB,
            disk_reserve=self.reserve.value() * MiB,
            allow_symlinks=self.symlinks.isChecked(),
        )
        s.save()


class InfoDialog(QDialog):
    def __init__(self, parent, archive, report: SecurityReport) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("info.title"))
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        lay.addWidget(_header(archive.path.name, "archive", t("type.archive",
                                                              fmt=archive.format_name)))
        form = QFormLayout()
        size = archive.size
        ratio = f"{report.total_size / size:.2f} : 1" if size and report.total_size else "—"
        enc = any(e.encrypted for e in archive.entries())
        rows = [
            (t("info.format"), archive.format_name),
            (t("info.path"), str(archive.path.parent)),
            (t("info.size"), f"{human_size(size)} ({size:,} B)"),
            (t("info.unpacked"), f"{human_size(report.total_size)} ({report.total_size:,} B)"),
            (t("info.entries"), f"{report.entry_count:,}"),
            (t("info.ratio"), ratio),
            (t("info.encrypted"), t("btn.yes") if enc else t("btn.no")),
        ]
        for k, v in rows:
            val = QLabel(v)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(f"<b>{k}</b>", val)
        lay.addLayout(form)
        title = QLabel(f"<b>{t('info.security')}</b>")
        lay.addWidget(title)
        if report.problems:
            box = QLabel("\n".join("✖ " + p for p in report.problems))
            box.setObjectName("dangerBox")
        elif report.warnings:
            box = QLabel("\n".join("• " + w for w in report.warnings))
            box.setObjectName("warnBox")
        else:
            box = QLabel(t("info.secure"))
            box.setObjectName("okBox")
        box.setWordWrap(True)
        lay.addWidget(box)
        if report.problems and report.warnings:
            w = QLabel("\n".join("• " + w for w in report.warnings))
            w.setObjectName("warnBox")
            w.setWordWrap(True)
            lay.addWidget(w)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(t("btn.ok"))
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)


def show_about(parent) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(t("act.about"))
    box.setIconPixmap(pixmap("app", 96))
    box.setText(t("about.text", app=APP_NAME, ver=__version__, tag=t("app.tagline")))
    box.exec()
