"""Platformdan bağımsız görünüm: Qt Fusion stili + sabit renk paleti."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

LIGHT = {
    "window": "#eef1f5", "base": "#ffffff", "alt": "#f6f8fb", "text": "#1d2430",
    "muted": "#5f6b7a", "button": "#f4f6f9", "border": "#cfd6df", "accent": "#2f7fd6",
    "accent_text": "#ffffff", "toolbar": "#e4e9f0", "hover": "#dbe8f8",
}
DARK = {
    "window": "#1f232a", "base": "#262b33", "alt": "#2b313a", "text": "#e6e9ee",
    "muted": "#9aa5b4", "button": "#2f3540", "border": "#3a414d", "accent": "#4b93e6",
    "accent_text": "#ffffff", "toolbar": "#1a1d23", "hover": "#33415a",
}


def apply_theme(app: QApplication, name: str = "light") -> dict:
    c = DARK if name == "dark" else LIGHT
    app.setStyle(QStyleFactory.create("Fusion"))
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: c["window"], QPalette.ColorRole.WindowText: c["text"],
        QPalette.ColorRole.Base: c["base"], QPalette.ColorRole.AlternateBase: c["alt"],
        QPalette.ColorRole.Text: c["text"], QPalette.ColorRole.Button: c["button"],
        QPalette.ColorRole.ButtonText: c["text"], QPalette.ColorRole.Highlight: c["accent"],
        QPalette.ColorRole.HighlightedText: c["accent_text"],
        QPalette.ColorRole.ToolTipBase: c["base"], QPalette.ColorRole.ToolTipText: c["text"],
        QPalette.ColorRole.PlaceholderText: c["muted"], QPalette.ColorRole.Link: c["accent"],
        QPalette.ColorRole.Mid: c["border"], QPalette.ColorRole.Dark: c["border"],
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["muted"]))
    app.setPalette(pal)

    font = QFont()
    font.setFamilies(["Segoe UI", "SF Pro Text", ".AppleSystemUIFont", "Helvetica Neue",
                      "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans", "Arial"])
    font.setPixelSize(13)
    app.setFont(font)

    app.setStyleSheet(f"""
        QToolBar#mainToolbar {{
            background: {c['toolbar']}; border: none; border-bottom: 1px solid {c['border']};
            padding: 4px 6px; spacing: 2px;
        }}
        QToolBar#mainToolbar QToolButton {{
            border: 1px solid transparent; border-radius: 6px; padding: 4px 8px;
            min-width: 64px; color: {c['text']};
        }}
        QToolBar#mainToolbar QToolButton:hover {{ background: {c['hover']}; border-color: {c['border']}; }}
        QToolBar#mainToolbar QToolButton:pressed {{ background: {c['border']}; }}
        QToolBar#mainToolbar QToolButton:disabled {{ color: {c['muted']}; }}
        QWidget#navBar {{ background: {c['window']}; border-bottom: 1px solid {c['border']}; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            border: 1px solid {c['border']}; border-radius: 5px; padding: 4px 6px;
            background: {c['base']}; selection-background-color: {c['accent']};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {c['accent']};
        }}
        QTreeView {{ border: none; background: {c['base']}; alternate-background-color: {c['alt']}; }}
        QTreeView::item {{ padding: 3px 2px; }}
        QHeaderView::section {{
            background: {c['window']}; border: none; border-right: 1px solid {c['border']};
            border-bottom: 1px solid {c['border']}; padding: 5px 6px; font-weight: 600;
        }}
        QStatusBar {{ background: {c['toolbar']}; border-top: 1px solid {c['border']}; }}
        QStatusBar QLabel {{ padding: 0 6px; }}
        QPushButton {{
            border: 1px solid {c['border']}; border-radius: 5px; padding: 5px 14px;
            background: {c['button']};
        }}
        QPushButton:hover {{ border-color: {c['accent']}; }}
        QPushButton:default {{ background: {c['accent']}; color: {c['accent_text']}; border-color: {c['accent']}; }}
        QProgressBar {{
            border: 1px solid {c['border']}; border-radius: 5px; text-align: center;
            background: {c['base']}; height: 18px;
        }}
        QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
        QGroupBox {{ border: 1px solid {c['border']}; border-radius: 6px; margin-top: 12px; padding-top: 8px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; font-weight: 600; }}
        QLabel#badge {{
            border-radius: 9px; padding: 2px 10px; background: {c['hover']}; color: {c['text']};
            font-weight: 600;
        }}
        QLabel#safetyOn {{ color: #2e9b4f; font-weight: 600; }}
        QLabel#safetyOff {{ color: #d0492e; font-weight: 600; }}
        QLabel#muted {{ color: {c['muted']}; }}
        QLabel#dangerBox {{
            background: #fdecea; color: #8a1f17; border: 1px solid #f3b8b2; border-radius: 6px; padding: 8px;
        }}
        QLabel#okBox {{
            background: #e8f6ec; color: #1d5e31; border: 1px solid #b6e0c2; border-radius: 6px; padding: 8px;
        }}
        QLabel#warnBox {{
            background: #fff6e0; color: #6b4b00; border: 1px solid #f1d58d; border-radius: 6px; padding: 8px;
        }}
    """)
    return c
