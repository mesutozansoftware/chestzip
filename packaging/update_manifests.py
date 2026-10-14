"""Bir GitHub sürümü yayınlandıktan sonra paket yöneticisi tariflerini üretir.

    python packaging/update_manifests.py 1.0.0

SHA256SUMS.txt sürümden indirilir ve şunlar yazılır:
  packaging/homebrew/chestzip.rb          (Homebrew Cask)
  packaging/winget/<sürüm>/*.yaml         (winget)
  packaging/aur/PKGBUILD + .SRCINFO       (Arch AUR)
"""

import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "mesutozansoftware/chestzip"
HERE = Path(__file__).resolve().parent
WINGET_ID = "mesutozansoftware.ChestZip"


def sums(version: str) -> dict[str, str]:
    url = f"https://github.com/{REPO}/releases/download/v{version}/SHA256SUMS.txt"
    text = urllib.request.urlopen(url, timeout=60).read().decode()
    out = {}
    for line in text.splitlines():
        sha, name = line.split(maxsplit=1)
        out[name.lstrip("*")] = sha
    return out


def homebrew(v: str, s: dict) -> None:
    name = f"ChestZip-{v}-macos-arm64.zip"
    (HERE / "homebrew").mkdir(exist_ok=True)
    (HERE / "homebrew" / "chestzip.rb").write_text(f'''cask "chestzip" do
  version "{v}"
  sha256 "{s[name]}"

  url "https://github.com/{REPO}/releases/download/v#{{version}}/ChestZip-#{{version}}-macos-arm64.zip"
  name "ChestZip"
  desc "Open-source archive manager with zip bomb protection"
  homepage "https://github.com/{REPO}"

  depends_on arch: :arm64
  depends_on macos: ">= :monterey"

  app "ChestZip.app"
  binary "#{{appdir}}/ChestZip.app/Contents/MacOS/chestzip"

  zap trash: "~/Library/Application Support/ChestZip"
end
''')


def winget(v: str, s: dict) -> None:
    name = f"ChestZip-{v}-setup-windows-x64.exe"
    d = HERE / "winget" / v
    d.mkdir(parents=True, exist_ok=True)
    head = "# yaml-language-server: $schema=https://aka.ms/winget-manifest.{kind}.1.6.0.schema.json\n"
    (d / f"{WINGET_ID}.yaml").write_text(head.format(kind="version") + f"""
PackageIdentifier: {WINGET_ID}
PackageVersion: {v}
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.6.0
""")
    (d / f"{WINGET_ID}.installer.yaml").write_text(head.format(kind="installer") + f"""
PackageIdentifier: {WINGET_ID}
PackageVersion: {v}
InstallerType: inno
UpgradeBehavior: install
FileExtensions:
  - chz
Installers:
  - Architecture: x64
    InstallerUrl: https://github.com/{REPO}/releases/download/v{v}/{name}
    InstallerSha256: {s[name].upper()}
ManifestType: installer
ManifestVersion: 1.6.0
""")
    (d / f"{WINGET_ID}.locale.en-US.yaml").write_text(head.format(kind="defaultLocale") + f"""
PackageIdentifier: {WINGET_ID}
PackageVersion: {v}
PackageLocale: en-US
Publisher: mesutozansoftware
PublisherUrl: https://github.com/mesutozansoftware
PackageName: ChestZip
PackageUrl: https://github.com/{REPO}
License: MIT
LicenseUrl: https://github.com/{REPO}/blob/main/LICENSE
ShortDescription: Open-source archive manager with zip bomb protection
Description: >-
  ChestZip creates and extracts CHZ (its own open format), ZIP, 7Z, TAR and
  TAR.GZ/BZ2/XZ archives and extracts RAR. It protects against zip bombs,
  Zip Slip path traversal and malicious symbolic links.
Moniker: chestzip
Tags:
  - archive
  - compression
  - zip
  - 7z
  - rar
  - unzip
ReleaseNotesUrl: https://github.com/{REPO}/releases/tag/v{v}
ManifestType: defaultLocale
ManifestVersion: 1.6.0
""")


def aur(v: str, s: dict) -> None:
    name = f"ChestZip-{v}-linux-x64.tar.gz"
    p = HERE / "aur" / "PKGBUILD"
    text = p.read_text()
    text = re.sub(r"^pkgver=.*$", f"pkgver={v}", text, flags=re.M)
    text = re.sub(r"^pkgrel=.*$", "pkgrel=1", text, flags=re.M)
    text = re.sub(r"^sha256sums=.*$", f"sha256sums=('{s[name]}')", text, flags=re.M)
    p.write_text(text)
    deps = re.search(r"depends=\((.*?)\)", text, re.S).group(1).split()
    deps = [d.strip("'") for d in deps]
    lines = [
        "pkgbase = chestzip-bin",
        "\tpkgdesc = Open-source archive manager with zip bomb protection (CHZ, ZIP, 7Z, TAR, RAR)",
        f"\tpkgver = {v}",
        "\tpkgrel = 1",
        f"\turl = https://github.com/{REPO}",
        "\tarch = x86_64",
        "\tlicense = MIT",
        *[f"\tdepends = {d}" for d in deps],
        "\tprovides = chestzip",
        "\tconflicts = chestzip",
        "\toptions = !strip",
        "\toptions = !debug",
        f"\tsource = https://github.com/{REPO}/releases/download/v{v}/{name}",
        f"\tsha256sums = {s[name]}",
        "",
        "pkgname = chestzip-bin",
        "",
    ]
    (HERE / "aur" / ".SRCINFO").write_text("\n".join(lines))


def main() -> None:
    v = sys.argv[1].lstrip("v")
    s = sums(v)
    homebrew(v, s)
    winget(v, s)
    aur(v, s)
    print("Güncellendi:", ", ".join(sorted(s)))
    subprocess.run(["git", "status", "--short", str(HERE)])


if __name__ == "__main__":
    main()
