#!/bin/sh
# PyInstaller çıktısından (dist/ChestZip) Debian/Ubuntu paketi üretir.
#   sh packaging/build-deb.sh 1.0.0
set -e
VERSION="${1:?sürüm gerekli}"
ARCH="${2:-amd64}"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PKG="$ROOT/build/deb/chestzip_${VERSION}_${ARCH}"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/chestzip" "$PKG/usr/bin" \
         "$PKG/usr/share/applications" "$PKG/usr/share/mime/packages" \
         "$PKG/usr/share/icons/hicolor/512x512/apps" \
         "$PKG/usr/share/icons/hicolor/512x512/mimetypes" \
         "$PKG/usr/share/doc/chestzip"
cp -r "$ROOT/dist/ChestZip/." "$PKG/opt/chestzip/"
ln -s /opt/chestzip/chestzip "$PKG/usr/bin/chestzip"
sed 's|^Exec=.*|Exec=/opt/chestzip/chestzip %F|' "$ROOT/packaging/chestzip.desktop" \
    > "$PKG/usr/share/applications/chestzip.desktop"
cp "$ROOT/packaging/chestzip-mime.xml" "$PKG/usr/share/mime/packages/chestzip.xml"
cp "$ROOT/packaging/icons/chestzip.png" "$PKG/usr/share/icons/hicolor/512x512/apps/chestzip.png"
cp "$ROOT/packaging/icons/chz-document.png" \
   "$PKG/usr/share/icons/hicolor/512x512/mimetypes/application-x-chestzip.png"
cp "$ROOT/LICENSE" "$PKG/usr/share/doc/chestzip/copyright"
cp "$ROOT/THIRD_PARTY_NOTICES.md" "$PKG/usr/share/doc/chestzip/"
SIZE=$(du -sk "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<CTRL
Package: chestzip
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Maintainer: mesutozansoftware <297260076+mesutozansoftware@users.noreply.github.com>
Homepage: https://github.com/mesutozansoftware/chestzip
Depends: libc6, libgl1, libegl1, libfontconfig1, libfreetype6, libdbus-1-3, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, libxcb-render-util0, libxcb-image0, libxcb-xkb1
Description: Open-source archive manager with zip bomb protection
 ChestZip creates and extracts CHZ (its own open format), ZIP, 7Z, TAR,
 TAR.GZ/BZ2/XZ archives and extracts RAR. It has built-in protection against
 zip bombs, Zip Slip path traversal and malicious symbolic links.
CTRL
cat > "$PKG/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
command -v update-mime-database >/dev/null && update-mime-database /usr/share/mime || true
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true
POST
cp "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
dpkg-deb --root-owner-group --build "$PKG" "$ROOT/chestzip_${VERSION}_${ARCH}.deb"
echo "Oluşturuldu: chestzip_${VERSION}_${ARCH}.deb"
