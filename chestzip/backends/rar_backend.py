"""RAR desteği — YALNIZCA AÇMA.

RAR sıkıştırma algoritması tescillidir; ChestZip RAR arşivi oluşturmaz.
Başlıklar ``rarfile`` (ISC) ile okunur; veri, ``py7zz`` paketiyle birlikte gelen
resmi 7-Zip programıyla (``7zz``) açılır. Böylece kullanıcının ek bir araç
kurması gerekmez ve her işletim sisteminde aynı çözücü kullanılır. 7-Zip
bulunamazsa sistemdeki unrar/unar/7z/bsdtar denenir. Açılan veri yine
ChestZip'in güvenlik katmanından geçer.
"""

from __future__ import annotations

import atexit
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

from ..errors import ArchiveError, PasswordRequired, WrongPassword
from ..i18n import t
from ..safety import ExtractContext
from .base import Backend, Entry, make_entry

try:
    import rarfile
except ImportError:  # pragma: no cover
    rarfile = None

_EXE = "7zz.exe" if sys.platform.startswith("win") else "7zz"


def bundled_7zz() -> Optional[Path]:
    """Uygulamayla birlikte gelen 7zz programının yolu."""
    candidates = []
    if getattr(sys, "frozen", False):  # PyInstaller paketi
        candidates.append(Path(getattr(sys, "_MEIPASS", "")) / "chestzip_bin" / _EXE)
    # py7zz modülünü içe aktarmadan (ağ/güncelleme kodu çalışmasın) yerini bul
    spec = importlib.util.find_spec("py7zz")
    if spec and spec.origin:
        candidates.append(Path(spec.origin).parent / "bin" / _EXE)
    for c in candidates:
        if c.is_file():
            return c
    return None


_tool_ready = False


def _local(dt):
    """RAR5 zamanları UTC'dir; görüntüleme için yerel saate çevir."""
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


_list_dir: Optional[str] = None


def _listfile(name: str) -> str:
    """Dosya adını UTF-8 liste dosyasına yazar.

    Adı komut satırında vermek Windows'ta bazı Unicode karakterleri bozar;
    7-Zip'e ``-scsUTF-8 -i@liste`` ile vermek her platformda aynı çalışır."""
    global _list_dir
    if _list_dir is None:
        _list_dir = tempfile.mkdtemp(prefix="chestzip-rar-")
        atexit.register(shutil.rmtree, _list_dir, True)
    fd, path = tempfile.mkstemp(suffix=".lst", dir=_list_dir)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(name + "\n")
    return path


if rarfile is not None:
    class _SevenZipSetup(rarfile.ToolSetup):
        """Gömülü 7zz için komut satırı: dosya adı liste dosyasıyla verilir."""

        def open_cmdline(self, pwd, rarfn, filefn=None):
            cmd = [rarfile.SEVENZIP2_TOOL, "e", "-so", "-bb0", "-scsUTF-8", "-spd"]
            self.add_password_arg(cmd, pwd)
            if filefn:
                cmd.append("-i@" + _listfile(filefn))
            cmd += ["--", rarfn]
            return cmd


def _setup_tool() -> None:
    global _tool_ready
    if _tool_ready:
        return
    exe = bundled_7zz()
    if exe is not None:
        rarfile.SEVENZIP2_TOOL = str(exe)
        setup = _SevenZipSetup(rarfile.SEVENZIP2_CONFIG)
        if setup.check():
            rarfile.CURRENT_SETUP = setup
            _tool_ready = True
            return
    rarfile.tool_setup(force=True)  # yedek: sistemdeki araçlar
    _tool_ready = True


class RarBackend(Backend):
    format_name = "RAR"
    can_create = False

    def __init__(self, path, password=None) -> None:
        super().__init__(path, password)
        if rarfile is None:
            raise ArchiveError(t("err.rar_tool"))
        try:
            _setup_tool()
        except rarfile.RarCannotExec as e:
            raise ArchiveError(t("err.rar_tool")) from e
        self._entries: Optional[list[Entry]] = None

    def _open(self):
        try:
            rf = rarfile.RarFile(str(self.path))
        except rarfile.PasswordRequired as e:
            if not self.password:
                raise PasswordRequired(t("err.password_required")) from e
            rf = None
        except rarfile.Error as e:
            raise ArchiveError(t("err.corrupt", detail=e)) from e
        if self.password:
            try:
                if rf is None:
                    rf = rarfile.RarFile(str(self.path), "r")
                rf.setpassword(self.password)
            except rarfile.Error as e:
                raise WrongPassword(t("err.wrong_password")) from e
        if not self.password and rf.needs_password() and not rf.infolist():
            # Başlığı şifreli arşiv: rarfile hata vermeden boş liste döndürür.
            rf.close()
            raise PasswordRequired(t("err.password_required"))
        return rf

    def needs_password(self) -> bool:
        try:
            with rarfile.RarFile(str(self.path)) as rf:
                return rf.needs_password()
        except rarfile.PasswordRequired:
            return True

    def entries(self) -> list[Entry]:
        if self._entries is None:
            out = []
            with self._open() as rf:
                for i in rf.infolist():
                    out.append(make_entry(
                        i.filename, is_dir=i.is_dir(), size=i.file_size or 0,
                        packed=i.compress_size, mtime=_local(getattr(i, "mtime", None)),
                        crc=i.CRC, encrypted=i.needs_password(),
                        kind="dir" if i.is_dir() else ("symlink" if i.is_symlink() else "file"),
                        ref=i))
            self._entries = out
        return self._entries

    def extract(self, ctx: ExtractContext, names=None) -> None:
        try:
            with self._open() as rf:
                for e in self.entries():
                    if names is not None and e.name not in names:
                        continue
                    ctx.begin_entry(e.name)
                    if e.kind == "dir":
                        ctx.make_dir(e.raw_name, e.timestamp)
                        continue
                    if e.kind == "symlink":
                        ctx.warn(t("sec.link_skipped", name=e.name, target="?"))
                        ctx.skipped += 1
                        continue
                    out = ctx.open_file(e.raw_name, packed=e.packed, mtime=e.timestamp)
                    if out is None:
                        continue
                    with out, rf.open(e.ref, pwd=self.password) as src:
                        out.copy_from(src)
        except rarfile.RarCannotExec as err:
            raise ArchiveError(t("err.rar_tool")) from err
        except rarfile.PasswordRequired as err:
            raise PasswordRequired(t("err.password_required")) from err
        except (rarfile.RarWrongPassword, rarfile.BadRarFile) as err:
            raise WrongPassword(t("err.wrong_password")) if self.password else \
                ArchiveError(t("err.corrupt", detail=err)) from err
        except rarfile.Error as err:
            raise ArchiveError(t("err.corrupt", detail=err)) from err
        ctx.finish()
