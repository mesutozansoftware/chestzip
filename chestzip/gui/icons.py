"""ChestZip'a özgü SVG ikonlar.

İşletim sisteminin ikon temasını kullanmak yerine tüm ikonlar burada çizilir;
böylece uygulama Windows, macOS ve Linux'ta birebir aynı görünür.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_S = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">{}</svg>'

# ChestZip — uygulama ikonu
CHEST = """
<rect x="5" y="20" width="38" height="22" rx="3" fill="#a0612b"/>
<path d="M5 20 Q5 7 24 7 Q43 7 43 20 Z" fill="#c07a3a"/>
<rect x="5" y="19" width="38" height="4" fill="#5b3a1e"/>
<rect x="11" y="8" width="4" height="34" fill="#e2b33c"/>
<rect x="33" y="8" width="4" height="34" fill="#e2b33c"/>
<rect x="19" y="17" width="10" height="12" rx="2" fill="#f2cf5b" stroke="#7a5a12" stroke-width="1.5"/>
<circle cx="24" cy="22" r="1.8" fill="#4a3410"/>
<rect x="23.2" y="22" width="1.6" height="4" fill="#4a3410"/>
"""

ICONS = {
    "app": CHEST,
    "add": CHEST + """
<circle cx="37" cy="36" r="10" fill="#2e9b4f" stroke="#fff" stroke-width="2"/>
<path d="M37 31v10M32 36h10" stroke="#fff" stroke-width="3" stroke-linecap="round"/>""",
    "extract": """
<rect x="5" y="22" width="30" height="20" rx="3" fill="#a0612b"/>
<path d="M5 22 Q5 11 20 11 Q35 11 35 22 Z" fill="#c07a3a" transform="rotate(-18 6 22)"/>
<rect x="10" y="22" width="3" height="20" fill="#e2b33c"/><rect x="27" y="22" width="3" height="20" fill="#e2b33c"/>
<circle cx="37" cy="14" r="10" fill="#2f7fd6" stroke="#fff" stroke-width="2"/>
<path d="M37 20V9M32 13l5-5 5 5" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>""",
    "test": """
<path d="M24 4 L40 10 V22 C40 33 33 40 24 44 C15 40 8 33 8 22 V10 Z" fill="#2e9b4f"/>
<path d="M24 8 L36 12.5 V22 C36 30.5 31 36 24 39.5 Z" fill="#3fb563"/>
<path d="M16 24 l6 6 l11 -12" stroke="#fff" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>""",
    "view": """
<rect x="9" y="4" width="26" height="36" rx="3" fill="#fff" stroke="#8592a3" stroke-width="2"/>
<path d="M15 13h14M15 19h14M15 25h8" stroke="#8592a3" stroke-width="2.5" stroke-linecap="round"/>
<circle cx="31" cy="31" r="8" fill="#e7f1ff" stroke="#2f7fd6" stroke-width="3.5"/>
<path d="M37 37l7 7" stroke="#2f7fd6" stroke-width="5" stroke-linecap="round"/>""",
    "delete": """
<rect x="10" y="13" width="28" height="31" rx="3" fill="#e0524a"/>
<rect x="6" y="8" width="36" height="6" rx="2" fill="#b83a33"/>
<rect x="18" y="4" width="12" height="5" rx="2" fill="#b83a33"/>
<path d="M18 20v18M24 20v18M30 20v18" stroke="#fff" stroke-width="3" stroke-linecap="round"/>""",
    "info": """
<circle cx="24" cy="24" r="20" fill="#2f7fd6"/>
<circle cx="24" cy="14" r="3" fill="#fff"/>
<rect x="21" y="20" width="6" height="16" rx="2" fill="#fff"/>""",
    "settings": """
<g transform="translate(24 24)">
<g fill="#6b7685">
<rect x="-4" y="-21" width="8" height="10" rx="2"/>
<rect x="-4" y="-21" width="8" height="10" rx="2" transform="rotate(45)"/>
<rect x="-4" y="-21" width="8" height="10" rx="2" transform="rotate(90)"/>
<rect x="-4" y="-21" width="8" height="10" rx="2" transform="rotate(135)"/>
<rect x="-4" y="-21" width="8" height="10" rx="2" transform="rotate(180)"/>
<rect x="-4" y="-21" width="8" height="10" rx="2" transform="rotate(225)"/>
<rect x="-4" y="-21" width="8" height="10" rx="2" transform="rotate(270)"/>
<rect x="-4" y="-21" width="8" height="10" rx="2" transform="rotate(315)"/>
<circle r="14"/></g><circle r="6" fill="#fff"/></g>""",
    "up": """
<path d="M24 8 L40 26 H30 V40 H18 V26 H8 Z" fill="#2f7fd6"/>""",
    "folder": """
<path d="M4 12 a3 3 0 0 1 3 -3 h11 l4 5 h19 a3 3 0 0 1 3 3 v22 a3 3 0 0 1 -3 3 H7 a3 3 0 0 1 -3 -3 Z" fill="#e8a93a"/>
<path d="M4 18 h40 v21 a3 3 0 0 1 -3 3 H7 a3 3 0 0 1 -3 -3 Z" fill="#f6c453"/>""",
    "file": """
<path d="M10 4 h20 l10 10 v28 a3 3 0 0 1 -3 3 H10 a3 3 0 0 1 -3 -3 V7 a3 3 0 0 1 3 -3 Z" fill="#f4f6f9" stroke="#8592a3" stroke-width="2"/>
<path d="M30 4 v10 h10" fill="#dfe4ea" stroke="#8592a3" stroke-width="2" stroke-linejoin="round"/>""",
    "archive": """
<rect x="6" y="6" width="36" height="38" rx="4" fill="#7b4fc9"/>
<rect x="6" y="6" width="36" height="9" rx="4" fill="#6a3fb5"/>
<g fill="#e9e0ff"><rect x="21" y="6" width="6" height="4"/><rect x="21" y="14" width="6" height="4"/>
<rect x="21" y="22" width="6" height="4"/></g>
<g fill="#b9a2ec"><rect x="21" y="10" width="6" height="4"/><rect x="21" y="18" width="6" height="4"/></g>
<rect x="19" y="27" width="10" height="10" rx="2" fill="#f2cf5b" stroke="#7a5a12" stroke-width="1.5"/>""",
    "lock": """
<path d="M15 21 V15 a9 9 0 0 1 18 0 V21" fill="none" stroke="#6b7685" stroke-width="4"/>
<rect x="10" y="21" width="28" height="22" rx="3" fill="#e2b33c"/>
<circle cx="24" cy="31" r="3" fill="#5b3a1e"/><rect x="22.5" y="31" width="3" height="7" fill="#5b3a1e"/>""",
    "shield": """
<path d="M24 4 L40 10 V22 C40 33 33 40 24 44 C15 40 8 33 8 22 V10 Z" fill="#2e9b4f"/>
<path d="M24 8 L36 12.5 V22 C36 30.5 31 36 24 39.5 Z" fill="#3fb563"/>""",
    "warning": """
<path d="M24 5 L45 42 H3 Z" fill="#f0a020" stroke="#c57d0b" stroke-width="2" stroke-linejoin="round"/>
<rect x="22" y="17" width="4" height="13" rx="2" fill="#fff"/><circle cx="24" cy="36" r="2.5" fill="#fff"/>""",
    "link": """
<path d="M20 28 l8 -8" stroke="#2f7fd6" stroke-width="4" stroke-linecap="round"/>
<rect x="5" y="23" width="20" height="12" rx="6" transform="rotate(-45 15 29)" fill="none" stroke="#2f7fd6" stroke-width="4"/>
<rect x="23" y="13" width="20" height="12" rx="6" transform="rotate(-45 33 19)" fill="none" stroke="#2f7fd6" stroke-width="4"/>""",
}


@lru_cache(maxsize=None)
def pixmap(name: str, size: int = 48) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_S.format(ICONS[name]).encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


@lru_cache(maxsize=None)
def icon(name: str) -> QIcon:
    ic = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(pixmap(name, s))
    return ic


def svg_source(name: str) -> str:
    return _S.format(ICONS[name])
