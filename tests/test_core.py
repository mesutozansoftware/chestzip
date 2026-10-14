import gzip
import io
import os
import struct
import tarfile
import zipfile
import zlib
from pathlib import Path

import pytest

from chestzip.api import Archive, create_archive
from chestzip.errors import (PasswordRequired, SafetyError, UnsupportedOperation, WrongPassword)
from chestzip.safety import CancelToken, Limits, MiB

FORMATS = ["chz", "zip", "7z", "tar", "tar.gz", "tar.bz2", "tar.xz"]


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "src" / "Proje"
    (root / "alt klasör").mkdir(parents=True)
    (root / "boş").mkdir()
    (root / "a.txt").write_text("merhaba dünya\n" * 100, encoding="utf-8")
    (root / "alt klasör" / "ğüşiöç.bin").write_bytes(os.urandom(200_000))
    return root


def _snapshot(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        out[rel] = None if p.is_dir() else p.read_bytes()
    return out


@pytest.mark.parametrize("fmt", FORMATS)
def test_roundtrip(tmp_path, tree, fmt):
    out = tmp_path / f"arsiv.{fmt}"
    create_archive(out, [tree], fmt=fmt, level=5)
    with Archive(out) as a:
        assert a.format == fmt
        names = {e.name for e in a.entries()}
        assert "Proje/alt klasör/ğüşiöç.bin" in names
        assert a.test().files == 2
        res = a.extract(tmp_path / "dst")
    assert res.files == 2
    assert _snapshot(tmp_path / "dst" / "Proje") == _snapshot(tree)


@pytest.mark.parametrize("fmt", ["gz", "bz2", "xz"])
def test_single_stream(tmp_path, fmt):
    f = tmp_path / "veri.txt"
    f.write_bytes(b"abc" * 10000)
    out = tmp_path / f"veri.txt.{fmt}"
    create_archive(out, [f], fmt=fmt)
    with Archive(out) as a:
        assert a.format == fmt
        a.extract(tmp_path / "dst")
    assert (tmp_path / "dst" / "veri.txt").read_bytes() == f.read_bytes()


@pytest.mark.parametrize("fmt", ["chz", "zip", "7z"])
def test_password(tmp_path, tree, fmt):
    out = tmp_path / f"gizli.{fmt}"
    create_archive(out, [tree], fmt=fmt, password="S3cret!")
    a = Archive(out)
    assert a.needs_password()
    with pytest.raises(PasswordRequired):
        a.extract(tmp_path / "x")
    a.set_password("yanlis")
    with pytest.raises((WrongPassword, PasswordRequired)):
        a.extract(tmp_path / "y")
    a.set_password("S3cret!")
    a.extract(tmp_path / "dst")
    assert _snapshot(tmp_path / "dst" / "Proje") == _snapshot(tree)


def test_zip_aes_is_not_plain(tmp_path, tree):
    out = tmp_path / "g.zip"
    create_archive(out, [tree], fmt="zip", password="pw")
    with zipfile.ZipFile(out) as zf:
        info = [i for i in zf.infolist() if not i.is_dir()][0]
        assert info.flag_bits & 1
        assert info.compress_type == 99  # WinZip AES


# ---------------------------------------------------------------- güvenlik

def test_zip_slip_is_blocked(tmp_path):
    out = tmp_path / "evil.zip"
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("../../kotu.txt", b"pwned")
        zf.writestr("/etc/mutlak.txt", b"abs")
        zf.writestr("..\\..\\win.txt", b"win")
        zf.writestr("iyi.txt", b"ok")
    dst = tmp_path / "a" / "b" / "dst"
    with Archive(out) as a:
        assert a.analyze().warnings  # uyarı verir
        res = a.extract(dst)
    assert (dst / "iyi.txt").read_bytes() == b"ok"
    assert (dst / "etc" / "mutlak.txt").exists()  # mutlak yol hedef içine alınır
    assert not (tmp_path / "a" / "kotu.txt").exists()
    assert not (tmp_path / "a" / "win.txt").exists()
    assert res.skipped == 2


def test_tar_symlink_escape_blocked(tmp_path):
    out = tmp_path / "evil.tar"
    with tarfile.open(out, "w") as tf:
        ti = tarfile.TarInfo("link")
        ti.type, ti.linkname = tarfile.SYMTYPE, "/etc"
        tf.addfile(ti)
        data = b"root::0:0"
        ti = tarfile.TarInfo("link/passwd")
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))
    dst = tmp_path / "dst"
    with Archive(out, limits=Limits(allow_symlinks=True)) as a:
        res = a.extract(dst)
    assert not (dst / "link").is_symlink()
    assert res.warnings


def _zeros_zip(path: Path, size: int) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        with zf.open("zeros.bin", "w", force_zip64=True) as f:
            chunk = b"\0" * MiB
            for _ in range(size // MiB):
                f.write(chunk)


def test_ratio_bomb_header_check(tmp_path):
    bomb = tmp_path / "bomb.zip"
    _zeros_zip(bomb, 200 * MiB)
    with Archive(bomb, limits=Limits(max_ratio=100, ratio_grace=8 * MiB)) as a:
        assert not a.analyze().ok
        with pytest.raises(SafetyError):
            a.extract(tmp_path / "dst")
    assert not any((tmp_path / "dst").rglob("*.bin"))


def test_lying_header_stream_check(tmp_path):
    """Başlıkta küçük boyut yazan ama büyük açılan gz akışı (tar.gz bombası)."""
    bomb = tmp_path / "bomb.tar.gz"
    with gzip.open(bomb, "wb", compresslevel=9) as g:
        ti = tarfile.TarInfo("zeros.bin")
        ti.size = 300 * MiB
        g.write(ti.tobuf(format=tarfile.PAX_FORMAT))
        chunk = b"\0" * MiB
        for _ in range(300):
            g.write(chunk)
    dst = tmp_path / "dst"
    limits = Limits(max_ratio=100, ratio_grace=16 * MiB)
    with Archive(bomb, limits=limits) as a:
        with pytest.raises(SafetyError):
            a.extract(dst)
    leftovers = [p for p in dst.rglob("*") if p.is_file()]
    assert leftovers == []  # yarım dosya silinmiş olmalı


def test_total_size_limit(tmp_path):
    bomb = tmp_path / "big.zip"
    _zeros_zip(bomb, 40 * MiB)
    with Archive(bomb, limits=Limits(max_total_size=10 * MiB)) as a:
        with pytest.raises(SafetyError):
            a.extract(tmp_path / "dst")


def test_entry_count_limit(tmp_path):
    out = tmp_path / "many.zip"
    with zipfile.ZipFile(out, "w") as zf:
        for i in range(60):
            zf.writestr(f"f{i}.txt", b"x")
    with Archive(out, limits=Limits(max_entries=50)) as a:
        with pytest.raises(SafetyError):
            a.extract(tmp_path / "dst")


def _overlap_bomb(path: Path, copies: int = 20) -> None:
    """Fifield tipi özyinelemesiz bomba: tüm merkezi kayıtlar aynı veriyi gösterir."""
    raw = zlib.compressobj(9, zlib.DEFLATED, -15)
    payload = raw.compress(b"\0" * (4 * MiB)) + raw.flush()
    crc = zlib.crc32(b"\0" * (4 * MiB))
    name = b"k.bin"
    local = struct.pack("<4sHHHHHIIIHH", b"PK\x03\x04", 20, 0, 8, 0, 0, crc, len(payload),
                        4 * MiB, len(name), 0) + name
    body = local + payload
    central = b""
    for i in range(copies):
        n = f"k{i}.bin".encode()
        central += struct.pack("<4sHHHHHHIIIHHHHHII", b"PK\x01\x02", 20, 20, 0, 8, 0, 0, crc,
                               len(payload), 4 * MiB, len(n), 0, 0, 0, 0, 0, 0) + n
    end = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, copies, copies, len(central),
                      len(body), 0)
    path.write_bytes(body + central + end)


def test_overlapping_zip_bomb(tmp_path):
    bomb = tmp_path / "overlap.zip"
    _overlap_bomb(bomb)
    with Archive(bomb) as a:
        report = a.analyze()
        assert not report.ok
        with pytest.raises(SafetyError):
            a.extract(tmp_path / "dst")


def test_disabled_limits_still_block_traversal(tmp_path):
    out = tmp_path / "evil.zip"
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("../x.txt", b"pwned")
    with Archive(out, limits=Limits.unlimited()) as a:
        a.extract(tmp_path / "dst")
    assert not (tmp_path / "x.txt").exists()


# ---------------------------------------------------------------- işlemler

@pytest.mark.parametrize("fmt", ["chz", "zip", "tar.gz"])
def test_delete_and_add(tmp_path, tree, fmt):
    out = tmp_path / f"d.{fmt}"
    create_archive(out, [tree], fmt=fmt)
    with Archive(out) as a:
        a.delete(["Proje/alt klasör"])
        names = {e.name for e in a.entries()}
        assert not any(n.startswith("Proje/alt klasör") for n in names)
        extra = tmp_path / "yeni.txt"
        extra.write_text("yeni")
        a.add([extra])
        assert "yeni.txt" in {e.name for e in a.entries()}
        assert a.test().files == 2


@pytest.mark.parametrize("fmt", ["zip", "chz"])
def test_delete_encrypted_keeps_data(tmp_path, tree, fmt):
    out = tmp_path / f"enc.{fmt}"
    create_archive(out, [tree], fmt=fmt, password="pw")
    a = Archive(out, password="pw")
    a.delete(["Proje/a.txt"])
    a.extract(tmp_path / "dst")
    assert (tmp_path / "dst/Proje/alt klasör/ğüşiöç.bin").read_bytes() == \
        (tree / "alt klasör" / "ğüşiöç.bin").read_bytes()


def test_overwrite_modes(tmp_path, tree):
    out = tmp_path / "o.zip"
    create_archive(out, [tree / "a.txt"], fmt="zip")
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "a.txt").write_text("eski")
    with Archive(out) as a:
        a.extract(dst, overwrite="never")
        assert (dst / "a.txt").read_text() == "eski"
        a.extract(dst, overwrite="rename")
        assert (dst / "a (1).txt").exists()
        a.extract(dst, overwrite="always")
        assert (dst / "a.txt").read_text() != "eski"


def test_cancel(tmp_path, tree):
    out = tmp_path / "c.zip"
    create_archive(out, [tree], fmt="zip")
    tok = CancelToken()
    tok.cancel()
    from chestzip.errors import Cancelled
    with Archive(out) as a, pytest.raises(Cancelled):
        a.extract(tmp_path / "dst", cancel=tok)


def test_rar_create_refused(tmp_path, tree):
    with pytest.raises(UnsupportedOperation):
        create_archive(tmp_path / "x.rar", [tree], fmt="rar")


@pytest.mark.parametrize("fmt", ["chz", "7z", "zip", "tar.xz"])
def test_cancel_midstream_leaves_no_partial(tmp_path, fmt):
    src = tmp_path / "big.bin"
    src.write_bytes(os.urandom(6 * MiB))
    out = tmp_path / f"b.{fmt}"
    create_archive(out, [src], fmt=fmt, level=1)
    tok = CancelToken()

    def progress(done, total, name):
        tok.cancel()  # ilk bildirimde iptal et

    from chestzip.errors import Cancelled
    dst = tmp_path / "dst"
    with Archive(out) as a, pytest.raises(Cancelled):
        a.extract(dst, progress=progress, cancel=tok)
    assert [p for p in dst.rglob("*") if p.is_file()] == []


def test_7z_stream_limit(tmp_path):
    """7z içinde başlık kontrolü kapalı olsa bile akış sınırı devrede."""
    src = tmp_path / "z.bin"
    src.write_bytes(b"\0" * (30 * MiB))
    out = tmp_path / "z.7z"
    create_archive(out, [src], fmt="7z")
    a = Archive(out, limits=Limits(max_total_size=10 * MiB))
    from chestzip.safety import ExtractContext
    ctx = ExtractContext(tmp_path / "dst", a.limits, a.size)
    with pytest.raises(SafetyError):
        a.backend.extract(ctx, None)  # ön kontrolü atlayıp doğrudan akışı dene
    assert [p for p in (tmp_path / "dst").rglob("*") if p.is_file()] == []
