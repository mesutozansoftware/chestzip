"""7z desteği (py7zr, LGPL). AES-256 şifreleme ve başlık şifreleme dahil."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from ..errors import ArchiveError, PasswordRequired, WrongPassword
from ..i18n import t
from ..safety import ExtractContext, is_within
from .base import AddProgress, Backend, Entry, Source, make_entry

try:
    import py7zr
    from py7zr.io import Py7zIO, WriterFactory
except ImportError:  # pragma: no cover
    py7zr = None
    Py7zIO = WriterFactory = object


def _map_error(e: Exception, encrypted: bool = False) -> Exception:
    if isinstance(e, ArchiveError):  # SafetyError, Cancelled ... olduğu gibi
        return e
    name = type(e).__name__
    msg = str(e).lower()
    if name == "PasswordRequired" or ("password" in msg and "required" in msg):
        return PasswordRequired(t("err.password_required"))
    if "password" in msg or name == "CrcError" or encrypted:
        return WrongPassword(t("err.wrong_password"))
    return ArchiveError(t("err.corrupt", detail=e))


class _Writer(Py7zIO):
    """py7zr'nin her dosya için çağırdığı yazıcı; veriyi ExtractContext'e aktarır."""

    def __init__(self, out) -> None:
        self.out = out
        self._size = 0

    def write(self, s) -> int:
        if self.out is not None:
            self.out.write(s)
        self._size += len(s)
        return len(s)

    def read(self, size=None) -> bytes:
        return b""

    def seek(self, offset, whence=0) -> int:
        return 0

    def flush(self) -> None:
        pass

    def size(self) -> int:
        return self._size

    def close(self) -> None:
        pass


class _Factory(WriterFactory):
    def __init__(self, ctx: ExtractContext, root: Path, by_name: dict[str, Entry]) -> None:
        self.ctx = ctx
        self.root = root
        self.by_name = by_name
        self.open: list = []

    def create(self, filename: str):
        ctx = self.ctx
        p = Path(filename)
        rel = p.relative_to(self.root).as_posix() if is_within(p, self.root) else filename
        entry = self.by_name.get(rel)
        raw = entry.raw_name if entry else rel
        ctx.begin_entry(entry.name if entry else rel)
        out = ctx.open_file(raw, packed=None, mtime=entry.timestamp if entry else None,
                            mode=entry.mode if entry else None)
        if out is not None:
            self.open.append(out)
        return _Writer(out)


def _local(dt):
    """UTC zaman damgasını yerel saate çevirir (görüntüleme için)."""
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


class SevenZipBackend(Backend):
    format_name = "7Z"
    can_add = True
    can_delete = False
    can_encrypt = True

    def __init__(self, path, password=None) -> None:
        super().__init__(path, password)
        self._entries: Optional[list[Entry]] = None
        self._needs_password: Optional[bool] = None

    def _open(self, fileobj=None):
        try:
            return py7zr.SevenZipFile(fileobj or self.path, "r", password=self.password)
        except Exception as e:  # py7zr pek çok farklı tip fırlatabiliyor
            raise _map_error(e, bool(self.password)) from e

    def needs_password(self) -> bool:
        if self._needs_password is None:
            try:
                with py7zr.SevenZipFile(self.path, "r") as z:
                    self._needs_password = bool(z.needs_password())
            except Exception as e:
                if type(e).__name__ == "PasswordRequired" or "password" in str(e).lower():
                    self._needs_password = True  # başlık şifreli
                else:
                    raise _map_error(e) from e
        return self._needs_password

    def entries(self) -> list[Entry]:
        if self._entries is None:
            if self.needs_password() and not self.password:
                try:  # yalnızca veri şifreliyse liste yine okunabilir
                    with py7zr.SevenZipFile(self.path, "r") as z:
                        infos = z.list()
                except Exception as e:
                    raise PasswordRequired(t("err.password_required")) from e
            else:
                with self._open() as z:
                    infos = z.list()
            encrypted = bool(self._needs_password)
            out = []
            for i in infos:
                kind = "dir" if i.is_directory else ("symlink" if i.is_symlink else "file")
                out.append(make_entry(
                    # Solid 7z'de sıkışık boyut dosya başına bilinemez (blok toplamıdır).
                    i.filename, is_dir=i.is_directory, size=i.uncompressed or 0,
                    packed=None, mtime=_local(i.creationtime), crc=i.crc32,
                    encrypted=encrypted, kind=kind))
            self._entries = out
        return self._entries

    def extract(self, ctx: ExtractContext, names=None) -> None:
        entries = self.entries()
        by_name = {make_entry(e.raw_name).name: e for e in entries}
        targets: list[str] = []
        for e in entries:
            if names is not None and e.name not in names:
                continue
            if e.kind == "dir":
                ctx.begin_entry(e.name)
                ctx.make_dir(e.raw_name, e.timestamp)
            elif e.kind == "symlink":
                ctx.begin_entry(e.name)
                ctx.warn(t("sec.link_skipped", name=e.name, target="?"))
                ctx.skipped += 1
            else:
                targets.append(e.raw_name)
        ctx.progress_total = sum(by_name[make_entry(n).name].size for n in targets)
        if targets:
            # py7zr yolları kendi kökü altına yerleştirir; sanal bir kök kullanıp
            # gerçek hedefi ExtractContext belirler.
            root = Path(os.path.realpath(tempfile.mkdtemp(prefix="sandik-7z-")))
            factory = _Factory(ctx, root, by_name)
            with open(self.path, "rb") as fp:  # dosya nesnesi -> tek iş parçacığı
                z = self._open(fp)
                try:
                    z.extract(path=root, targets=targets, factory=factory)
                except Exception as e:
                    for out in factory.open:
                        out.discard()
                    raise _map_error(e, bool(self.password)) from e
                finally:
                    z.close()
                    _rmdir_quiet(root)
            for out in factory.open:
                out.commit()
        ctx.finish()

    def add(self, sources: list[Source], level=5, progress=None, cancel=None) -> None:
        existing = {e.name for e in self.entries()}
        if {s.arcname for s in sources} & existing:
            from ..errors import UnsupportedOperation
            raise UnsupportedOperation(t("err.no_delete", fmt="7Z"))
        with py7zr.SevenZipFile(self.path, "a", password=self.password) as z:
            _write_sources(z, sources, progress, cancel)
        self._entries = None


def _rmdir_quiet(root: Path) -> None:
    # Sanal kök boş kalmalı; yalnızca boşsa kaldırılır.
    try:
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            if filenames:
                return
            os.rmdir(dirpath)
    except OSError:
        pass


def _write_sources(z, sources: list[Source], progress, cancel) -> None:
    tracker = AddProgress(sources, progress)
    for s in sources:
        if cancel:
            cancel.check()
        tracker.start(s.arcname)
        if s.is_dir:
            z.write(s.path, s.arcname)
        else:
            z.write(s.path, s.arcname)
            tracker(s.size)


def create_7z(out_path, sources: list[Source], level=5, password=None, progress=None,
              cancel=None) -> None:
    filters = [{"id": py7zr.FILTER_LZMA2, "preset": min(max(level, 0), 9)}]
    if password:
        filters.append({"id": py7zr.FILTER_CRYPTO_AES256_SHA256})
    if level == 0:
        filters = [{"id": py7zr.FILTER_COPY}] + filters[1:]
    with py7zr.SevenZipFile(out_path, "w", password=password, filters=filters,
                            header_encryption=bool(password)) as z:
        _write_sources(z, sources, progress, cancel)
