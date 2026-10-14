#!/bin/sh
# ChestZip kurulumu (macOS ve Linux):
#   curl -fsSL https://raw.githubusercontent.com/mesutozansoftware/chestzip/main/install.sh | sh
#
# Son sürümü GitHub'dan indirir, SHA-256 özetini doğrular ve kurar.
# Yönetici (sudo) yetkisi gerekmez.
#   macOS : ~/Applications/ChestZip.app   (+ ~/.local/bin/chestzip)
#   Linux : ~/.local/share/chestzip       (+ ~/.local/bin/chestzip, menü kısayolu)
# Ortam değişkenleri: CHESTZIP_VERSION=1.0.0 (belirli sürüm), CHESTZIP_INSTALL_DIR
set -eu

REPO="mesutozansoftware/chestzip"
if [ -n "${CHESTZIP_VERSION:-}" ]; then
  BASE="https://github.com/$REPO/releases/download/v${CHESTZIP_VERSION#v}"
else
  BASE="https://github.com/$REPO/releases/latest/download"
fi

say() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mHata:\033[0m %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' gerekli ama bulunamadı."; }

need curl
OS=$(uname -s)
ARCH=$(uname -m)
case "$OS" in
  Darwin)
    [ "$ARCH" = "arm64" ] || die "Şu an yalnızca Apple Silicon (M1 ve sonrası) Mac'ler destekleniyor."
    PATTERN='macos-arm64\.zip$'
    SHA="shasum -a 256" ;;
  Linux)
    [ "$ARCH" = "x86_64" ] || die "Şu an yalnızca x86_64 Linux destekleniyor."
    PATTERN='linux-x64\.tar\.gz$'
    SHA="sha256sum"
    need tar ;;
  *) die "Desteklenmeyen sistem: $OS (Windows için install.ps1 kullanın)." ;;
esac

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

say "Sürüm bilgisi alınıyor..."
curl -fsSL "$BASE/SHA256SUMS.txt" -o "$TMP/SHA256SUMS.txt" || die "Sürüm bulunamadı."
LINE=$(grep -E "$PATTERN" "$TMP/SHA256SUMS.txt" | head -n 1)
[ -n "$LINE" ] || die "Bu sistem için paket bulunamadı."
EXPECTED=$(echo "$LINE" | awk '{print $1}')
FILE=$(echo "$LINE" | awk '{print $2}' | sed 's/^\*//')

say "İndiriliyor: $FILE"
curl -fL --progress-bar "$BASE/$FILE" -o "$TMP/$FILE"
ACTUAL=$($SHA "$TMP/$FILE" | awk '{print $1}')
[ "$ACTUAL" = "$EXPECTED" ] || die "SHA-256 doğrulaması başarısız! Dosya bozuk veya değiştirilmiş."
say "SHA-256 doğrulandı."

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

if [ "$OS" = "Darwin" ]; then
  need ditto
  DEST="${CHESTZIP_INSTALL_DIR:-$HOME/Applications}"
  mkdir -p "$DEST"
  ditto -x -k "$TMP/$FILE" "$TMP/app"
  rm -rf "$DEST/ChestZip.app"
  mv "$TMP/app/ChestZip.app" "$DEST/ChestZip.app"
  ln -sf "$DEST/ChestZip.app/Contents/MacOS/chestzip" "$BIN_DIR/chestzip"
  # .chz türünü sisteme tanıt
  LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
  [ -x "$LSREG" ] && "$LSREG" -f "$DEST/ChestZip.app" >/dev/null 2>&1 || true
  say "Kuruldu: $DEST/ChestZip.app"
else
  tar -xzf "$TMP/$FILE" -C "$TMP"
  if [ -n "${CHESTZIP_INSTALL_DIR:-}" ]; then export XDG_DATA_HOME="$CHESTZIP_INSTALL_DIR"; fi
  sh "$TMP/ChestZip/linux-install.sh"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "Komut satırı için PATH'e ekleyin: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
say "Tamamlandı. ChestZip'i uygulamalar menüsünden veya 'chestzip' komutuyla açabilirsiniz."
