"""Kullanıcı ayarları (platforma uygun yapılandırma klasöründe JSON)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .i18n import detect_language
from .safety import Limits


def config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "Sandik"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Sandik"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "sandik"


@dataclass
class Settings:
    language: str = field(default_factory=detect_language)
    theme: str = "light"
    limits: Limits = field(default_factory=Limits)
    last_dir: str = ""
    default_format: str = "zip"
    default_level: int = 5
    overwrite: str = "ask"
    window: list = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        path = config_dir() / "settings.json"
        s = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return s
        for k, v in data.items():
            if k == "limits":
                s.limits = Limits.from_dict(v)
            elif hasattr(s, k):
                setattr(s, k, v)
        return s

    def save(self) -> None:
        d = config_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
            data = asdict(self)
            (d / "settings.json").write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
        except OSError:
            pass
