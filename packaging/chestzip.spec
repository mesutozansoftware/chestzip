# PyInstaller yapılandırması — Windows, macOS ve Linux için aynı dosya.
#   pyinstaller packaging/chestzip.spec
import importlib.util
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ICONS = ROOT / "packaging" / "icons"
icon = {"win32": ICONS / "chestzip.ico", "darwin": ICONS / "chestzip.icns"}.get(
    sys.platform, ICONS / "chestzip.png")

# RAR açmak için gömülü 7-Zip programı (py7zz paketinden)
# (Windows'ta 7zz.exe yanındaki 7z.dll'e ihtiyaç duyar; bin klasörü olduğu gibi alınır.)
_bin = Path(importlib.util.find_spec("py7zz").origin).parent / "bin"
_exe = "7zz.exe" if sys.platform.startswith("win") else "7zz"
if not (_bin / _exe).is_file():
    raise SystemExit(f"7zz bulunamadı: {_bin / _exe}")
_bin_files = [(str(f), "chestzip_bin") for f in _bin.iterdir()
              if f.is_file() and not f.name.startswith(".")]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=_bin_files,
    datas=[(str(ROOT / "LICENSE"), "."), (str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")],
    hiddenimports=["chestzip.gui.app", "PySide6.QtSvg"],
    excludes=["tkinter", "py7zz", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.Qt3DCore", "PySide6.QtMultimedia"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="chestzip",
          console=False, icon=str(icon), upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ChestZip", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll, name="ChestZip.app", icon=str(icon), bundle_identifier="org.chestzip.app",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Archive",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["public.zip-archive", "org.7-zip.7-zip-archive",
                                       "public.tar-archive", "org.gnu.gnu-zip-archive",
                                       "public.bzip2-archive", "org.tukaani.xz-archive",
                                       "com.rarlab.rar-archive"],
            }],
        },
    )
