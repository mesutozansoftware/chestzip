"""Biçim dönüştürme testleri."""

import tempfile
import zipfile
from pathlib import Path

import pytest

from chestzip.api import Archive, convert_archive, create_archive
from chestzip.errors import SafetyError, UnsupportedOperation
from chestzip.safety import Limits, MiB

RAR = Path(__file__).parent / "data" / "rar"


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "src" / "Belgeler"
    (root / "alt").mkdir(parents=True)
    (root / "boş klasör").mkdir()
    (root / "not.txt").write_text("merhaba " * 1000, encoding="utf-8")
    (root / "alt" / "ğüş.bin").write_bytes(bytes(range(256)) * 100)
    return root


def _files(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): (None if p.is_dir() else p.read_bytes())
            for p in sorted(root.rglob("*"))}


@pytest.mark.parametrize("src_fmt,dst_fmt", [("chz", "zip"), ("zip", "chz"), ("7z", "tar.gz"),
                                             ("tar.xz", "7z"), ("chz", "chz")])
def test_convert_roundtrip(tmp_path, tree, src_fmt, dst_fmt):
    src = create_archive(tmp_path / f"a.{src_fmt}", [tree])
    out = tmp_path / "out" / f"b.{dst_fmt}"
    convert_archive(src, out)
    with Archive(out) as a:
        assert a.format == dst_fmt
        a.extract(tmp_path / "dst")
    assert _files(tmp_path / "dst" / "Belgeler") == _files(tree)


def test_chz_to_zip_opens_with_standard_zipfile(tmp_path, tree):
    src = create_archive(tmp_path / "a.chz", [tree])
    out = tmp_path / "a.zip"
    convert_archive(src, out)
    with zipfile.ZipFile(out) as zf:  # herhangi bir ZIP programı açabilmeli
        assert zf.testzip() is None
        assert "Belgeler/alt/ğüş.bin" in zf.namelist()


def test_encrypted_to_encrypted(tmp_path, tree):
    src = create_archive(tmp_path / "g.chz", [tree], password="eski")
    out = tmp_path / "g.7z"
    convert_archive(src, out, password="eski", new_password="yeni")
    a = Archive(out)
    assert a.needs_password()
    a.set_password("yeni")
    a.extract(tmp_path / "dst")
    assert _files(tmp_path / "dst" / "Belgeler") == _files(tree)


def test_rar_to_chz(tmp_path):
    out = tmp_path / "r.chz"
    convert_archive(RAR / "rar5-subdirs.rar", out)
    names = {e.name for e in Archive(out).entries()}
    assert "sub/üȵĩöḋè/file.txt" in names


def test_convert_respects_bomb_limits_and_cleans_temp(tmp_path):
    f = tmp_path / "zeros.bin"
    f.write_bytes(b"\0" * (40 * MiB))
    src = create_archive(tmp_path / "z.chz", [f])
    before = set(Path(tempfile.gettempdir()).glob("chestzip-convert-*"))
    with pytest.raises(SafetyError):
        convert_archive(src, tmp_path / "z.zip", limits=Limits(max_total_size=10 * MiB))
    assert not (tmp_path / "z.zip").exists()
    assert set(Path(tempfile.gettempdir()).glob("chestzip-convert-*")) == before


def test_convert_same_file_refused(tmp_path, tree):
    src = create_archive(tmp_path / "a.zip", [tree])
    with pytest.raises(UnsupportedOperation):
        convert_archive(src, src)


def test_cli_convert(tmp_path, tree):
    from chestzip.cli import main
    src = create_archive(tmp_path / "a.chz", [tree])
    assert main(["c", str(src), str(tmp_path / "a.zip"), "-q"]) == 0
    assert zipfile.is_zipfile(tmp_path / "a.zip")
