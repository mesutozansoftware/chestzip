"""Flatpak için Python bağımlılık modülünü (python-deps.json) üretir.

Flatpak derlemesi internetsiz yapılır; bu yüzden her tekerlek (wheel) dosyası
adres + SHA-256 ile tarife yazılır. Kullanım:  python packaging/flatpak/gen_deps.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PY = "3.12"  # org.freedesktop.Platform 24.08 içindeki Python
PLATFORMS = ["manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64",
             "manylinux_2_5_x86_64", "manylinux1_x86_64", "linux_x86_64"]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        cmd = [sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed",
               "--quiet", "--report", str(report), "--only-binary=:all:",
               "--python-version", PY, "--target", tmp]
        for p in PLATFORMS:
            cmd += ["--platform", p]
        cmd.append(str(ROOT))
        subprocess.run(cmd, check=True)
        data = json.loads(report.read_text())
    sources, names = [], []
    for item in data["install"]:
        name = item["metadata"]["name"]
        if name.lower() == "chestzip":
            continue
        info = item["download_info"]
        sha = info["archive_info"]["hashes"]["sha256"]
        sources.append({"type": "file", "url": info["url"], "sha256": sha})
        names.append(name)
    module = {
        "name": "python-deps",
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --verbose --no-index --find-links=\"file://${PWD}\" "
            "--prefix=${FLATPAK_DEST} --no-build-isolation " + " ".join(sorted(names))
        ],
        "sources": sources,
    }
    out = HERE / "python-deps.json"
    out.write_text(json.dumps(module, indent=2) + "\n")
    print(f"{len(sources)} paket -> {out}")


if __name__ == "__main__":
    main()
