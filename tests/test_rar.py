"""RAR açma testleri (tests/data/rar: rarfile projesinin ISC lisanslı test dosyaları)."""

from pathlib import Path

import pytest

from chestzip.api import Archive
from chestzip.backends.rar_backend import bundled_7zz
from chestzip.errors import PasswordRequired, SafetyError, WrongPassword
from chestzip.safety import Limits

DATA = Path(__file__).parent / "data" / "rar"
PW = "password"


def test_bundled_decoder_is_used():
    import rarfile
    exe = bundled_7zz()
    assert exe is not None and exe.is_file()
    Archive(DATA / "rar5-solid.rar")  # aracı yapılandırır
    assert type(rarfile.CURRENT_SETUP).__name__ == "_SevenZipSetup"
    assert rarfile.SEVENZIP2_TOOL == str(exe)


@pytest.mark.parametrize("name", ["rar3-solid", "rar5-solid"])
def test_extract_solid(tmp_path, name):
    with Archive(DATA / f"{name}.rar") as a:
        assert a.format == "rar"
        res = a.extract(tmp_path)
        assert a.test().files == 2
    assert res.files == 2
    for f in ("stest1.txt", "stest2.txt"):
        assert (tmp_path / f).stat().st_size == 2048


@pytest.mark.parametrize("name", ["rar3-subdirs", "rar5-subdirs"])
def test_extract_subdirs_unicode(tmp_path, name):
    with Archive(DATA / f"{name}.rar") as a:
        a.extract(tmp_path)
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")
                   if p.is_file())
    assert files and all(f.startswith("sub/") for f in files)
    assert any("üȵĩöḋè" in f for f in files)


def test_unicode_names(tmp_path):
    with Archive(DATA / "unicode.rar") as a:
        a.extract(tmp_path)
    assert (tmp_path / "уииоотивл.txt").exists()


@pytest.mark.parametrize("name", ["rar5-psw", "rar5-hpsw", "rar3-comment-psw",
                                  "rar3-comment-hpsw"])
def test_password(tmp_path, name):
    a = Archive(DATA / f"{name}.rar") if "hpsw" not in name else None
    if a is not None:
        assert a.needs_password()
        with pytest.raises(PasswordRequired):
            a.extract(tmp_path / "x")
    else:
        with pytest.raises(PasswordRequired):
            Archive(DATA / f"{name}.rar").entries()
    a = Archive(DATA / f"{name}.rar", password=PW)
    res = a.extract(tmp_path / "ok")
    assert res.files == 2


def test_wrong_password(tmp_path):
    a = Archive(DATA / "rar5-psw.rar", password="yanlis")
    with pytest.raises(WrongPassword):
        a.extract(tmp_path)
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []


def test_evil_symlink_traversal_blocked(tmp_path):
    dst = tmp_path / "a" / "dst"
    with Archive(DATA / "rar5-evil-symlink-traversal.rar",
                 limits=Limits(allow_symlinks=True)) as a:
        res = a.extract(dst)
    assert not (dst / "up").is_symlink()
    assert not list(tmp_path.glob("**/pwned.txt")) or all(
        p.resolve().is_relative_to(dst.resolve()) for p in tmp_path.glob("**/pwned.txt"))
    assert res.warnings


def test_stream_ratio_limit(tmp_path):
    with Archive(DATA / "rar3-solid.rar", limits=Limits(max_ratio=5, ratio_grace=100)) as a:
        with pytest.raises(SafetyError):
            a.extract(tmp_path)


@pytest.mark.parametrize("name", ["unicode", "rar5-subdirs", "rar3-subdirs", "rar5-solid"])
def test_listfile_path_unicode(tmp_path, monkeypatch, name):
    """Dosya adının 7-Zip'e liste dosyasıyla verildiği yol (Windows Unicode hatası)."""
    import rarfile
    monkeypatch.setattr(rarfile, "USE_EXTRACT_HACK", 0)
    with Archive(DATA / f"{name}.rar") as a:
        res = a.extract(tmp_path)
        assert res.files == sum(1 for e in a.entries() if not e.is_dir)
