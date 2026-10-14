"""CHZ (ChestZip'in kendi biçimi) için güvenlik ve bütünlük testleri."""

import io
import os
import struct

import pytest

from chestzip.api import Archive, create_archive
from chestzip.backends import chz_backend as chz
from chestzip.errors import (ArchiveError, PasswordRequired, SafetyError, UnsupportedFormat,
                             WrongPassword)
from chestzip.safety import MiB


@pytest.fixture
def sample(tmp_path):
    src = tmp_path / "src" / "Gizli Proje"
    (src / "alt").mkdir(parents=True)
    (src / "rapor-çok-gizli.txt").write_text("merhaba " * 20000)
    (src / "alt" / "veri.bin").write_bytes(os.urandom(300_000))
    (src / "boş.txt").write_bytes(b"")
    return src


def _rewrite_index(path, mutate, mutate_blocks=None):
    """Veri alanını koruyup dizini değiştirerek kötü niyetli arşiv üretir."""
    r = chz.ChzReader(path)
    r.f.seek(r.data_start)
    data = r.f.read(r.index_offset - r.data_start)
    entries, blocks = r.entries, r.blocks
    r.close()
    w = chz.ChzWriter(path)
    w.f.write(data)
    w.entries = mutate(entries)
    w.blocks = mutate_blocks(blocks) if mutate_blocks else blocks
    w.close()


def test_roundtrip_and_extension(tmp_path, sample):
    out = create_archive(tmp_path / "a.chz", [sample])
    with Archive(out) as a:
        assert a.format == "chz" and a.format_name == "CHZ"
        a.extract(tmp_path / "dst")
    d = tmp_path / "dst" / "Gizli Proje"
    assert (d / "alt" / "veri.bin").read_bytes() == (sample / "alt" / "veri.bin").read_bytes()
    assert (d / "boş.txt").read_bytes() == b""
    # varsayılan biçim CHZ
    out2 = create_archive(tmp_path / "b.chz", [sample])
    assert out2.read_bytes()[:8] == chz.MAGIC


def test_multi_block_and_solid(tmp_path):
    f = tmp_path / "big.bin"
    f.write_bytes(os.urandom(150_000) + b"\0" * 300_000)
    out = tmp_path / "m.chz"
    w = chz.ChzWriter(out, block_size=64 * 1024)
    for i in range(20):  # küçük dosyalar aynı blokta toplanmalı
        w.add_file(io.BytesIO(b"kucuk %d " % i * 50), f"k{i}.txt")
    with open(f, "rb") as src:
        w.add_file(src, "big.bin")
    w.close()
    r = chz.ChzReader(out)
    smalls = [e for e in r.entries if e["n"].startswith("k")]
    assert len({sg[0] for e in smalls for sg in e["g"]}) == 1  # tek blok (solid)
    big = next(e for e in r.entries if e["n"] == "big.bin")
    assert len(big["g"]) > 5
    assert b"".join(r.iter_data(big)) == f.read_bytes()
    assert b"".join(r.iter_data(smalls[3])) == b"kucuk 3 " * 50
    r.close()


def test_delete_from_shared_block_compacts(tmp_path):
    src = tmp_path / "s"
    src.mkdir()
    for i in range(30):
        (src / f"f{i}.txt").write_text(f"dosya {i} " * 2000)
    out = create_archive(tmp_path / "d.chz", [src])
    before = out.stat().st_size
    a = Archive(out)
    a.delete([f"s/f{i}.txt" for i in range(15)])
    assert out.stat().st_size < before
    res = a.extract(tmp_path / "dst")
    assert res.files == 15
    assert (tmp_path / "dst/s/f20.txt").read_text() == "dosya 20 " * 2000


def test_encrypted_hides_names(tmp_path, sample):
    out = create_archive(tmp_path / "e.chz", [sample], password="çok gizli şifre")
    blob = out.read_bytes()
    assert b"rapor" not in blob and "rapor".encode("utf-16-le") not in blob
    with pytest.raises(PasswordRequired):
        Archive(out).entries()
    with pytest.raises(WrongPassword):
        Archive(out, password="yanlış").entries()
    names = {e.name for e in Archive(out, password="çok gizli şifre").entries()}
    assert "Gizli Proje/rapor-çok-gizli.txt" in names


def test_tampered_data_detected(tmp_path, sample):
    out = create_archive(tmp_path / "t.chz", [sample], level=0)
    raw = bytearray(out.read_bytes())
    pos = raw.find(b"merhaba merhaba")
    raw[pos] ^= 0xFF
    out.write_bytes(bytes(raw))
    with Archive(out) as a, pytest.raises(ArchiveError):
        a.extract(tmp_path / "dst")
    assert not [p for p in (tmp_path / "dst").rglob("*.txt") if p.stat().st_size]


def test_tampered_encrypted_chunk_detected(tmp_path, sample):
    out = create_archive(tmp_path / "t.chz", [sample], password="pw")
    raw = bytearray(out.read_bytes())
    raw[200] ^= 0x01  # veri alanında bir bayt
    out.write_bytes(bytes(raw))
    with pytest.raises(ArchiveError):
        Archive(out, password="pw").extract(tmp_path / "dst")


def test_overlapping_chunks_rejected(tmp_path, sample):
    out = create_archive(tmp_path / "o.chz", [sample])

    def mutate(entries):
        f = next(e for e in entries if e["t"] == "f" and e["s"])
        clones = []
        for i in range(50):  # aynı veriyi 50 kez gösteren kayıtlar
            c = dict(f)
            c["n"] = f"kopya{i}.txt"
            clones.append(c)
        return entries + clones

    _rewrite_index(out, mutate)
    with pytest.raises(SafetyError):
        Archive(out).entries()


def test_block_lying_about_size(tmp_path):
    f = tmp_path / "z.bin"
    f.write_bytes(b"\0" * (8 * MiB))
    out = create_archive(tmp_path / "z.chz", [f])

    def mutate_blocks(blocks):
        for b in blocks:
            b[2] = 1024  # "açılınca 1 KB" diye yalan söyle
        return blocks

    def mutate(entries):
        e = entries[0]
        e["g"] = [[bi, 0, 1024] for bi, _so, _sl in e["g"]]
        e["s"] = 1024 * len(e["g"])
        return entries

    _rewrite_index(out, mutate, mutate_blocks)
    with Archive(out) as a, pytest.raises(SafetyError):
        a.extract(tmp_path / "dst")
    assert not (tmp_path / "dst" / "z.bin").exists()


def test_huge_block_declaration_rejected(tmp_path, sample):
    out = create_archive(tmp_path / "h.chz", [sample])

    def mutate_blocks(blocks):
        blocks[0][2] = 10 * 1024 * MiB
        return blocks

    _rewrite_index(out, lambda e: e, mutate_blocks)
    with pytest.raises(SafetyError):
        Archive(out).entries()


def test_scrypt_dos_rejected(tmp_path, sample):
    out = create_archive(tmp_path / "s.chz", [sample], password="pw")
    raw = bytearray(out.read_bytes())
    raw[chz.HEADER.size + 16] = 30  # N = 2^30 -> devasa bellek
    out.write_bytes(bytes(raw))
    with pytest.raises(SafetyError):
        Archive(out, password="pw").entries()


def test_future_version_and_truncation(tmp_path, sample):
    out = create_archive(tmp_path / "v.chz", [sample])
    raw = bytearray(out.read_bytes())
    raw[8] = 99
    (tmp_path / "v2.chz").write_bytes(bytes(raw))
    with pytest.raises(UnsupportedFormat):
        Archive(tmp_path / "v2.chz").entries()
    (tmp_path / "t.chz").write_bytes(out.read_bytes()[:-10])
    with pytest.raises(ArchiveError):
        Archive(tmp_path / "t.chz").entries()


def test_zip_slip_in_chz(tmp_path, sample):
    out = create_archive(tmp_path / "s.chz", [sample])

    def mutate(entries):
        for e in entries:
            if e["t"] == "f":
                e["n"] = "../../" + e["n"]
        return entries

    _rewrite_index(out, mutate)
    dst = tmp_path / "x" / "dst"
    res = Archive(out).extract(dst)
    assert res.files == 0 and res.skipped >= 3
    assert not list((tmp_path).glob("Gizli Proje"))


def test_footer_struct_size():
    assert chz.FOOTER.size == 48 and chz.HEADER.size == 16 and chz.KDF.size == 20
    assert struct.calcsize("<QQQ12s") == 36
