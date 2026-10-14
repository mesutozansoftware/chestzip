"""Güvenlik katmanı.

Arşiv açarken karşılaşılabilecek saldırılara karşı korur:

* Zip bombası (yüksek sıkıştırma oranı, devasa toplam boyut)
* Üst üste binen (overlapping) ZIP kayıtları — Fifield tipi özyinelemesiz bomba
* Çok fazla dosya içeren arşivler (inode/dosya tablosu tüketme)
* Diskin tamamen doldurulması
* Zip Slip / path traversal (``../../etc/passwd``, mutlak yollar, sürücü harfleri)
* Hedef dışını gösteren sembolik bağlantılar
* Windows'ta ayrılmış adlar (CON, NUL ...) ve geçersiz karakterler

Önemli tasarım ilkesi: arşiv başlıklarındaki boyut bilgilerine güvenilmez.
Başlıklar ön kontrol için kullanılır, asıl koruma veri açılırken bayt bayt
sayılarak yapılır. Sınır aşılırsa yarım dosya silinir.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import sys
import threading
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Callable, Iterable, Optional

from .errors import Cancelled, SafetyError, UnsafePathError
from .i18n import t

KiB = 1024
MiB = 1024 * KiB
GiB = 1024 * MiB

IS_WINDOWS = sys.platform.startswith("win")
CHUNK = 1 * MiB


@dataclass
class Limits:
    """Çıkarma sırasında uygulanan güvenlik sınırları.

    ``enabled`` False olsa bile yol güvenliği (Zip Slip) her zaman açıktır.
    """

    enabled: bool = True
    max_total_size: int = 20 * GiB      # tek işlemde açılabilecek en fazla veri
    max_entries: int = 250_000          # en fazla dosya/klasör sayısı
    max_ratio: float = 1000.0           # sıkıştırma oranı üst sınırı (açık/sıkışık)
    ratio_grace: int = 64 * MiB         # oran kontrolü bu boyuttan sonra devreye girer
    disk_reserve: int = 1 * GiB         # diskte her zaman boş bırakılacak alan
    allow_symlinks: bool = False        # yalnızca hedef içini gösteren bağlantılara izin

    @classmethod
    def unlimited(cls) -> "Limits":
        return cls(enabled=False)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Limits":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in names})


def human_size(n: Optional[float]) -> str:
    if n is None:
        return "?"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# --------------------------------------------------------------------------
# Yol güvenliği
# --------------------------------------------------------------------------

_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                 *(f"LPT{i}" for i in range(1, 10))}
_WIN_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_DRIVE = re.compile(r"^[A-Za-z]:")


def normalize_name(name: str) -> str:
    """Arşiv içi adı görüntüleme için ``a/b/c`` biçimine getirir (güvenlik değil)."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    return "/".join(parts)


def safe_parts(name: str) -> list[str]:
    """Arşiv içi adı güvenli yol parçalarına çevirir; tehlikeliyse hata verir."""
    if "\x00" in name:
        raise UnsafePathError(t("err.unsafe_path", name=name))
    n = name.replace("\\", "/")
    n = _DRIVE.sub("", n)  # C:/... -> /...
    parts: list[str] = []
    for p in n.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            raise UnsafePathError(t("err.unsafe_path", name=name))
        if IS_WINDOWS:
            p = _WIN_BAD_CHARS.sub("_", p).rstrip(" .") or "_"
            if p.split(".")[0].upper() in _WIN_RESERVED:
                p = "_" + p
        parts.append(p)
    if not parts:
        raise UnsafePathError(t("err.unsafe_path", name=name))
    return parts


def _norm(p: str) -> str:
    return os.path.normcase(os.path.realpath(p))


def is_within(path: str | Path, root: str | Path) -> bool:
    path, root = _norm(str(path)), _norm(str(root))
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # Windows'ta farklı sürücüler
        return False


# --------------------------------------------------------------------------
# Ön analiz (başlık bilgileriyle)
# --------------------------------------------------------------------------

@dataclass
class SecurityReport:
    problems: list[str]   # çıkarmayı engelleyen sorunlar
    warnings: list[str]   # bilgilendirme
    total_size: int
    packed_size: int
    entry_count: int

    @property
    def ok(self) -> bool:
        return not self.problems


def analyze_entries(entries: Iterable, archive_size: int, limits: Limits,
                    dest: Optional[str] = None) -> SecurityReport:
    """Başlıklardaki bilgilerle hızlı güvenlik ön kontrolü yapar."""
    problems: list[str] = []
    warnings: list[str] = []
    total = packed = count = 0
    unsafe: list[str] = []
    links = 0
    for e in entries:
        count += 1
        total += e.size or 0
        packed += e.packed or 0
        try:
            safe_parts(e.raw_name)
        except UnsafePathError:
            unsafe.append(e.raw_name)
        if e.kind in ("symlink", "hardlink"):
            links += 1
        if (limits.enabled and e.packed and e.size and e.size > limits.ratio_grace
                and e.size / e.packed > limits.max_ratio):
            problems.append(t("sec.entry_ratio", name=e.name, ratio=e.size / e.packed,
                              max=limits.max_ratio))
    if unsafe:
        warnings.append(t("sec.unsafe_paths", n=len(unsafe), first=unsafe[0]))
    if links:
        warnings.append(t("sec.links", n=links))
    if limits.enabled:
        if count > limits.max_entries:
            problems.append(t("sec.too_many", n=count, max=limits.max_entries))
        if total > limits.max_total_size:
            problems.append(t("sec.too_big", size=human_size(total),
                              max=human_size(limits.max_total_size)))
        if archive_size and total > limits.ratio_grace and total / archive_size > limits.max_ratio:
            problems.append(t("sec.total_ratio", ratio=total / archive_size,
                              max=limits.max_ratio))
        if dest:
            free = disk_free(dest)
            if free is not None and total > free - limits.disk_reserve:
                problems.append(t("sec.no_space", size=human_size(total),
                                  free=human_size(free)))
    return SecurityReport(problems, warnings, total, packed, count)


def disk_free(path: str | Path) -> Optional[int]:
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


# --------------------------------------------------------------------------
# İptal ve ilerleme
# --------------------------------------------------------------------------

class CancelToken:
    def __init__(self) -> None:
        self._ev = threading.Event()

    def cancel(self) -> None:
        self._ev.set()

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()

    def check(self) -> None:
        if self._ev.is_set():
            raise Cancelled(t("err.cancelled"))


ProgressFn = Callable[[int, int, str], None]          # (yapılan, toplam, ad)
AskOverwriteFn = Callable[[str], str]                 # yol -> karar


class StreamGuard:
    """Açılmış (decompressed) veri akışını sayar; tar.gz/gz gibi
    başlığında boyut bilgisi olmayan biçimlerde bomba koruması sağlar."""

    def __init__(self, limits: Limits, compressed_size: int,
                 cancel: Optional[CancelToken] = None) -> None:
        self.limits = limits
        self.compressed_size = max(compressed_size, 1)
        self.cancel = cancel
        self.total = 0

    def feed(self, n: int) -> None:
        self.total += n
        if self.cancel:
            self.cancel.check()
        lim = self.limits
        if not lim.enabled:
            return
        # Tar başlıkları ve dolgu için küçük bir pay bırakılır.
        if self.total > lim.max_total_size + 64 * MiB:
            raise SafetyError(t("sec.stream_too_big", max=human_size(lim.max_total_size)))
        if self.total > lim.ratio_grace and self.total / self.compressed_size > lim.max_ratio:
            raise SafetyError(t("sec.stream_ratio", ratio=self.total / self.compressed_size,
                                max=lim.max_ratio))


class GuardedReader:
    """Okunan her baytı bir StreamGuard'a bildiren salt-okunur dosya sarmalayıcı."""

    def __init__(self, raw, guard: StreamGuard) -> None:
        self.raw = raw
        self.guard = guard

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            # Sınırsız okuma yerine parça parça oku ki koruma çalışsın.
            out = bytearray()
            while True:
                chunk = self.read(CHUNK)
                if not chunk:
                    return bytes(out)
                out += chunk
        data = self.raw.read(n)
        self.guard.feed(len(data))
        return data

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        self.raw.close()


# --------------------------------------------------------------------------
# Çıkarma bağlamı
# --------------------------------------------------------------------------

class ExtractContext:
    """Bir çıkarma/test işleminin durumunu ve güvenlik kontrollerini taşır.

    Bütün arka uçlar (zip, tar, 7z ...) dosya yazmak için yalnızca bu sınıfı
    kullanır; böylece kurallar tek bir yerde uygulanır.
    """

    def __init__(self, dest: Optional[str | Path], limits: Limits, archive_size: int = 0,
                 overwrite: str = "ask", ask_overwrite: Optional[AskOverwriteFn] = None,
                 progress: Optional[ProgressFn] = None, cancel: Optional[CancelToken] = None,
                 dry_run: bool = False, progress_total: int = 0) -> None:
        self.limits = limits
        self.dry_run = dry_run
        self.archive_size = max(archive_size, 1)
        self.overwrite = overwrite          # ask | always | never | rename
        self.ask_overwrite = ask_overwrite
        self.progress_fn = progress
        self.cancel = cancel or CancelToken()
        self.progress_total = progress_total
        self.progress_source: Optional[Callable[[], int]] = None
        self.written = 0
        self.entries = 0
        self.files = 0
        self.skipped = 0
        self.warnings: list[str] = []
        self.current = ""
        self._last_report = 0.0
        self._lock = threading.Lock()
        self._dirs_mtime: list[tuple[Path, float]] = []
        if dry_run:
            self.dest = None
            self.budget = None
        else:
            assert dest is not None
            self.dest = Path(dest)
            self.dest.mkdir(parents=True, exist_ok=True)
            self.dest = Path(os.path.realpath(self.dest))
            free = disk_free(self.dest)
            self.budget = None if free is None else max(free - limits.disk_reserve, 0)

    # -- sayaçlar ---------------------------------------------------------
    def check_cancel(self) -> None:
        self.cancel.check()

    def begin_entry(self, name: str) -> None:
        self.cancel.check()
        self.entries += 1
        self.current = name
        if self.limits.enabled and self.entries > self.limits.max_entries:
            raise SafetyError(t("sec.too_many", n=self.entries, max=self.limits.max_entries))
        self.report(force=True)

    def account(self, n: int, out: Optional["OutFile"] = None) -> None:
        """Yazılmak üzere olan ``n`` baytı sınırlara karşı kontrol eder."""
        with self._lock:
            self.written += n
            written = self.written
        self.cancel.check()
        lim = self.limits
        if lim.enabled:
            if written > lim.max_total_size:
                raise SafetyError(t("sec.stream_too_big", max=human_size(lim.max_total_size)))
            if written > lim.ratio_grace and written / self.archive_size > lim.max_ratio:
                raise SafetyError(t("sec.stream_ratio", ratio=written / self.archive_size,
                                    max=lim.max_ratio))
            if out is not None and out.packed:
                if out.written > lim.ratio_grace and out.written / out.packed > lim.max_ratio:
                    raise SafetyError(t("sec.entry_ratio", name=out.name,
                                        ratio=out.written / out.packed, max=lim.max_ratio))
        if self.budget is not None and written > self.budget:
            raise SafetyError(t("sec.disk_full"))
        self.report()

    def report(self, force: bool = False) -> None:
        if not self.progress_fn:
            return
        now = time.monotonic()
        if not force and now - self._last_report < 0.08:
            return
        self._last_report = now
        done = self.progress_source() if self.progress_source else self.written
        self.progress_fn(done, self.progress_total, self.current)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    # -- yollar -------------------------------------------------------------
    def target_path(self, name: str) -> Optional[Path]:
        """Arşiv içi ada karşılık gelen güvenli hedef yolu döndürür.

        Tehlikeli yollar atlanır (None) ve uyarı olarak kaydedilir."""
        try:
            parts = safe_parts(name)
        except UnsafePathError as e:
            self.warn(str(e))
            self.skipped += 1
            return None
        if self.dry_run:
            return Path(*parts)
        target = self.dest.joinpath(*parts)
        # Hedefteki mevcut sembolik bağlantılar üzerinden dışarı çıkmayı engelle.
        if not is_within(target.parent, self.dest) or (
                target.is_symlink() and not is_within(target, self.dest)):
            self.warn(t("err.unsafe_path", name=name))
            self.skipped += 1
            return None
        return target

    def make_dir(self, name: str, mtime: Optional[float] = None) -> None:
        target = self.target_path(name)
        if target is None or self.dry_run:
            return
        if target.exists() and not target.is_dir():
            self.warn(t("err.dir_conflict", name=name))
            return
        target.mkdir(parents=True, exist_ok=True)
        if mtime:
            self._dirs_mtime.append((target, mtime))

    def make_symlink(self, name: str, link_target: str) -> None:
        target = self.target_path(name)
        if target is None or self.dry_run:
            return
        if not self.limits.allow_symlinks or IS_WINDOWS:
            self.warn(t("sec.link_skipped", name=name, target=link_target))
            self.skipped += 1
            return
        resolved = (target.parent / link_target) if not os.path.isabs(link_target) else Path(link_target)
        if os.path.isabs(link_target) or not is_within(resolved, self.dest):
            self.warn(t("sec.link_outside", name=name, target=link_target))
            self.skipped += 1
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            decision = self._decide(target)
            if decision != "overwrite":
                self.skipped += 1
                return
            target.unlink()
        os.symlink(link_target, target)

    def _decide(self, target: Path) -> str:
        """Var olan dosya için ne yapılacağına karar verir:
        overwrite | skip | rename"""
        mode = self.overwrite
        if mode == "always":
            return "overwrite"
        if mode == "never":
            return "skip"
        if mode == "rename":
            return "rename"
        if self.ask_overwrite is None:
            return "skip"
        answer = self.ask_overwrite(str(target))
        if answer == "cancel":
            self.cancel.cancel()
            self.cancel.check()
        if answer == "all":
            self.overwrite = "always"
            return "overwrite"
        if answer == "none":
            self.overwrite = "never"
            return "skip"
        if answer == "rename_all":
            self.overwrite = "rename"
            return "rename"
        return {"yes": "overwrite", "no": "skip", "rename": "rename"}.get(answer, "skip")

    def open_file(self, name: str, packed: Optional[int] = None,
                  mtime: Optional[float] = None, mode: Optional[int] = None):
        """Yazmak için bir OutFile döndürür; dosya atlanacaksa None."""
        target = self.target_path(name)
        if target is None:
            return None
        if self.dry_run:
            return OutFile(self, None, name, packed, mtime, mode)
        if target.is_dir() and not target.is_symlink():
            self.warn(t("err.dir_conflict", name=name))
            self.skipped += 1
            return None
        if target.exists() or target.is_symlink():
            decision = self._decide(target)
            if decision == "skip":
                self.skipped += 1
                return None
            if decision == "rename":
                target = unique_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        return OutFile(self, target, name, packed, mtime, mode)

    def finish(self) -> None:
        for path, mtime in reversed(self._dirs_mtime):
            try:
                os.utime(path, (mtime, mtime))
            except OSError:
                pass
        self.report(force=True)


def unique_path(path: Path) -> Path:
    stem, suffix = path.stem, path.suffix
    i = 1
    while True:
        cand = path.with_name(f"{stem} ({i}){suffix}")
        if not cand.exists() and not cand.is_symlink():
            return cand
        i += 1


class OutFile:
    """Geçici dosyaya yazar; başarıyla biterse yerine taşır, hata olursa siler.

    Böylece bomba tespit edildiğinde diskte yarım kalmış dev dosya kalmaz."""

    def __init__(self, ctx: ExtractContext, target: Optional[Path], name: str,
                 packed: Optional[int], mtime: Optional[float], mode: Optional[int]) -> None:
        self.ctx = ctx
        self.target = target
        self.name = name
        self.packed = packed
        self.mtime = mtime
        self.mode = mode
        self.written = 0
        self._tmp: Optional[Path] = None
        self._f = None
        if target is not None:
            for i in range(1000):
                tmp = target.with_name(f".{target.name}.{i}.sandik-part")
                try:
                    self._f = open(tmp, "xb")
                    self._tmp = tmp
                    break
                except FileExistsError:
                    continue
            else:  # pragma: no cover
                raise OSError(f"cannot create temp file for {target}")

    def write(self, data) -> int:
        n = len(data)
        self.written += n
        self.ctx.account(n, self)
        if self._f is not None:
            self._f.write(data)
        return n

    def copy_from(self, src, chunk: int = CHUNK) -> None:
        while True:
            data = src.read(chunk)
            if not data:
                break
            self.write(data)

    def commit(self) -> None:
        self.ctx.files += 1
        if self._f is None:
            return
        self._f.close()
        os.replace(self._tmp, self.target)
        self._tmp = None
        if self.mode is not None and not IS_WINDOWS:
            # setuid/setgid/sticky bitleri asla uygulanmaz.
            try:
                os.chmod(self.target, (self.mode & 0o777) | stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        if self.mtime:
            try:
                os.utime(self.target, (self.mtime, self.mtime))
            except (OSError, OverflowError, ValueError):
                pass

    def discard(self) -> None:
        if self._f is not None:
            try:
                self._f.close()
            except OSError:
                pass
        if self._tmp is not None:
            try:
                os.unlink(self._tmp)
            except OSError:
                pass
            self._tmp = None

    def __enter__(self) -> "OutFile":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.discard()
        return False
