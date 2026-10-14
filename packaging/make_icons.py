"""Uygulama ikonunu SVG'den PNG/ICO/ICNS olarak üretir."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from chestzip.gui.icons import pixmap  # noqa: E402

out = Path(__file__).resolve().parent / "icons"
out.mkdir(exist_ok=True)
app = QGuiApplication([])
big = pixmap("app", 512)
big.save(str(out / "chestzip.png"))
for name, base in (("app", "chestzip"), ("chzdoc", "chz-document")):
    pixmap(name, 512).save(str(out / f"{base}.png"))
    for fmt in ("ico", "icns"):
        target = out / f"{base}.{fmt}"
        src = pixmap(name, 256) if fmt == "ico" else pixmap(name, 512)
        print(target.name, "ok" if src.save(str(target), fmt.upper()) else "FAILED")
