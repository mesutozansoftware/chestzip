"""Komut satırı arayüzü.

Örnekler::

    chestzip l arsiv.zip                 # içeriği listele
    chestzip x arsiv.7z -o hedef/        # çıkart
    chestzip a yeni.zip dosya klasor/    # arşiv oluştur / ekle
    chestzip a -p sifre gizli.7z belge/  # şifreli 7z
    chestzip t arsiv.tar.gz              # test et
    chestzip d arsiv.zip eski.txt        # arşivden sil
    chestzip c arsiv.chz arsiv.zip       # biçim dönüştür
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .api import Archive, convert_archive, create_archive
from .backends import CREATE_FORMATS
from .errors import ArchiveError, PasswordRequired
from .i18n import set_language, t
from .safety import GiB, MiB, Limits, human_size
from .settings import Settings


def _parse_size(text: str) -> int:
    text = text.strip().upper()
    mult = 1
    for suf, m in (("T", 1024 * GiB), ("G", GiB), ("M", MiB), ("K", 1024)):
        if text.endswith(suf + "B") or text.endswith(suf):
            text = text.rstrip("B")[:-1]
            mult = m
            break
    return int(float(text) * mult)


def _limits(args, base: Limits) -> Limits:
    if args.no_limits:
        return Limits.unlimited()
    lim = Limits.from_dict(base.to_dict())
    if args.max_size:
        lim.max_total_size = _parse_size(args.max_size)
    if args.max_ratio:
        lim.max_ratio = args.max_ratio
    if args.max_files:
        lim.max_entries = args.max_files
    return lim


class _Progress:
    def __init__(self, label: str, quiet: bool) -> None:
        self.label = label
        self.quiet = quiet or not sys.stderr.isatty()

    def __call__(self, done: int, total: int, name: str) -> None:
        if self.quiet:
            return
        pct = f"{done * 100 // total:3d}%" if total else "   "
        line = f"\r{self.label} {pct} {name[-60:]:<60}"
        sys.stderr.write(line)
        sys.stderr.flush()

    def end(self) -> None:
        if not self.quiet:
            sys.stderr.write("\r" + " " * 80 + "\r")


def _ask_overwrite(path: str) -> str:
    if not sys.stdin.isatty():
        return "no"
    ans = input(f"{t('dlg.overwrite_text', path=path)} [y]es/[n]o/[A]ll/[N]one/[r]ename: ")
    return {"y": "yes", "n": "no", "A": "all", "N": "none", "r": "rename"}.get(ans.strip(), "no")


def _open(args, limits: Limits) -> Archive:
    a = Archive(args.archive, password=args.password, limits=limits)
    if a.needs_password() and not a.password:
        if not sys.stdin.isatty():
            raise PasswordRequired(t("err.password_required"))
        a.set_password(getpass.getpass(t("dlg.password_for", name=a.path.name) + " "))
    return a


def cmd_list(args, limits) -> int:
    a = _open(args, limits)
    print(f"{a.path.name}  [{a.format_name}]  {human_size(a.size)}")
    print(f"{t('col.size'):>12} {t('col.packed'):>12}  {t('col.modified'):16}  {t('col.name')}")
    total = 0
    for e in a.entries():
        when = e.mtime.strftime("%Y-%m-%d %H:%M") if e.mtime else ""
        packed = "" if e.packed is None else str(e.packed)
        flag = "*" if e.encrypted else " "
        name = e.name + ("/" if e.is_dir else "")
        print(f"{e.size:>12} {packed:>12}  {when:16} {flag}{name}")
        total += e.size
    print(t("cli.entries", n=len(a.entries()), size=human_size(total)))
    report = a.analyze()
    for p in report.problems:
        print("!! " + p, file=sys.stderr)
    for w in report.warnings:
        print("!  " + w, file=sys.stderr)
    return 0 if report.ok else 3


def cmd_extract(args, limits) -> int:
    a = _open(args, limits)
    dest = Path(args.output) if args.output else Path.cwd()
    overwrite = "always" if args.yes else args.overwrite
    prog = _Progress(t("prog.extracting"), args.quiet)
    res = a.extract(dest, args.members or None, overwrite=overwrite,
                    ask_overwrite=_ask_overwrite, progress=prog)
    prog.end()
    print(t("res.extracted", files=res.files, size=human_size(res.bytes)))
    for w in res.warnings:
        print("!  " + w, file=sys.stderr)
    return 0


def cmd_test(args, limits) -> int:
    a = _open(args, limits)
    prog = _Progress(t("prog.testing"), args.quiet)
    res = a.test(progress=prog)
    prog.end()
    print(t("res.test_ok", files=res.files, size=human_size(res.bytes)))
    for w in res.warnings:
        print("!  " + w, file=sys.stderr)
    return 0


def cmd_add(args, limits) -> int:
    out = Path(args.archive)
    prog = _Progress(t("prog.adding"), args.quiet)
    if out.exists():
        a = Archive(out, password=args.password, limits=limits)
        a.add(args.files, level=args.level, progress=prog)
    else:
        create_archive(out, args.files, fmt=args.format, level=args.level,
                       password=args.password, progress=prog)
    prog.end()
    print(t("res.created", path=out))
    return 0


def cmd_delete(args, limits) -> int:
    a = _open(args, limits)
    n = a.delete(args.members)
    print(t("res.deleted", n=n))
    return 0


def cmd_convert(args, limits) -> int:
    a = _open(args, limits)  # gerekirse kaynak şifresini sorar
    a.close()
    prog = _Progress(t("prog.converting"), args.quiet)
    res = convert_archive(args.archive, args.output, fmt=args.format, level=args.level,
                          password=a.password, new_password=args.new_password,
                          limits=limits, progress=prog)
    prog.end()
    print(t("res.converted", path=res.dest))
    for w in res.warnings:
        print("!  " + w, file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chestzip", description=f"{APP_NAME} — {t('app.tagline')}")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    p.add_argument("--lang", choices=["tr", "en"])
    sub = p.add_subparsers(dest="cmd")

    def common(sp, password=True):
        sp.add_argument("archive")
        if password:
            sp.add_argument("-p", "--password")
        sp.add_argument("-q", "--quiet", action="store_true")
        g = sp.add_argument_group("güvenlik / security")
        g.add_argument("--max-size", help="ör. 20G")
        g.add_argument("--max-ratio", type=float)
        g.add_argument("--max-files", type=int)
        g.add_argument("--no-limits", action="store_true",
                       help="zip bombası korumasını kapat (yol güvenliği açık kalır)")
        return sp

    common(sub.add_parser("l", aliases=["list"], help="listele"))
    sp = common(sub.add_parser("x", aliases=["extract"], help="çıkart"))
    sp.add_argument("members", nargs="*")
    sp.add_argument("-o", "--output")
    sp.add_argument("-y", "--yes", action="store_true", help="sormadan üzerine yaz")
    sp.add_argument("--overwrite", choices=["ask", "always", "never", "rename"], default="ask")
    common(sub.add_parser("t", aliases=["test"], help="test et"))
    sp = common(sub.add_parser("a", aliases=["add"], help="oluştur / ekle"))
    sp.add_argument("files", nargs="+")
    sp.add_argument("-f", "--format", choices=list(CREATE_FORMATS))
    sp.add_argument("-l", "--level", type=int, default=5, choices=range(0, 10))
    sp = common(sub.add_parser("c", aliases=["convert"],
                               help="biçim dönüştür (ör. a.chz -> a.zip)"))
    sp.add_argument("output", help="yeni arşiv (biçim uzantıdan anlaşılır)")
    sp.add_argument("-f", "--format", choices=list(CREATE_FORMATS))
    sp.add_argument("-l", "--level", type=int, default=5, choices=range(0, 10))
    sp.add_argument("--new-password", help="yeni arşivin şifresi (CHZ, ZIP, 7Z)")
    sp = common(sub.add_parser("d", aliases=["delete"], help="arşivden sil"))
    sp.add_argument("members", nargs="+")
    sp = sub.add_parser("gui", help="grafik arayüzü aç")
    sp.add_argument("paths", nargs="*")
    return p


COMMANDS = {"l": cmd_list, "list": cmd_list, "x": cmd_extract, "extract": cmd_extract,
            "t": cmd_test, "test": cmd_test, "a": cmd_add, "add": cmd_add,
            "d": cmd_delete, "delete": cmd_delete, "c": cmd_convert, "convert": cmd_convert}


def main(argv=None) -> int:
    settings = Settings.load()
    set_language(settings.language)
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and not argv[0].startswith("-") and argv[0] not in COMMANDS and argv[0] != "gui":
        argv.insert(0, "gui")  # dosya yöneticisinden "Birlikte aç" ile gelen yollar
    args = build_parser().parse_args(argv)
    if args.lang:
        set_language(args.lang)
    if args.cmd in (None, "gui"):
        from .gui.app import run
        return run(getattr(args, "paths", []) or [])
    try:
        return COMMANDS[args.cmd](args, _limits(args, settings.limits))
    except KeyboardInterrupt:
        print("\n" + t("err.cancelled"), file=sys.stderr)
        return 130
    except ArchiveError as e:
        print(f"{t('dlg.error')}: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"{t('dlg.error')}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
