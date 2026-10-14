#!/bin/sh
# ChestZip'i Linux'ta kullanıcı için kurar ve .chz dosyalarını ilişkilendirir.
# Paket klasöründe çalıştırın:  ./linux-install.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
APPS="${XDG_DATA_HOME:-$HOME/.local/share}"
mkdir -p "$HOME/.local/bin" "$APPS/applications" "$APPS/icons/hicolor/512x512/apps" \
         "$APPS/icons/hicolor/512x512/mimetypes" "$APPS/chestzip"
cp -r "$HERE"/. "$APPS/chestzip/"
ln -sf "$APPS/chestzip/chestzip" "$HOME/.local/bin/chestzip"
cp "$HERE/chestzip.png" "$APPS/icons/hicolor/512x512/apps/chestzip.png"
cp "$HERE/chz-document.png" "$APPS/icons/hicolor/512x512/mimetypes/application-x-chestzip.png"
sed "s|^Exec=.*|Exec=$APPS/chestzip/chestzip %F|" "$HERE/chestzip.desktop" \
    > "$APPS/applications/chestzip.desktop"
xdg-mime install --novendor "$HERE/chestzip-mime.xml" 2>/dev/null || true
xdg-mime default chestzip.desktop application/x-chestzip 2>/dev/null || true
update-desktop-database "$APPS/applications" 2>/dev/null || true
gtk-update-icon-cache "$APPS/icons/hicolor" 2>/dev/null || true
echo "ChestZip kuruldu. .chz dosyaları artık ChestZip ile açılır."
