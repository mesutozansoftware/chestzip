"""CHZ — ChestZip'in kendi arşiv biçimi (.chz).

Açık ve belgeli bir biçimdir; ayrıntılı tanım: docs/CHZ_FORMAT.md

Yerleşim::

    [başlık 16 B][şifreleme bloğu 20 B, şifreliyse][bloklar ...][dizin][son ek 48 B]

* Dosya verileri art arda eklenip en fazla ``BLOCK`` baytlık **solid bloklara**
  bölünür; küçük dosyalar aynı blokta birlikte sıkıştırılır (yüksek oran),
  büyük dosyalar birden çok bloğa yayılır. Her blok bağımsız olarak LZMA2 ile
  sıkıştırılır (küçülmüyorsa sıkıştırmadan saklanır), böylece tek bir dosyayı
  açmak için en fazla ilgili bloklar açılır.
* Her dosya, blok içi parçalar (segment) listesiyle tanımlanır ve BLAKE2b-256
  özetiyle doğrulanır.
* Şifreliyse her blok AES-256-GCM ile şifrelenir; anahtar parola + rastgele tuz
  ile scrypt'ten türetilir. Dizin (dosya adları dahil) de şifrelenir.

Güvenlik (zip bombası) açısından:

* Blok başına açılmış boyut ``MAX_BLOCK`` ile sınırlıdır; açıcı bildirilenden
  fazla veri üretemez (``max_length``), LZMA2 sözlüğü blok boyutuyla sınırlıdır.
* Bloklar dosyada üst üste binemez; bir bloğun her baytı en fazla **bir**
  dosyaya ait olabilir. Böylece aynı veriyi binlerce dosyaya gösterip
  çoğaltma (özyinelemesiz zip bombası) mümkün değildir.
* Dizin boyutu ve scrypt parametreleri üst sınırlıdır (kaynak tüketme saldırısı).
"""

from __future__ import annotations

import hashlib
import json
import lzma
import os
import secrets
import struct
import tempfile
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from ..errors import (ArchiveError, PasswordRequired, SafetyError, UnsupportedFormat,
                      WrongPassword)
from ..i18n import t
from ..safety import CancelToken, ExtractContext, MiB, ProgressFn
from .base import AddProgress, Backend, Entry, Source, make_entry

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover
    AESGCM = None
    InvalidTag = Exception

MAGIC = b"CHZ!\x1a\r\n\x00"
END_MAGIC = b"CHZ-END\x00"
VERSION = 1
FLAG_ENCRYPTED = 0x01
HEADER = struct.Struct("<8sBB6x")              # magic, sürüm, bayraklar
KDF = struct.Struct("<16sBBBx")                # tuz, log2(N), r, p
FOOTER = struct.Struct("<QQQ12sI8s")           # dizin ofseti, saklı, ham, nonce, crc, magic

BLOCK = 8 * MiB                                # yazarken blok boyutu
MAX_BLOCK = 64 * MiB                           # okurken kabul edilen en büyük blok
MAX_INDEX = 256 * MiB                          # açılmış dizin üst sınırı
METHOD_STORE = 0
METHOD_LZMA2 = 1
TAG = 16                                       # AES-GCM doğrulama etiketi
SCRYPT_DEFAULT = (15, 8, 1)                    # N=2^15, r=8, p=1  (~32 MB bellek)
SCRYPT_MAX = (20, 16, 4)
INDEX_AAD = b"CHZ1-index"
BLOCK_AAD = b"CHZ1-block"


def _dict_size(raw_len: int) -> int:
    # LZMA2 sözlüğü veri boyutundan büyük olamaz -> açarken bellek sınırlı.
    return max(4096, 1 << max(12, (max(raw_len, 1) - 1).bit_length()))


def derive_key(password: str, salt: bytes, params: tuple[int, int, int]) -> bytes:
    log_n, r, p = params
    if log_n > SCRYPT_MAX[0] or r > SCRYPT_MAX[1] or p > SCRYPT_MAX[2] or log_n < 10 \
            or r < 1 or p < 1:
        raise SafetyError(t("err.corrupt", detail="scrypt parameters out of range"))
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=1 << log_n, r=r, p=p,
                          maxmem=256 * MiB, dklen=32)


@dataclass
class KeyMaterial:
    salt: bytes
    params: tuple[int, int, int]
    key: bytes

    @classmethod
    def new(cls, password: str) -> "KeyMaterial":
        if AESGCM is None:  # pragma: no cover
            raise ArchiveError("cryptography is required for encrypted CHZ")
        salt = secrets.token_bytes(16)
        return cls(salt, SCRYPT_DEFAULT, derive_key(password, salt, SCRYPT_DEFAULT))


def _bad(detail: str) -> ArchiveError:
    return ArchiveError(t("err.corrupt", detail=detail))


def _decompress(blob: bytes, raw: int) -> bytes:
    d = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
        "id": lzma.FILTER_LZMA2, "dict_size": _dict_size(raw)}])
    try:
        out = d.decompress(blob, max_length=raw)
        if len(out) == raw and not d.eof:
            # Bitiş işaretini işlet; ek veri çıkarsa blok bildirilenden büyüktür.
            out += d.decompress(b"", max_length=1)
    except lzma.LZMAError as e:
        raise _bad(str(e)) from e
    if len(out) != raw or not d.eof:
        # Bildirilenden fazla/az veri: bozuk ya da bomba girişimi.
        raise SafetyError(t("err.corrupt", detail="block size mismatch"))
    return out


# --------------------------------------------------------------------------
# Yazıcı
# --------------------------------------------------------------------------

class ChzWriter:
    def __init__(self, path: str | Path, keymat: Optional[KeyMaterial] = None,
                 level: int = 5, block_size: int = BLOCK) -> None:
        self.f = open(path, "wb")
        self.keymat = keymat
        self.aes = AESGCM(keymat.key) if keymat else None
        self.level = min(max(level, 0), 9)
        self.block_size = block_size
        self.blocks: list[list] = []
        self.entries: list[dict] = []
        self.buf = bytearray()
        flags = FLAG_ENCRYPTED if keymat else 0
        self.f.write(HEADER.pack(MAGIC, VERSION, flags))
        if keymat:
            self.f.write(KDF.pack(keymat.salt, *keymat.params))

    def flush(self) -> None:
        """Bekleyen veriyi bir blok olarak sıkıştırıp yazar."""
        if not self.buf:
            return
        data = bytes(self.buf)
        self.buf.clear()
        method, payload = METHOD_STORE, data
        if self.level > 0:
            comp = lzma.compress(data, format=lzma.FORMAT_RAW, filters=[{
                "id": lzma.FILTER_LZMA2, "preset": self.level,
                "dict_size": _dict_size(len(data))}])
            if len(comp) < len(data):
                method, payload = METHOD_LZMA2, comp
        nonce = ""
        if self.aes:
            n = secrets.token_bytes(12)
            payload = self.aes.encrypt(n, payload, BLOCK_AAD)
            nonce = n.hex()
        self.blocks.append([self.f.tell(), len(payload), len(data), method, nonce])
        self.f.write(payload)

    def add_file(self, src, name: str, mtime: Optional[float] = None,
                 mode: Optional[int] = None, on_read=None,
                 cancel: Optional[CancelToken] = None) -> None:
        h = hashlib.blake2b(digest_size=32)
        segs: list[list[int]] = []
        size = 0
        while True:
            if cancel:
                cancel.check()
            room = self.block_size - len(self.buf)
            data = src.read(room)
            if not data:
                break
            h.update(data)
            size += len(data)
            segs.append([len(self.blocks), len(self.buf), len(data)])
            self.buf += data
            if len(self.buf) >= self.block_size:
                self.flush()
            if on_read:
                on_read(len(data))
        self.entries.append({"n": name, "t": "f", "s": size, "m": mtime, "p": mode,
                             "h": h.hexdigest(), "g": segs})

    def add_dir(self, name: str, mtime: Optional[float] = None) -> None:
        self.entries.append({"n": name, "t": "d", "m": mtime})

    def copy_block(self, reader: "ChzReader", idx: int) -> int:
        """Bir bloğu açmadan, ham olarak kopyalar (aynı anahtar gerekir)."""
        self.flush()
        off, stored, raw, method, nonce = reader.blocks[idx]
        reader.f.seek(off)
        data = reader.f.read(stored)
        if len(data) != stored:
            raise _bad("truncated block")
        self.blocks.append([self.f.tell(), stored, raw, method, nonce])
        self.f.write(data)
        return len(self.blocks) - 1

    def close(self) -> None:
        self.flush()
        raw = json.dumps({"v": VERSION, "b": self.blocks, "e": self.entries},
                         ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        stored = lzma.compress(raw, format=lzma.FORMAT_RAW, filters=[{
            "id": lzma.FILTER_LZMA2, "preset": 6, "dict_size": _dict_size(len(raw))}])
        nonce = b"\0" * 12
        if self.aes:
            nonce = secrets.token_bytes(12)
            stored = self.aes.encrypt(nonce, stored, INDEX_AAD)
        off = self.f.tell()
        self.f.write(stored)
        head = struct.pack("<QQQ12s", off, len(stored), len(raw), nonce)
        self.f.write(FOOTER.pack(off, len(stored), len(raw), nonce, zlib.crc32(head),
                                 END_MAGIC))
        self.f.close()

    def abort(self) -> None:
        self.f.close()


# --------------------------------------------------------------------------
# Okuyucu
# --------------------------------------------------------------------------

class ChzReader:
    def __init__(self, path: str | Path, password: Optional[str] = None) -> None:
        self.path = Path(path)
        self.f = open(self.path, "rb")
        self._cache: tuple[int, bytes] = (-1, b"")
        try:
            self._load(password)
        except BaseException:
            self.f.close()
            raise

    def _load(self, password: Optional[str]) -> None:
        size = self.path.stat().st_size
        head = self.f.read(HEADER.size)
        if len(head) < HEADER.size or head[:8] != MAGIC:
            raise UnsupportedFormat(t("err.unknown_format", path=self.path))
        _magic, version, flags = HEADER.unpack(head)
        if version > VERSION:
            raise UnsupportedFormat(t("err.unknown_format", path=self.path) +
                                    f" (CHZ v{version})")
        self.encrypted = bool(flags & FLAG_ENCRYPTED)
        self.keymat: Optional[KeyMaterial] = None
        self.data_start = HEADER.size
        salt = params = None
        if self.encrypted:
            kdf = self.f.read(KDF.size)
            if len(kdf) < KDF.size:
                raise _bad("truncated header")
            salt, *params = KDF.unpack(kdf)
            params = tuple(params)
            self.data_start += KDF.size
        if size < self.data_start + FOOTER.size:
            raise _bad("truncated archive")
        self.f.seek(size - FOOTER.size)
        off, stored, raw, nonce, crc, end = FOOTER.unpack(self.f.read(FOOTER.size))
        if end != END_MAGIC or \
                zlib.crc32(struct.pack("<QQQ12s", off, stored, raw, nonce)) != crc:
            raise _bad("bad footer")
        if off < self.data_start or off + stored != size - FOOTER.size:
            raise _bad("bad index location")
        if raw > MAX_INDEX:
            raise SafetyError(t("err.corrupt", detail="index too large"))
        self.index_offset = off
        self.aes = None
        if self.encrypted:
            if not password:
                raise PasswordRequired(t("err.password_required"))
            self.keymat = KeyMaterial(salt, params, derive_key(password, salt, params))
            self.aes = AESGCM(self.keymat.key)
        self.f.seek(off)
        blob = self.f.read(stored)
        if self.aes:
            try:
                blob = self.aes.decrypt(nonce, blob, INDEX_AAD)
            except InvalidTag as e:
                raise WrongPassword(t("err.wrong_password")) from e
        data = _decompress(blob, raw)
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise _bad("bad index") from e
        self._validate(doc)

    def _validate(self, doc) -> None:
        if not isinstance(doc, dict) or not isinstance(doc.get("b"), list) or \
                not isinstance(doc.get("e"), list):
            raise _bad("bad index")
        blocks = doc["b"]
        spans = []
        for b in blocks:
            if (not isinstance(b, list) or len(b) != 5 or
                    not all(isinstance(x, int) and x >= 0 for x in b[:4]) or
                    not isinstance(b[4], str)):
                raise _bad("bad block")
            off, stored, raw, method, nonce = b
            if method not in (METHOD_STORE, METHOD_LZMA2):
                raise _bad("unknown method")
            if raw > MAX_BLOCK:
                raise SafetyError(t("err.corrupt", detail="block too large"))
            if off < self.data_start or off + stored > self.index_offset:
                raise _bad("block outside data area")
            overhead = TAG if self.aes else 0
            if method == METHOD_STORE and stored != raw + overhead:
                raise _bad("bad stored block")
            if self.aes and len(nonce) != 24:
                raise _bad("bad nonce")
            spans.append((off, off + stored))
        spans.sort()
        for (_s1, e1), (s2, _e2) in zip(spans, spans[1:]):
            if s2 < e1:
                raise SafetyError(t("sec.overlap"))

        used: list[tuple[int, int, int]] = []
        entries = []
        for e in doc["e"]:
            if not isinstance(e, dict) or not isinstance(e.get("n"), str) or \
                    e.get("t") not in ("f", "d"):
                raise _bad("bad entry")
            if e["t"] == "f":
                segs = e.get("g")
                if not isinstance(segs, list) or not isinstance(e.get("s"), int):
                    raise _bad("bad entry")
                total = 0
                for sg in segs:
                    if (not isinstance(sg, list) or len(sg) != 3 or
                            not all(isinstance(x, int) and x >= 0 for x in sg)):
                        raise _bad("bad segment")
                    bi, so, sl = sg
                    if bi >= len(blocks) or so + sl > blocks[bi][2]:
                        raise _bad("segment outside block")
                    used.append((bi, so, so + sl))
                    total += sl
                if total != e["s"]:
                    raise _bad("size mismatch")
                if not isinstance(e.get("h"), str) or len(e["h"]) != 64:
                    raise _bad("bad checksum")
            entries.append(e)
        # Bir bloğun her baytı en fazla bir dosyaya ait olabilir (çoğaltma bombası).
        used.sort()
        for (b1, _s1, e1), (b2, s2, _e2) in zip(used, used[1:]):
            if b1 == b2 and s2 < e1:
                raise SafetyError(t("sec.overlap"))
        self.blocks = blocks
        self.entries = entries

    def read_block(self, idx: int) -> bytes:
        if self._cache[0] == idx:
            return self._cache[1]
        off, stored, raw, method, nonce = self.blocks[idx]
        self.f.seek(off)
        data = self.f.read(stored)
        if len(data) != stored:
            raise _bad("truncated block")
        if self.aes:
            try:
                data = self.aes.decrypt(bytes.fromhex(nonce), data, BLOCK_AAD)
            except InvalidTag as err:
                raise _bad("block authentication failed") from err
        if method == METHOD_LZMA2:
            data = _decompress(data, raw)
        elif len(data) != raw:
            raise _bad("bad stored block")
        self._cache = (idx, data)
        return data

    def iter_data(self, e: dict, cancel: Optional[CancelToken] = None) -> Iterator[bytes]:
        h = hashlib.blake2b(digest_size=32)
        for bi, so, sl in e["g"]:
            if cancel:
                cancel.check()
            data = self.read_block(bi)[so:so + sl]
            h.update(data)
            yield data
        if h.hexdigest() != e["h"]:
            raise _bad(f"checksum mismatch: {e['n']}")

    def close(self) -> None:
        self._cache = (-1, b"")
        self.f.close()


# --------------------------------------------------------------------------
# Arka uç
# --------------------------------------------------------------------------

def _mtime(ts) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(ts) if ts is not None else None
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def needs_password_file(path: Path) -> bool:
    with open(path, "rb") as f:
        head = f.read(HEADER.size)
    return len(head) == HEADER.size and bool(HEADER.unpack(head)[2] & FLAG_ENCRYPTED)


class ChzBackend(Backend):
    format_name = "CHZ"
    can_delete = True
    can_add = True
    can_encrypt = True

    def __init__(self, path, password=None) -> None:
        super().__init__(path, password)
        self._reader: Optional[ChzReader] = None
        self._entries: Optional[list[Entry]] = None

    def _open(self) -> ChzReader:
        if self._reader is None:
            self._reader = ChzReader(self.path, self.password)
        return self._reader

    def needs_password(self) -> bool:
        return needs_password_file(self.path)

    def entries(self) -> list[Entry]:
        if self._entries is None:
            r = self._open()
            out = []
            for e in r.entries:
                is_dir = e["t"] == "d"
                mode = e.get("p")
                out.append(make_entry(
                    e["n"], is_dir=is_dir, size=0 if is_dir else e["s"],
                    # Solid bloklarda dosya başına sıkışık boyut bilinemez.
                    packed=None, mtime=_mtime(e.get("m")), encrypted=r.encrypted,
                    kind="dir" if is_dir else "file",
                    mode=mode if isinstance(mode, int) else None, ref=e))
            self._entries = out
        return self._entries

    def extract(self, ctx: ExtractContext, names=None) -> None:
        r = self._open()
        for ent in self.entries():
            if names is not None and ent.name not in names:
                continue
            ctx.begin_entry(ent.name)
            if ent.is_dir:
                ctx.make_dir(ent.raw_name, ent.timestamp)
                continue
            out = ctx.open_file(ent.raw_name, mtime=ent.timestamp, mode=ent.mode)
            if out is None:
                continue
            with out:
                for data in r.iter_data(ent.ref, ctx.cancel):
                    out.write(data)
        ctx.finish()

    def _rebuild(self, drop: set[str], sources: list[Source], level: int,
                 progress: Optional[ProgressFn], cancel: Optional[CancelToken]) -> None:
        """Silme/ekleme için arşivi yeniden yazar.

        Silinen dosyaların bulunmadığı bloklar açılmadan ham kopyalanır; silinen
        veriyle blok paylaşan dosyalar yeniden sıkıştırılır (boşluk kalmaz)."""
        r = self._open()
        removed = drop | {s.arcname for s in sources}
        dirty = {sg[0] for e in r.entries if e["t"] == "f" and e["n"] in removed
                 for sg in e["g"]}
        fd, tmp = tempfile.mkstemp(prefix=".chestzip-", suffix=".chz", dir=self.path.parent)
        os.close(fd)
        w = ChzWriter(tmp, r.keymat, level)
        try:
            remap: dict[int, int] = {}
            for e in r.entries:
                if e["n"] in removed:
                    continue
                if cancel:
                    cancel.check()
                if e["t"] == "d":
                    w.entries.append(dict(e))
                elif any(sg[0] in dirty for sg in e["g"]):
                    w.add_file(_Chain(r.iter_data(e, cancel)), e["n"], e.get("m"), e.get("p"))
                else:
                    segs = []
                    for bi, so, sl in e["g"]:
                        if bi not in remap:
                            remap[bi] = w.copy_block(r, bi)
                        segs.append([remap[bi], so, sl])
                    new = dict(e)
                    new["g"] = segs
                    w.entries.append(new)
            _write_sources(w, sources, progress, cancel)
            w.close()
            self.close()
            os.replace(tmp, self.path)
        except BaseException:
            w.abort()
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        self._entries = None

    def delete(self, names: set[str], cancel: Optional[CancelToken] = None) -> None:
        self._rebuild(set(names), [], 5, None, cancel)

    def add(self, sources, level=5, progress=None, cancel=None) -> None:
        self._rebuild(set(), sources, level, progress, cancel)

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None


class _Chain:
    """Bayt parçaları üreten bir yineleyiciyi read() arayüzüne çevirir."""

    def __init__(self, it: Iterator[bytes]) -> None:
        self.it = it
        self.buf = b""

    def read(self, n: int) -> bytes:
        while len(self.buf) < n:
            try:
                self.buf += next(self.it)
            except StopIteration:
                break
        out, self.buf = self.buf[:n], self.buf[n:]
        return out


def _write_sources(w: ChzWriter, sources: list[Source], progress, cancel) -> None:
    tracker = AddProgress(sources, progress)
    for s in sources:
        if cancel:
            cancel.check()
        tracker.start(s.arcname)
        st = os.stat(s.path)
        if s.is_dir:
            w.add_dir(s.arcname, st.st_mtime)
            continue
        with open(s.path, "rb") as f:
            w.add_file(f, s.arcname, st.st_mtime, st.st_mode & 0o777, tracker, cancel)


def create_chz(out_path, sources: list[Source], level=5, password=None, progress=None,
               cancel=None) -> None:
    keymat = KeyMaterial.new(password) if password else None
    w = ChzWriter(out_path, keymat, level)
    try:
        _write_sources(w, sources, progress, cancel)
        w.close()
    except BaseException:
        w.abort()
        raise
