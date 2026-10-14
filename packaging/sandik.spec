# PyInstaller yapılandırması — Windows, macOS ve Linux için aynı dosya.
#   pyinstaller packaging/sandik.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ICONS = ROOT / "packaging" / "icons"
icon = {"win32": ICONS / "sandik.ico", "darwin": ICONS / "sandik.icns"}.get(
    sys.platform, ICONS / "sandik.png")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    hiddenimports=["sandik.gui.app", "PySide6.QtSvg"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.Qt3DCore", "PySide6.QtMultimedia"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="sandik",
          console=False, icon=str(icon), upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Sandik", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll, name="Sandık.app", icon=str(icon), bundle_identifier="org.sandik.app",
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
