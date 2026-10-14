"""Arka uçların ortak arayüzü ve yardımcıları."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from ..errors import UnsupportedOperation
from ..i18n import t
from ..safety import CancelToken, ExtractContext, ProgressFn, normalize_name


@dataclass
class Entry:
    name: str                    # görüntüleme için normalize edilmiş ad (a/b/c)
    raw_name: str                # arşivdeki ham ad (güvenlik kontrolü bununla)
    is_dir: bool = False
    size: int = 0                # açılmış boyut (başlığa göre)
    packed: Optional[int] = None # sıkışık boyut (solid arşivlerde bilinmeyebilir)
    mtime: Optional[datetime] = None
    crc: Optional[int] = None
    encrypted: bool = False
    kind: str = "file"           # file | dir | symlink | hardlink | special
    link_target: Optional[str] = None
    mode: Optional[int] = None
    ref: Any = field(default=None, repr=False, compare=False)

    @property
    def timestamp(self) -> Optional[float]:
        if self.mtime is None:
            return None
        try:
            return self.mtime.timestamp()
        except (OverflowError, OSError, ValueError):
            return None


def make_entry(raw_name: str, **kw) -> Entry:
    return Entry(name=normalize_name(raw_name), raw_name=raw_name, **kw)


class Backend:
    """Bir arşiv biçimi için okuma/yazma işlemleri."""

    format_name = "?"
    can_create = True
    can_delete = False
    can_add = False
    can_encrypt = False

    def __init__(self, path: str | Path, password: Optional[str] = None) -> None:
        self.path = Path(path)
        self.password = password

    # Okuma ---------------------------------------------------------------
    def entries(self) -> list[Entry]:
        raise NotImplementedError

    def needs_password(self) -> bool:
        return any(e.encrypted for e in self.entries())

    def extract(self, ctx: ExtractContext, names: Optional[set[str]] = None) -> None:
        raise NotImplementedError

    def security_problems(self) -> list[str]:
        """Biçime özel yapısal kontroller (ör. ZIP üst üste binme)."""
        return []

    # Yazma ---------------------------------------------------------------
    def delete(self, names: set[str], cancel: Optional[CancelToken] = None) -> None:
        raise UnsupportedOperation(t("err.no_delete", fmt=self.format_name))

    def add(self, sources: list["Source"], level: int = 5,
            progress: Optional[ProgressFn] = None, cancel: Optional[CancelToken] = None) -> None:
        raise UnsupportedOperation(t("err.no_add", fmt=self.format_name))

    def close(self) -> None:
        pass


@dataclass
class Source:
    """Arşive eklenecek bir disk öğesi."""
    path: Path
    arcname: str
    is_dir: bool
    size: int = 0


def collect_sources(paths: Iterable[str | Path]) -> list[Source]:
    """Verilen dosya/klasörleri arşive eklenecek öğe listesine çevirir.

    Klasör eklenince klasörün kendisi de arşivde yer alır (``Klasör/...``).
    Klasöre işaret eden sembolik bağlantılar döngüleri önlemek için izlenmez.
    """
    out: list[Source] = []
    seen: set[str] = set()

    def push(src: Source) -> None:
        if src.arcname in seen:
            return
        seen.add(src.arcname)
        out.append(src)

    for p in paths:
        p = Path(p)
        base = p.parent
        if p.is_dir() and not p.is_symlink():
            push(Source(p, p.name, True))
            for root, dirs, files in os.walk(p, followlinks=False):
                dirs.sort()
                rootp = Path(root)
                for d in list(dirs):
                    dp = rootp / d
                    if dp.is_symlink():
                        dirs.remove(d)
                        continue
                    push(Source(dp, dp.relative_to(base).as_posix(), True))
                for f in sorted(files):
                    fp = rootp / f
                    if fp.is_file():  # bozuk bağlantıları ve özel dosyaları atla
                        push(Source(fp, fp.relative_to(base).as_posix(), False,
                                    fp.stat().st_size))
        elif p.is_file():
            push(Source(p, p.name, False, p.stat().st_size))
    return out


class ProgressReader:
    """Kaynak dosyadan okurken ilerleme bildirir ve iptali denetler."""

    def __init__(self, f, on_read, cancel: Optional[CancelToken]) -> None:
        self.f = f
        self.on_read = on_read
        self.cancel = cancel

    def read(self, n: int = -1) -> bytes:
        if self.cancel:
            self.cancel.check()
        data = self.f.read(n)
        self.on_read(len(data))
        return data


class AddProgress:
    def __init__(self, sources: list[Source], progress: Optional[ProgressFn]) -> None:
        self.total = sum(s.size for s in sources)
        self.done = 0
        self.progress = progress
        self.name = ""

    def start(self, name: str) -> None:
        self.name = name
        if self.progress:
            self.progress(self.done, self.total, name)

    def __call__(self, n: int) -> None:
        self.done += n
        if self.progress:
            self.progress(self.done, self.total, self.name)
