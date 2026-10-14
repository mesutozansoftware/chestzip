"""ChestZip'ın üst düzey API'si. Arayüz ve komut satırı yalnızca bunu kullanır."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .backends import (CREATE_FORMATS, ENCRYPTABLE, Entry, collect_sources, detect_format,
                       open_backend)
from .backends.base import Backend, Source
from .errors import (ArchiveError, PasswordRequired, SafetyError, UnsupportedOperation)
from .i18n import t
from .safety import (AskOverwriteFn, CancelToken, ExtractContext, Limits, ProgressFn,
                     SecurityReport, analyze_entries)


@dataclass
class OperationResult:
    files: int = 0
    bytes: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    dest: Optional[Path] = None


class Archive:
    """Açılmış bir arşiv."""

    def __init__(self, path: str | Path, password: Optional[str] = None,
                 limits: Optional[Limits] = None) -> None:
        self.path = Path(path).resolve()
        self.limits = limits or Limits()
        self.format = detect_format(self.path)
        self.password = password
        self.backend: Backend = open_backend(self.path, password, self.limits, self.format)
        self._entries: Optional[list[Entry]] = None

    # -- bilgi ----------------------------------------------------------------
    @property
    def format_name(self) -> str:
        return self.backend.format_name

    @property
    def size(self) -> int:
        return self.path.stat().st_size

    def set_password(self, password: Optional[str]) -> None:
        self.password = password
        self.backend = open_backend(self.path, password, self.limits, self.format)
        self._entries = None

    def needs_password(self) -> bool:
        return self.backend.needs_password()

    def entries(self) -> list[Entry]:
        if self._entries is None:
            self._entries = self.backend.entries()
        return self._entries

    def reload(self) -> None:
        self.backend = open_backend(self.path, self.password, self.limits, self.format)
        self._entries = None

    def analyze(self, dest: Optional[str | Path] = None,
                names: Optional[set[str]] = None) -> SecurityReport:
        entries = [e for e in self.entries() if names is None or e.name in names]
        report = analyze_entries(entries, self.size, self.limits, str(dest) if dest else None)
        report.problems[:0] = self.backend.security_problems()
        nested = sum(1 for e in entries if not e.is_dir and e.name.lower().endswith(
            (".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".tgz")))
        if nested:
            report.warnings.append(t("sec.nested", n=nested))
        return report

    def expand(self, names: Optional[Iterable[str]]) -> Optional[set[str]]:
        """Seçilen klasörleri içindeki tüm kayıtlarla birlikte genişletir."""
        if names is None:
            return None
        sel = {n.strip("/") for n in names}
        out = set()
        for e in self.entries():
            if e.name in sel or any(e.name.startswith(s + "/") for s in sel):
                out.add(e.name)
        return out

    # -- işlemler -------------------------------------------------------------
    def extract(self, dest: str | Path, members: Optional[Iterable[str]] = None,
                overwrite: str = "ask", ask_overwrite: Optional[AskOverwriteFn] = None,
                progress: Optional[ProgressFn] = None,
                cancel: Optional[CancelToken] = None) -> OperationResult:
        names = self.expand(members)
        self._precheck(names, dest)
        sel = [e for e in self.entries() if names is None or e.name in names]
        ctx = ExtractContext(dest, self.limits, self.size, overwrite, ask_overwrite, progress,
                             cancel, progress_total=sum(e.size for e in sel))
        self.backend.extract(ctx, names)
        return OperationResult(ctx.files, ctx.written, ctx.skipped, ctx.warnings, ctx.dest)

    def test(self, progress: Optional[ProgressFn] = None,
             cancel: Optional[CancelToken] = None) -> OperationResult:
        """Tüm veriyi diske yazmadan açar; CRC ve bütünlük hatalarını bulur."""
        self._precheck(None, None)
        ctx = ExtractContext(None, self.limits, self.size, "always", None, progress, cancel,
                             dry_run=True, progress_total=sum(e.size for e in self.entries()))
        self.backend.extract(ctx, None)
        return OperationResult(ctx.files, ctx.written, ctx.skipped, ctx.warnings)

    def extract_to_temp(self, name: str, cancel: Optional[CancelToken] = None) -> Path:
        """Tek bir dosyayı görüntülemek için geçici klasöre çıkartır."""
        tmp = Path(tempfile.mkdtemp(prefix="chestzip-view-"))
        self.extract(tmp, [name], overwrite="always", cancel=cancel)
        for root, _dirs, files in os.walk(tmp):
            for f in files:
                return Path(root) / f
        raise ArchiveError(t("err.corrupt", detail=name))

    def delete(self, members: Iterable[str], cancel: Optional[CancelToken] = None) -> int:
        if not self.backend.can_delete:
            raise UnsupportedOperation(t("err.no_delete", fmt=self.format_name))
        names = self.expand(members) or set()
        self.backend.delete(names, cancel)
        self.reload()
        return len(names)

    def add(self, paths: Iterable[str | Path], level: int = 5, prefix: str = "",
            progress: Optional[ProgressFn] = None, cancel: Optional[CancelToken] = None) -> None:
        if not self.backend.can_add:
            raise UnsupportedOperation(t("err.no_add", fmt=self.format_name))
        sources = collect_sources(paths)
        if prefix:
            prefix = prefix.strip("/")
            sources = [Source(s.path, f"{prefix}/{s.arcname}", s.is_dir, s.size)
                       for s in sources]
        self.backend.add(sources, level, progress, cancel)
        self.reload()

    def _precheck(self, names, dest) -> None:
        if self.needs_password() and not self.password:
            raise PasswordRequired(t("err.password_required"))
        report = self.analyze(dest, names)
        if report.problems:
            raise SafetyError(report.problems[0])

    def close(self) -> None:
        self.backend.close()

    def __enter__(self) -> "Archive":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def create_archive(out_path: str | Path, paths: Iterable[str | Path], fmt: Optional[str] = None,
                   level: int = 5, password: Optional[str] = None,
                   progress: Optional[ProgressFn] = None,
                   cancel: Optional[CancelToken] = None) -> Path:
    """Yeni bir arşiv oluşturur. Hata/iptal olursa yarım dosya bırakmaz."""
    from .backends import format_for_filename
    out_path = Path(out_path)
    fmt = fmt or format_for_filename(out_path.name) or "chz"
    if fmt == "rar":
        raise UnsupportedOperation(t("err.rar_create"))
    if fmt not in CREATE_FORMATS:
        raise UnsupportedOperation(t("err.unknown_format", path=out_path))
    if password and fmt not in ENCRYPTABLE:
        raise UnsupportedOperation(t("err.no_password_support", fmt=fmt.upper()))
    sources = collect_sources(paths)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".chestzip-", suffix=".part", dir=out_path.parent)
    os.close(fd)
    os.unlink(tmp)
    try:
        if fmt == "chz":
            from .backends.chz_backend import create_chz
            create_chz(tmp, sources, level, password, progress, cancel)
        elif fmt == "zip":
            from .backends.zip_backend import create_zip
            create_zip(tmp, sources, level, password, progress, cancel)
        elif fmt == "7z":
            from .backends.sevenzip_backend import create_7z
            create_7z(tmp, sources, level, password, progress, cancel)
        elif fmt == "tar" or fmt.startswith("tar."):
            from .backends.tar_backend import create_tar
            comp = fmt.split(".", 1)[1] if "." in fmt else None
            create_tar(tmp, sources, comp, level, progress, cancel)
        else:
            from .backends.tar_backend import create_stream
            create_stream(tmp, sources, fmt, level, progress, cancel)
        os.replace(tmp, out_path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return out_path
