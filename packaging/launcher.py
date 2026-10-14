"""Paketlenmiş uygulamanın giriş noktası (komut verilirse CLI, yoksa arayüz)."""

import sys

from chestzip.cli import main

if __name__ == "__main__":
    sys.exit(main())
