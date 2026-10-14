"""Bir GitHub sürümü yayınlandıktan sonra Homebrew tarifini (Cask) üretir.

    python packaging/update_manifests.py 1.0.0

SHA256SUMS.txt sürümden indirilir ve packaging/homebrew/chestzip.rb yazılır;
ardından bu dosya mesutozansoftware/homebrew-chestzip deposuna kopyalanır.
"""

import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "mesutozansoftware/chestzip"
HERE = Path(__file__).resolve().parent


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


def main() -> None:
    v = sys.argv[1].lstrip("v")
    s = sums(v)
    homebrew(v, s)
    print("Güncellendi:", ", ".join(sorted(s)))
    subprocess.run(["git", "status", "--short", str(HERE)])


if __name__ == "__main__":
    main()
