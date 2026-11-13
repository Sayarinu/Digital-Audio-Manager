"""Exercise native clicks and catalog updates with a synthetic account and no worker requests."""

import copy
import json
import os
from pathlib import Path
import statistics
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QPointF, Property, Qt, QUrl, Slot
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dam import app as application
from dam.account.account import Account
from dam.state import AppState
from dam.player import Player
from dam.color_picker import ColorSampler
from dam.updates.maintenance import Maintenance
from dam.theme import ThemeState


class PreviewAccount(Account):
    @Property(bool, constant=True)
    def signInAvailable(self):
        return True

    @Slot()
    def signIn(self):
        self._mode = "waiting"
        self.changed.emit()

    @Slot()
    def cancelSignIn(self):
        self._mode = ""
        self.changed.emit()


def main():
    QQuickStyle.setStyle("Basic")
    app = QApplication([])
    package = Path(application.__file__).parent
    for name in ("Roboto-Regular.ttf", "Roboto-Bold.ttf"):
        QFontDatabase.addApplicationFont(str(package / "assets" / name))
    font = QFont("Roboto")
    font.setPixelSize(14)
    app.setFont(font)
    with tempfile.TemporaryDirectory(prefix="dam-interactions-") as directory:
        config = Path(directory) / "native.ini"
        account = PreviewAccount(config, fixture=True)
        account._profile = {}
        fixture = json.loads((package / "assets" / "preview.json").read_text())
        fixture["tracks"] = [dict(fixture["tracks"][0], id=str(i), video_id=str(i), title=f"Song {i}")
                             for i in range(8000)]
        fixture["playlists"][0]["track_count"] = 8000
        artwork = Path(directory) / "artwork.svg"
        artwork.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#627a84"/><circle cx="100" cy="100" r="60" fill="#223440"/></svg>')
        fixture["tracks"][0]["artwork_url"] = QUrl.fromLocalFile(str(artwork)).toString()
        state = AppState(config, account, fixture=fixture)
        player = Player(config)
        state.player = player
        theme = ThemeState(config)
        maintenance = Maintenance(Path(directory) / "release.json", state, fixture=True)
        color_sampler = ColorSampler()
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda messages: warnings.extend(str(message) for message in messages))
        for name, value in (("appState", state), ("account", account), ("accountState", account), ("themeState", theme), ("colorSampler", color_sampler), ("maintenanceState", maintenance), ("playerState", player)):
            engine.rootContext().setContextProperty(name, value)
        engine.load(QUrl.fromLocalFile(str(package / "qml" / "Main.qml")))
        assert engine.rootObjects(), "Window failed to load"
        window = engine.rootObjects()[0]
        QTest.qWait(300)

        def find(name):
            item = window.findChild(QObject, name)
            if item is None:
                pending = [window.contentItem()]
                while pending:
                    visual = pending.pop()
                    if visual.objectName() == name:
                        item = visual
                        break
                    pending.extend(visual.childItems())
            assert item is not None, name
            return item

        def click(name):
            item = find(name)
            assert isinstance(item, QQuickItem) and item.isVisible(), name
            point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)

        timings = []
        for _ in range(5):
            start = time.perf_counter()
            click("settingsButton")
            assert find("settingsDialog").property("visible")
            timings.append((time.perf_counter() - start) * 1000)
            QTest.qWait(250)
            click("closeSettings")
            QTest.qWait(250)
        click("settingsButton")
        QTest.qWait(250)
        click("themeCard-mint")
        assert theme.activeThemeId == "mint"
        click("addThemeButton")
        QTest.qWait(200)
        menu = find("addThemeMenu")
        menu.setProperty("currentIndex", 0)
        QTest.keyClick(window, Qt.Key.Key_Return)
        QTest.qWait(250)
        find("themeNameField").setProperty("text", "Synthetic custom theme")
        click("themeNameSave")
        QTest.qWait(250)
        assert theme.activeThemeIsCustom
        assert find("appearanceSettingsDialog").property("editingColors")
        click("settingsNav-updateSettings")
        assert find("updateChannelOption").property("currentIndex") == 0
        find("updateChannelOption").setProperty("currentIndex", 1)
        find("updateChannelOption").activated.emit(1)
        assert maintenance.channel == "experimental"
        assert not maintenance.busy  # Fixture checks must never query GitHub.
        click("closeSettings")
        QTest.qWait(250)
        click("profileButton")
        assert find("accountDialog").property("visible")
        QTest.qWait(250)
        click("browserSignIn")
        assert account.signingIn
        assert "Waiting" in find("browserSignIn").property("text")
        QTest.qWait(250)
        window.grabWindow().save(str(Path(directory) / "browser-sign-in.png"))
        click("cancelBrowserSignIn")
        assert not account.signingIn
        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.qWait(250)
        assert not find("accountDialog").property("visible")
        state.navigate("downloads")
        QTest.qWait(300)
        songs = find("librarySongs")
        songs.setProperty("contentY", 400.0)
        QTest.qWait(50)
        position = songs.property("contentY")
        sample = copy.deepcopy(fixture)
        sample["tracks"][40]["title"] = "Updated song"
        start = time.perf_counter()
        state._set_data(sample)
        app.processEvents()
        update_ms = (time.perf_counter() - start) * 1000
        assert songs.property("contentY") == position
        assert state.trackModel.rowCount() == 8000
        player._queue, player._index = [fixture["tracks"][0]], 0
        player.changed.emit()
        click("playerTrackToggle")
        QTest.qWait(320)
        assert window.property("expanded")
        assert find("expandedPlayer").isVisible()
        assert find("immersiveTrackTitle").property("text") == fixture["tracks"][0]["title"]
        click("playPauseButton")
        assert window.property("expanded")  # Playback controls must not toggle the surrounding view.
        player._queue[0] = dict(player._queue[0], title="The next local song")
        player.changed.emit()
        assert find("immersiveTrackTitle").property("text") == "The next local song"
        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.qWait(320)
        assert not window.property("expanded") and songs.property("contentY") == position
        click("immersiveToggle")
        QTest.qWait(320)
        click("closeExpandedPlayer")
        QTest.qWait(320)
        assert not window.property("expanded")
        click("queueToggle")
        QTest.qWait(300)
        state.setReducedMotion(True)
        click("queueToggle")
        QTest.qWait(50)
        click("playerTrackToggle")
        assert window.property("expanded")
        assert find("expandedPlayer").property("slide") == 0
        player.close()
        assert not window.property("expanded")
        assert not warnings, "\n".join(warnings)
        print(json.dumps({"settings_open_median_ms": round(statistics.median(timings), 2),
                          "update_8000_rows_ms": round(update_ms, 2), "scroll_preserved": True}))
        player.close()
        maintenance.close()
        state.close()
        account.close()
        # Destroy bindings while their context objects still exist.
        window = None
        del engine
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
