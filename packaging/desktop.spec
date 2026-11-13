"""Build on the target OS; Qt and Python are bundled, no system Python required."""

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
datas = [(str(root / "native/src/dam/qml"), "dam/qml"),
         (str(root / "native/src/dam/assets"), "dam/assets")]
binaries = []
hiddenimports = collect_submodules("keyring.backends")
for package in ("yt_dlp", "yt_dlp_ejs", "ytmusicapi"):
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden

analysis = Analysis(
    [str(root / "packaging/entry.py")], pathex=[str(root / "native/src")],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
)
archive = PYZ(analysis.pure)
icon = root / "native/src/dam/assets" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")
exe = EXE(archive, analysis.scripts, [], exclude_binaries=True, name="Digital Audio Manager",
          console=sys.platform != "darwin", icon=str(icon),
          hide_console="hide-early" if sys.platform == "win32" else None)
bundle = COLLECT(exe, analysis.binaries, analysis.datas, name="Digital Audio Manager")
if sys.platform == "darwin":
    bundle = BUNDLE(bundle, name="Digital Audio Manager.app", icon=str(icon),
                    bundle_identifier="studio.nouvellelune.digitalaudiomanager")
