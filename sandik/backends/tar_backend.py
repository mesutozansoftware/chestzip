"""TAR, TAR.GZ, TAR.BZ2, TAR.XZ ve tek dosyalık GZ/BZ2/XZ desteği.

Sıkıştırılmış akışlar Sandık tarafından açılır ve her bayt StreamGuard'dan
geçer; böylece başlığında boyut bilgisi bulunmayan biçimlerde de zip bombası
tespit edilir.
"""

from __future__ import annotations

import bz2
import gzip
import lzma
import os
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..errors import ArchiveError, UnsupportedOperation
from ..i18n import t
from ..safety import (CHUNK, CancelToken, ExtractContext, GuardedReader, Limits,
                      ProgressFn, StreamGuard)
from .base import AddProgress, Backend, Entry, ProgressReader, Source, make_entry

COMPRESSORS = {
    "gz": (b"\x1f\x8b", gzip.GzipFile),
    "bz2": (b"BZh", bz2.BZ2File),
    "xz": (b"\xfd7zXZ\x00", lzma.LZMAFile),
}


def sniff_compression(head: bytes) -> Optional[str]:
    for name, (magic, _cls) in COMPRESSORS.items():
        if head.startswith(magic):
            return name
    return None


def open_decompressed(raw, comp: Optional[str]):
    if comp is None:
        return raw
    cls = COMPRESSORS[comp][1]
    return cls(fileobj=raw) if comp == "gz" else cls(raw)


def _mtime(ts) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(ts)
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def _kind(ti: tarfile.TarInfo) -> str:
    if ti.isdir():
        return "dir"
    if ti.issym():
        return "symlink"
    if ti.islnk():
        return "hardlink"
    if ti.isfile():
        return "file"
    return "special"


class _Stream:
    """Tar dosyasını sıralı (stream) modda, korumalı olarak açar."""

    def __init__(self, path: Path, comp: Optional[str], limits: Limits,
                 cancel: Optional[CancelToken]) -> None:
        self.raw = open(path, "rb")
        try:
            self.guard = StreamGuard(limits, path.stat().st_size, cancel)
            self.reader = GuardedReader(open_decompressed(self.raw, comp), self.guard)
            self.tar = tarfile.open(fileobj=self.reader, mode="r|")
        except (tarfile.TarError, OSError, EOFError, lzma.LZMAError) as e:
            self.raw.close()
            raise ArchiveError(t("err.corrupt", detail=e)) from e

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.tar.close()
        finally:
            self.raw.close()


class TarBackend(Backend):
    can_delete = True
    can_add = True

    def __init__(self, path, password=None, comp: Optional[str] = None,
                 limits: Optional[Limits] = None) -> None:
        super().__init__(path, password)
        self.comp = comp
        self.limits = limits or Limits()
        self.format_name = "TAR" + (f".{comp.upper()}" if comp else "")
        self._entries: Optional[list[Entry]] = None

    def entries(self, cancel: Optional[CancelToken] = None) -> list[Entry]:
        if self._entries is None:
            out = []
            with _Stream(self.path, self.comp, self.limits, cancel) as s:
                try:
                    for ti in s.tar:
                        out.append(make_entry(
                            ti.name, is_dir=ti.isdir(), size=ti.size if ti.isfile() else 0,
                            packed=None, mtime=_mtime(ti.mtime), kind=_kind(ti),
                            link_target=ti.linkname or None, mode=ti.mode))
                        if self.limits.enabled and len(out) > self.limits.max_entries:
                            break  # analiz bunu sorun olarak raporlar
                except (tarfile.TarError, EOFError, OSError, lzma.LZMAError) as e:
                    if not out:
                        raise ArchiveError(t("err.corrupt", detail=e)) from e
            self._entries = out
        return self._entries

    def needs_password(self) -> bool:
        return False

    def extract(self, ctx: ExtractContext, names=None) -> None:
        with _Stream(self.path, self.comp, ctx.limits, ctx.cancel) as s:
            ctx.progress_total = self.path.stat().st_size
            ctx.progress_source = s.raw.tell
            extracted: dict[str, Path] = {}
            try:
                for ti in s.tar:
                    e_name = make_entry(ti.name).name
                    if names is not None and e_name not in names:
                        continue
                    ctx.begin_entry(e_name)
                    if ti.isdir():
                        ctx.make_dir(ti.name, ti.mtime)
                    elif ti.isfile():
                        out = ctx.open_file(ti.name, packed=None, mtime=ti.mtime, mode=ti.mode)
                        if out is None:
                            continue
                        with out:
                            src = s.tar.extractfile(ti)
                            out.copy_from(src)
                        if out.target is not None:
                            extracted[e_name] = out.target
                    elif ti.issym():
                        ctx.make_symlink(ti.name, ti.linkname)
                    elif ti.islnk():
                        # Sabit bağlantı: daha önce çıkartılmış dosyanın kopyası olarak yazılır.
                        src_path = extracted.get(make_entry(ti.linkname).name)
                        if src_path is None or not src_path.exists():
                            ctx.warn(t("sec.link_skipped", name=ti.name, target=ti.linkname))
                            ctx.skipped += 1
                            continue
                        out = ctx.open_file(ti.name, mtime=ti.mtime, mode=ti.mode)
                        if out is None:
                            continue
                        with out, open(src_path, "rb") as src:
                            out.copy_from(src)
                    else:
                        ctx.warn(t("sec.special_skipped", name=ti.name))
                        ctx.skipped += 1
            except (tarfile.TarError, EOFError, lzma.LZMAError, zlib_error()) as e:
                raise ArchiveError(t("err.corrupt", detail=e)) from e
        ctx.finish()

    # ------------------------------------------------------------------
    def _rebuild(self, drop: set[str], sources: list[Source], level: int,
                 progress: Optional[ProgressFn], cancel: Optional[CancelToken]) -> None:
        """Arşivi geçici dosyaya yeniden yazar (silme ve ekleme için)."""
        fd, tmp = tempfile.mkstemp(prefix=".sandik-", suffix=".tar", dir=self.path.parent)
        os.close(fd)
        replace = {s.arcname for s in sources}
        try:
            with _Stream(self.path, self.comp, Limits.unlimited(), cancel) as s, \
                    _open_tar_writer(tmp, self.comp, level) as out:
                for ti in s.tar:
                    name = make_entry(ti.name).name
                    if any(name == d or name.startswith(d + "/") for d in drop) or name in replace:
                        continue
                    if cancel:
                        cancel.check()
                    out.addfile(ti, s.tar.extractfile(ti) if ti.isfile() else None)
                _add_sources(out, sources, progress, cancel)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        self._entries = None

    def delete(self, names: set[str], cancel: Optional[CancelToken] = None) -> None:
        self._rebuild(names, [], 6, None, cancel)

    def add(self, sources, level=5, progress=None, cancel=None) -> None:
        self._rebuild(set(), sources, level, progress, cancel)


def zlib_error():
    import zlib
    return zlib.error


def _open_tar_writer(path, comp: Optional[str], level: int) -> tarfile.TarFile:
    level = min(max(level, 0), 9)
    if comp is None:
        return tarfile.open(path, "w", format=tarfile.PAX_FORMAT)
    if comp == "xz":
        return tarfile.open(path, "w:xz", preset=level, format=tarfile.PAX_FORMAT)
    return tarfile.open(path, f"w:{comp}", compresslevel=max(level, 1),
                        format=tarfile.PAX_FORMAT)


def _add_sources(tf: tarfile.TarFile, sources: list[Source], progress, cancel) -> None:
    tracker = AddProgress(sources, progress)
    for s in sources:
        if cancel:
            cancel.check()
        tracker.start(s.arcname)
        ti = tf.gettarinfo(str(s.path), arcname=s.arcname)
        ti.uname = ti.gname = ""
        ti.uid = ti.gid = 0
        if s.is_dir:
            ti.type = tarfile.DIRTYPE
            tf.addfile(ti)
            continue
        if not ti.isfile():  # bağlantı izlenerek içerik eklenir
            st = os.stat(s.path)
            ti.type, ti.size, ti.linkname = tarfile.REGTYPE, st.st_size, ""
        with open(s.path, "rb") as f:
            tf.addfile(ti, ProgressReader(f, tracker, cancel))


def create_tar(out_path, sources, comp=None, level=5, progress=None, cancel=None) -> None:
    with _open_tar_writer(out_path, comp, level) as tf:
        _add_sources(tf, sources, progress, cancel)


# ----------------------------------------------------------------------
# Tek dosyalık sıkıştırılmış akışlar (.gz, .bz2, .xz)
# ----------------------------------------------------------------------

class StreamBackend(Backend):
    can_add = False
    can_delete = False

    def __init__(self, path, password=None, comp: str = "gz") -> None:
        super().__init__(path, password)
        self.comp = comp
        self.format_name = comp.upper()

    def _inner_name(self) -> str:
        name = self.path.name
        suffix = "." + self.comp
        if name.lower().endswith(suffix):
            return name[: -len(suffix)] or "data"
        return name + ".out"

    def entries(self) -> list[Entry]:
        size = 0
        if self.comp == "gz":  # ISIZE alanı (mod 2^32, yalnızca bilgi amaçlı)
            with open(self.path, "rb") as f:
                f.seek(-4, os.SEEK_END)
                size = int.from_bytes(f.read(4), "little")
        st = self.path.stat()
        return [make_entry(self._inner_name(), size=size, packed=st.st_size,
                           mtime=_mtime(st.st_mtime))]

    def needs_password(self) -> bool:
        return False

    def extract(self, ctx: ExtractContext, names=None) -> None:
        name = self._inner_name()
        ctx.begin_entry(name)
        size = self.path.stat().st_size
        with open(self.path, "rb") as raw:
            ctx.progress_total = size
            ctx.progress_source = raw.tell
            out = ctx.open_file(name, packed=size, mtime=self.path.stat().st_mtime)
            if out is None:
                return
            try:
                with out:
                    out.copy_from(open_decompressed(raw, self.comp), CHUNK)
            except (OSError, EOFError, lzma.LZMAError, zlib_error()) as e:
                raise ArchiveError(t("err.corrupt", detail=e)) from e
        ctx.finish()


def create_stream(out_path, sources: list[Source], comp: str, level=5, progress=None,
                  cancel=None) -> None:
    files = [s for s in sources if not s.is_dir]
    if len(files) != 1 or len(sources) != 1:
        raise UnsupportedOperation(t("err.single_file", fmt=comp.upper(), up=comp.upper()))
    src = files[0]
    level = min(max(level, 1), 9)
    if comp == "gz":
        dst = gzip.GzipFile(out_path, "wb", compresslevel=level)
    elif comp == "bz2":
        dst = bz2.BZ2File(out_path, "wb", compresslevel=level)
    else:
        dst = lzma.LZMAFile(out_path, "wb", preset=level)
    tracker = AddProgress(sources, progress)
    tracker.start(src.arcname)
    with dst, open(src.path, "rb") as f:
        shutil.copyfileobj(ProgressReader(f, tracker, cancel), dst, 1 << 20)
