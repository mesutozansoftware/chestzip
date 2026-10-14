"""ZIP desteği (okuma, oluşturma, ekleme, silme, AES-256 şifreleme)."""

from __future__ import annotations

import copy
import os
import shutil
import stat
import struct
import tempfile
import zipfile
from datetime import datetime
from typing import Optional

from ..errors import ArchiveError, PasswordRequired, SafetyError, WrongPassword
from ..i18n import t
from ..safety import CancelToken, ExtractContext, ProgressFn
from .base import AddProgress, Backend, Entry, ProgressReader, Source, make_entry

try:  # AES şifreli ZIP için (MIT lisanslı)
    import pyzipper
except ImportError:  # pragma: no cover
    pyzipper = None

_LOCAL_SIG = b"PK\x03\x04"
_LINK_MAX = 4096


def _reader_class():
    return pyzipper.AESZipFile if pyzipper else zipfile.ZipFile


def _display_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if not info.flag_bits & 0x800:
        # UTF-8 bayrağı olmadan UTF-8 yazan araçlar için düzeltme.
        try:
            name = name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def _mtime(info: zipfile.ZipInfo) -> Optional[datetime]:
    try:
        return datetime(*info.date_time)
    except (ValueError, TypeError):
        return None


def _unix_mode(info: zipfile.ZipInfo) -> Optional[int]:
    if info.create_system == 3:  # Unix
        return info.external_attr >> 16
    return None


def _map_runtime_error(e: Exception) -> Exception:
    msg = str(e).lower()
    if "password required" in msg or "encrypted" in msg and "required" in msg:
        return PasswordRequired(t("err.password_required"))
    if "password" in msg:
        return WrongPassword(t("err.wrong_password"))
    return ArchiveError(t("err.corrupt", detail=e))


class ZipBackend(Backend):
    format_name = "ZIP"
    can_delete = True
    can_add = True
    can_encrypt = pyzipper is not None

    def __init__(self, path, password=None) -> None:
        super().__init__(path, password)
        self._entries: Optional[list[Entry]] = None

    def _open(self):
        try:
            zf = _reader_class()(self.path)
        except (zipfile.BadZipFile, OSError, ValueError) as e:
            raise ArchiveError(t("err.corrupt", detail=e)) from e
        if self.password:
            zf.setpassword(self.password.encode("utf-8"))
        return zf

    def entries(self) -> list[Entry]:
        if self._entries is None:
            out = []
            with self._open() as zf:
                for info in zf.infolist():
                    mode = _unix_mode(info)
                    is_link = mode is not None and stat.S_ISLNK(mode)
                    is_dir = info.is_dir()
                    out.append(make_entry(
                        _display_name(info), is_dir=is_dir, size=info.file_size,
                        packed=info.compress_size, mtime=_mtime(info), crc=info.CRC,
                        encrypted=bool(info.flag_bits & 0x1),
                        kind="dir" if is_dir else ("symlink" if is_link else "file"),
                        mode=mode, ref=info))
            self._entries = out
        return self._entries

    def security_problems(self) -> list[str]:
        """Üst üste binen kayıtları (Fifield tipi zip bombası) tespit eder."""
        problems = []
        size = self.path.stat().st_size
        with open(self.path, "rb") as f:
            spans = []
            for e in self.entries():
                info = e.ref
                f.seek(info.header_offset)
                hdr = f.read(30)
                if len(hdr) < 30 or hdr[:4] != _LOCAL_SIG:
                    problems.append(t("err.corrupt", detail=f"bad local header: {e.name}"))
                    continue
                n, m = struct.unpack("<HH", hdr[26:30])
                start = info.header_offset
                end = start + 30 + n + m + info.compress_size
                if end > size:
                    problems.append(t("err.corrupt", detail=f"entry beyond EOF: {e.name}"))
                spans.append((start, end))
            spans.sort()
            for (s1, e1), (s2, _e2) in zip(spans, spans[1:]):
                if s2 < e1:
                    problems.append(t("sec.overlap"))
                    break
        return problems

    # ------------------------------------------------------------------
    def extract(self, ctx: ExtractContext, names=None) -> None:
        problems = self.security_problems()
        if problems:
            raise SafetyError(problems[0])
        with self._open() as zf:
            for e in sorted(self.entries(), key=lambda e: e.ref.header_offset):
                if names is not None and e.name not in names:
                    continue
                info = e.ref
                ctx.begin_entry(e.name)
                if e.kind == "dir":
                    ctx.make_dir(e.raw_name, e.timestamp)
                    continue
                try:
                    if e.kind == "symlink":
                        with zf.open(info) as src:
                            target = src.read(_LINK_MAX).decode("utf-8", "replace")
                        ctx.make_symlink(e.raw_name, target)
                        continue
                    out = ctx.open_file(e.raw_name, packed=info.compress_size,
                                        mtime=e.timestamp, mode=e.mode)
                    if out is None:
                        continue
                    with out:
                        with zf.open(info) as src:
                            out.copy_from(src)
                except RuntimeError as err:
                    raise _map_runtime_error(err) from err
                except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as err:
                    raise ArchiveError(t("err.corrupt", detail=err)) from err
                except NotImplementedError as err:
                    raise ArchiveError(t("err.corrupt", detail=err)) from err
        ctx.finish()

    # ------------------------------------------------------------------
    def delete(self, names: set[str], cancel: Optional[CancelToken] = None) -> None:
        """Seçilen kayıtları siler. Veri yeniden sıkıştırılmadan ham olarak
        kopyalandığı için şifreli kayıtlar da korunur."""
        keep = [e.ref for e in self.entries() if e.name not in names]
        fd, tmp = tempfile.mkstemp(prefix=".chestzip-", suffix=".zip", dir=self.path.parent)
        os.close(fd)
        try:
            with open(self.path, "rb") as src, zipfile.ZipFile(tmp, "w") as out:
                for info in keep:
                    if cancel:
                        cancel.check()
                    _raw_copy_entry(src, out, info)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        self._entries = None

    def add(self, sources: list[Source], level: int = 5, progress: Optional[ProgressFn] = None,
            cancel: Optional[CancelToken] = None) -> None:
        existing = {e.name for e in self.entries()}
        dup = {s.arcname for s in sources} & existing
        if dup:  # aynı adlı kayıtları değiştir
            self.delete(dup, cancel)
        _write_zip(self.path, sources, level, self.password, progress, cancel, mode="a")
        self._entries = None


def _raw_copy_entry(src, out: zipfile.ZipFile, info: zipfile.ZipInfo) -> None:
    src.seek(info.header_offset)
    hdr = src.read(30)
    if hdr[:4] != _LOCAL_SIG:
        raise ArchiveError(t("err.corrupt", detail=info.filename))
    n, m = struct.unpack("<HH", hdr[26:30])
    src.read(n)  # eski ad baytları; merkezi dizinle tutarlı olacak şekilde yeniden yazılır
    extra = src.read(m)
    new = copy.copy(info)
    new.header_offset = out.fp.tell()
    name_bytes, flags = new._encodeFilenameFlags()
    new.flag_bits = flags
    local = hdr[:6] + struct.pack("<H", flags) + hdr[8:26] + struct.pack("<HH", len(name_bytes), m)
    out.fp.write(local + name_bytes + extra)
    remaining = info.compress_size
    while remaining:
        chunk = src.read(min(remaining, 1 << 20))
        if not chunk:
            raise ArchiveError(t("err.corrupt", detail=info.filename))
        out.fp.write(chunk)
        remaining -= len(chunk)
    if info.flag_bits & 0x8:  # veri tanımlayıcı (data descriptor)
        sig = src.read(4)
        zip64 = info.file_size > zipfile.ZIP64_LIMIT or info.compress_size > zipfile.ZIP64_LIMIT
        body = 20 if zip64 else 12
        if sig == b"PK\x07\x08":
            out.fp.write(sig + src.read(body))
        else:
            out.fp.write(sig + src.read(body - 4))
    out.filelist.append(new)
    out.NameToInfo[new.filename] = new
    out.start_dir = out.fp.tell()
    out._didModify = True


def _set_level(zinfo, level: int) -> None:
    for attr in ("compress_level", "_compresslevel"):
        try:
            setattr(zinfo, attr, level)
        except AttributeError:
            pass


def _write_zip(out_path, sources: list[Source], level: int, password: Optional[str],
               progress: Optional[ProgressFn], cancel: Optional[CancelToken], mode="w") -> None:
    method = zipfile.ZIP_STORED if level == 0 else zipfile.ZIP_DEFLATED
    if password:
        if pyzipper is None:  # pragma: no cover
            raise ArchiveError("pyzipper is required for encrypted ZIP")
        zf = pyzipper.AESZipFile(out_path, mode, compression=method,
                                 encryption=pyzipper.WZ_AES)
        zf.setpassword(password.encode("utf-8"))
        zf.setencryption(pyzipper.WZ_AES, nbits=256)
        info_cls = zf.zipinfo_cls
    else:
        zf = zipfile.ZipFile(out_path, mode, compression=method,
                             compresslevel=None if level == 0 else level, allowZip64=True)
        info_cls = zipfile.ZipInfo
    tracker = AddProgress(sources, progress)
    with zf:
        for s in sources:
            if cancel:
                cancel.check()
            tracker.start(s.arcname)
            zinfo = info_cls.from_file(s.path, s.arcname)
            if s.is_dir:
                zf.writestr(zinfo, b"")
                continue
            zinfo.compress_type = method
            _set_level(zinfo, level)
            with open(s.path, "rb") as f, \
                    zf.open(zinfo, "w", force_zip64=s.size >= zipfile.ZIP64_LIMIT) as dst:
                shutil.copyfileobj(ProgressReader(f, tracker, cancel), dst, 1 << 20)


def create_zip(out_path, sources, level=5, password=None, progress=None, cancel=None) -> None:
    _write_zip(out_path, sources, level, password, progress, cancel, mode="w")
