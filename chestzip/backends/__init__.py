"""Biçim tespiti ve arka uç seçimi."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

from ..errors import UnsupportedFormat
from ..i18n import t
from ..safety import Limits
from .base import Backend, Entry, Source, collect_sources
from .tar_backend import COMPRESSORS, open_decompressed, sniff_compression

SEVENZ_MAGIC = b"7z\xbc\xaf\x27\x1c"
RAR_MAGIC = b"Rar!\x1a\x07"

# Oluşturulabilen biçimler ve varsayılan uzantıları
CREATE_FORMATS = {
    "zip": ".zip",
    "7z": ".7z",
    "tar": ".tar",
    "tar.gz": ".tar.gz",
    "tar.bz2": ".tar.bz2",
    "tar.xz": ".tar.xz",
    "gz": ".gz",
    "bz2": ".bz2",
    "xz": ".xz",
}
ENCRYPTABLE = {"zip", "7z"}

ARCHIVE_EXTENSIONS = (".zip", ".7z", ".rar", ".tar", ".tgz", ".tbz", ".tbz2", ".txz",
                      ".tar.gz", ".tar.bz2", ".tar.xz", ".gz", ".bz2", ".xz", ".jar",
                      ".cbz", ".cbr", ".epub", ".apk")


def _is_tar_header(block: bytes) -> bool:
    if len(block) < 512:
        return False
    if block[257:262] == b"ustar":
        return True
    # Eski V7 tar: sağlama toplamını doğrula
    try:
        chk = int(block[148:156].split(b"\x00")[0].strip() or b"-1", 8)
    except ValueError:
        return False
    calc = sum(block[:148]) + 8 * 32 + sum(block[156:512])
    return chk == calc


def detect_format(path: str | Path) -> str:
    """Dosyanın içeriğine (uzantıya değil) bakarak biçimi bulur."""
    path = Path(path)
    try:
        with open(path, "rb") as f:
            head = f.read(512)
            if head.startswith(SEVENZ_MAGIC):
                return "7z"
            if head.startswith(RAR_MAGIC):
                return "rar"
            if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
                return "zip"
            comp = sniff_compression(head)
            if comp:
                f.seek(0)
                try:
                    # Yalnızca ilk 512 bayt açılır: güvenli ve sınırlı.
                    inner = open_decompressed(f, comp).read(512)
                except Exception:
                    inner = b""
                return f"tar.{comp}" if _is_tar_header(inner) else comp
            if _is_tar_header(head):
                return "tar"
    except OSError as e:
        raise UnsupportedFormat(t("err.unknown_format", path=path)) from e
    if zipfile.is_zipfile(path):  # kendinden açılan (SFX) ZIP'ler vb.
        return "zip"
    raise UnsupportedFormat(t("err.unknown_format", path=path))


def open_backend(path: str | Path, password: Optional[str] = None,
                 limits: Optional[Limits] = None, fmt: Optional[str] = None) -> Backend:
    fmt = fmt or detect_format(path)
    if fmt == "zip":
        from .zip_backend import ZipBackend
        return ZipBackend(path, password)
    if fmt == "7z":
        from .sevenzip_backend import SevenZipBackend
        return SevenZipBackend(path, password)
    if fmt == "rar":
        from .rar_backend import RarBackend
        return RarBackend(path, password)
    if fmt == "tar" or fmt.startswith("tar."):
        from .tar_backend import TarBackend
        comp = fmt.split(".", 1)[1] if "." in fmt else None
        return TarBackend(path, password, comp=comp, limits=limits)
    if fmt in COMPRESSORS:
        from .tar_backend import StreamBackend
        return StreamBackend(path, password, comp=fmt)
    raise UnsupportedFormat(t("err.unknown_format", path=path))


def format_for_filename(name: str) -> Optional[str]:
    n = name.lower()
    for fmt, ext in sorted(CREATE_FORMATS.items(), key=lambda kv: -len(kv[1])):
        if n.endswith(ext):
            return fmt
    if n.endswith(".tgz"):
        return "tar.gz"
    if n.endswith((".tbz", ".tbz2")):
        return "tar.bz2"
    if n.endswith(".txz"):
        return "tar.xz"
    return None


__all__ = ["Backend", "Entry", "Source", "collect_sources", "detect_format", "open_backend",
           "CREATE_FORMATS", "ENCRYPTABLE", "ARCHIVE_EXTENSIONS", "format_for_filename"]
