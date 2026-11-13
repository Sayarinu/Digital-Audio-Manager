"""Qt Quick application bootstrap. No account reads during synthetic checks."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QLockFile, QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .account.account import Account
from .paths import data_directory
from .state import AppState
from .theme import ThemeState


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--screenshot")
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--view", choices=["library", "downloads", "queue", "device", "settings", "collection"], default="library")
    parser.add_argument("--theme", default="classic-dark")
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=820)
    parser.add_argument("--dialog", choices=["account", "import"])
    parser.add_argument("--state", choices=["loading", "error"])
    args = parser.parse_args()
    synthetic = args.fixture or args.smoke_test or bool(args.screenshot)
    temporary = tempfile.TemporaryDirectory(prefix="dam-preview-") if synthetic else None
    if temporary:
        os.environ["MP3_MAKER_APP_DATA"] = str(Path(temporary.name) / "data")
        os.environ["MP3_MAKER_LIBRARY"] = str(Path(temporary.name) / "Music" / "Digital Audio Manager" / "Library")
    QQuickStyle.setStyle("Basic")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Digital Audio Manager")
    app.setOrganizationName("Nouvelle Lune Atelier")
    assets = Path(__file__).parent / "assets"
    for name in ("Roboto-Regular.ttf", "Roboto-Bold.ttf"):
        QFontDatabase.addApplicationFont(str(assets / name))
    font = QFont("Roboto")
    font.setPixelSize(14)
    app.setFont(font)
    app.setWindowIcon(QIcon(str(assets / "icon.png")))
    root = data_directory()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        root.chmod(0o700)
    lock = QLockFile(str(root / "native.lock"))
    if not lock.tryLock(0):
        print("Digital Audio Manager is already open.", file=sys.stderr)
        return 1
    config = root / "native.ini"
    account = Account(config, fixture=synthetic)
    fixture = json.loads((assets / "preview.json").read_text()) if synthetic else None
    if fixture and args.empty:
        fixture.update(playlists=[], tracks=[], jobs=[])
    state = AppState(config, account, fixture=fixture)
    theme = ThemeState(config)
    if synthetic:
        if args.view == "collection" and fixture["playlists"]:
            state.selectCollection(fixture["playlists"][0]["id"])
        else:
            state.navigate(args.view)
        if args.state == "loading":
            state._busy = "initialize"
        elif args.state == "error":
            state._error = "Could not refresh your library. Check your connection and retry."
        theme.selectTheme(args.theme)
    engine = QQmlApplicationEngine()
    for name, value in (("appState", state), ("account", account), ("accountState", account), ("themeState", theme)):
        engine.rootContext().setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    if not engine.rootObjects():
        state.close()
        account.close()
        lock.unlock()
        return 1
    window = engine.rootObjects()[0]
    window.setWidth(args.width if synthetic else max(920, min(state.settings.value("windowWidth", 1280, type=int), app.primaryScreen().availableGeometry().width())))
    window.setHeight(args.height if synthetic else max(620, min(state.settings.value("windowHeight", 820, type=int), app.primaryScreen().availableGeometry().height())))

    if synthetic and args.dialog:
        QTimer.singleShot(0, window.openAccount if args.dialog == "account" else window.openImport)

    def shutdown():
        state.settings.setValue("windowWidth", window.width())
        state.settings.setValue("windowHeight", window.height())
        state.settings.sync()
        state.close()
        account.close()

    app.aboutToQuit.connect(shutdown)
    if args.screenshot:
        QTimer.singleShot(1200, lambda: window.grabWindow().save(args.screenshot))
    if args.smoke_test or args.screenshot:
        QTimer.singleShot(1500, app.quit)
    result = app.exec()
    # Destroy QML bindings before their context objects.
    del engine
    lock.unlock()
    if temporary:
        temporary.cleanup()
    return result
