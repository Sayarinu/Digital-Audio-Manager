"""Native view state; storage, downloads and network calls stay in processes."""

from PySide6.QtCore import QObject, Property, QSettings, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from .jobs import Worker
from .list_model import PageModel
from .util import needs_reconnect


class AppState(QObject):
    changed = Signal()
    preferencesChanged = Signal()
    dataChanged = Signal()
    libraryChanged = Signal()
    collectionChanged = Signal()
    tracksChanged = Signal()
    navigationChanged = Signal()
    searchChanged = Signal()

    def __init__(self, config, account, parent=None, fixture=None):
        super().__init__(parent)
        self.account = account
        self.settings = QSettings(str(config), QSettings.Format.IniFormat)
        self._data = fixture or {"playlists": [], "tracks": [], "jobs": [], "health": {}}
        self._view = "library"
        self._selected = ""
        self._search = ""
        self._history = []
        self._tracks = []
        self._playlists = []
        self._track_model = PageModel(self)
        self._playlist_model = PageModel(self)
        self._job_model = PageModel(self)
        self._search_model = PageModel(self)
        self._results = []
        self._search_pending = None
        self._search_error = ""
        self._remote_query = ""
        self.player = None
        self._fixture = fixture is not None
        self._error = ""
        self._preview = {}
        self._sync = {}
        self._busy = ""
        self._pending = None
        self._queue_id = None
        self._queue_error = ""
        self._closed = False
        self._mount = str(self.settings.value("deviceFolder", ""))
        self._reduced = self.settings.value("reducedMotion", False, type=bool)
        self.worker = Worker(self, timeout_ms=3600000)
        self.reader = Worker(self)
        self.catalog = Worker(self)
        self.catalog.succeeded.connect(self._search_finished)
        self.catalog.failed.connect(self._search_failed)
        self.downloader = Worker(self, timeout_ms=3600000)
        self.worker.succeeded.connect(self._finished)
        self.worker.failed.connect(self._failed)
        self.reader.succeeded.connect(self._read)
        self.reader.failed.connect(self._read_failed)
        self.downloader.succeeded.connect(self._queue_finished)
        self.downloader.failed.connect(self._queue_failed)
        self._read_pending = False
        self._revision = 0
        self._read_revision = 0
        self.poll = QTimer(self)
        self.poll.setInterval(1000)
        self.poll.timeout.connect(self.refresh)
        self.files_poll = QTimer(self)
        self.files_poll.setInterval(5000)
        self.files_poll.timeout.connect(self.refresh)
        account.sessionChanged.connect(self._session_changed)
        account.changed.connect(self._auto_start_queue, Qt.ConnectionType.QueuedConnection)
        self._sync_models()
        if not fixture:
            self.files_poll.start()
            self.run("initialize", {})

    @Property("QVariantMap", notify=dataChanged)
    def data(self):
        return {key: value for key, value in self._data.items() if key not in {"tracks", "playlists"}}

    @Property("QVariantList", notify=libraryChanged)
    def playlists(self):
        return self._playlists

    @Property("QVariantMap", notify=collectionChanged)
    def collection(self):
        return next((p for p in self.playlists if p["id"] == self._selected), {})

    @Property(QObject, constant=True)
    def trackModel(self):
        return self._track_model

    @Property(QObject, constant=True)
    def playlistModel(self):
        return self._playlist_model

    @Property(QObject, constant=True)
    def jobModel(self):
        return self._job_model

    @Property("QVariantList", notify=tracksChanged)
    def tracks(self):
        return self._tracks

    @Property(str, notify=tracksChanged)
    def searchQuery(self):
        return self._search

    def _filtered_tracks(self):
        rows = self._data.get("tracks", [])
        if self._selected:
            rows = [t for t in rows if t["playlist_id"] == self._selected]
        else:
            rows = list({t["video_id"]: t for t in rows}.values())
        if self._view == "downloads":
            rows = [t for t in rows if t["local_status"] == "ready" and not t["video_id"].startswith("local:")]
        term = self._search.casefold()
        return [t for t in rows if term in (t["title"] + " " + t["artist"] + " " + (t.get("album") or "")).casefold()]

    @Property(str, notify=navigationChanged)
    def view(self):
        return self._view

    @Property(str, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=changed)
    def queueRunning(self):
        return self._queue_id is not None

    @Property(bool, notify=dataChanged)
    def hasQueuedDownloads(self):
        return any(job.get("state") in {"queued", "retry"} for job in self._data.get("jobs", []))

    @Property(str, notify=changed)
    def queuePauseReason(self):
        return self._queue_error or self._data.get("queue_pause_reason", "")

    @Slot()
    def _auto_start_queue(self):
        if not self._fixture and not self._closed and not self.queuePauseReason:
            self.startQueue()

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property("QVariantMap", notify=changed)
    def preview(self):
        return self._preview

    @Property("QVariantMap", notify=changed)
    def syncProgress(self):
        return self._sync

    @Property(str, notify=changed)
    def mountPath(self):
        return self._mount

    @Property(float, constant=True)
    def uiScaleFactor(self):
        return 1.0

    @Property(bool, notify=preferencesChanged)
    def reducedMotion(self):
        return self._reduced

    @Slot(bool)
    def setReducedMotion(self, value):
        self._reduced = value
        self.settings.setValue("reducedMotion", value)
        self.preferencesChanged.emit()

    @Slot(str)
    def navigate(self, view):
        if view not in {"library", "downloads", "queue", "device", "settings", "search"}:
            return
        if (self._view, self._selected, self._search) == (view, "", ""):
            return
        self._history.append((self._view, self._selected, self._search))
        self._view, self._selected, self._search = view, "", ""
        self._navigated()

    @Slot(str)
    def selectCollection(self, identifier):
        if self._selected == identifier:
            return
        self._history.append((self._view, self._selected, self._search))
        self._selected, self._view, self._search = identifier, "library", ""
        self._navigated()

    @Slot(str)
    def search(self, text):
        if self._search != text:
            self._search = text
            self._sync_tracks()
            self.tracksChanged.emit()

    @Slot()
    def back(self):
        if self._history:
            self._view, self._selected, self._search = self._history.pop()
            self._navigated()

    def _navigated(self):
        self._sync_tracks(reset=True)
        self.collectionChanged.emit()
        self.navigationChanged.emit()
        self.changed.emit()
        if not self._fixture and self._view == "downloads":
            self.refresh()

    def _sync_tracks(self, reset=False):
        rows = self._filtered_tracks()
        if reset or rows != self._tracks:
            self._tracks = rows
            self._track_model.sync(rows, reset=reset)
            self.tracksChanged.emit()

    def _sync_models(self):
        artwork = {}
        for row in self._data.get("tracks", []):
            if row.get("artwork_url") and row["playlist_id"] not in artwork:
                artwork[row["playlist_id"]] = row["artwork_url"]
        playlists = [dict(row, artwork_url=artwork.get(row["id"], ""))
                     for row in self._data.get("playlists", [])]
        if playlists != self._playlists:
            self._playlists = playlists
            self._playlist_model.sync(playlists)
            self.libraryChanged.emit()
            self.collectionChanged.emit()
        self._job_model.sync(self._data.get("jobs", []))
        self._sync_tracks()
        self._sync_search()

    @Slot()
    def dismissError(self):
        self._error = ""
        self.changed.emit()

    @Slot(result=bool)
    def canClose(self):
        if self._busy in {"sync_apply", "reset_and_resync_library", "repair_library_metadata", "set_music_folder", "remove_download"}:
            self._error = "Wait for the current file operation to finish before closing the app."
            self.changed.emit()
            return False
        return True

    @Slot(QUrl)
    def setDevice(self, url):
        if url.isLocalFile():
            self._mount = url.toLocalFile()
            self.settings.setValue("deviceFolder", self._mount)
            self._preview = {}
            self.changed.emit()

    @Slot(QUrl)
    def setMusicFolder(self, url):
        if url.isLocalFile():
            self.run("set_music_folder", {"path": url.toLocalFile()})

    @Slot()
    def openLibrary(self):
        folder = self._data.get("health", {}).get("library_root")
        if folder and not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            self._error = "Could not open the download folder. Open it from your file manager."
            self.changed.emit()

    @Property(bool, notify=tracksChanged)
    def hasPlayableTracks(self):
        return any(row.get("local_status") == "ready" and row.get("media_path") for row in self._tracks)

    @Slot()
    def playCollection(self):
        row = next((row for row in self.tracks if row.get("local_status") == "ready" and row.get("media_path")), None)
        if row:
            self.openTrack(row["id"])

    @Slot(str)
    def openTrack(self, identifier):
        row = next((t for t in self._data.get("tracks", []) if t["id"] == identifier), {})
        if self.player and row:
            self.player.play_rows(self.tracks, row["video_id"])

    @Slot(str)
    def playSearchTrack(self, identifier):
        if self.player:
            self.player.play_rows(self._data.get("tracks", []), identifier)

    @Slot("QVariantList")
    def importFiles(self, urls):
        paths = [QUrl(url).toLocalFile() for url in urls if QUrl(url).isLocalFile()]
        if paths:
            self.run("import_local_files", {"paths": paths})

    @Property(QObject, constant=True)
    def searchModel(self):
        return self._search_model

    @Property(str, notify=searchChanged)
    def remoteQuery(self):
        return self._remote_query

    @Property(bool, notify=searchChanged)
    def searching(self):
        return self._search_pending is not None

    @Property(str, notify=searchChanged)
    def searchError(self):
        return self._search_error

    @Slot(str)
    def searchMusic(self, query):
        query = query.strip()
        if not query:
            return
        if self._search_pending is not None:
            self.catalog.cancel(self._search_pending)
        self.navigate("search")
        self._remote_query, self._search_error = query, ""
        self._results = []
        self._search_model.sync([], reset=True)
        self._search_pending = self.catalog.request("search_music", {"query": query})
        self.searchChanged.emit()

    @Slot(str)
    def queueSearchTrack(self, identifier):
        track = next((t for t in self._results if t["video_id"] == identifier), None)
        if track:
            self.run("queue_search_track", {"track": track})

    def _sync_search(self):
        local = {row["video_id"]: row for row in self._data.get("tracks", [])}
        rows = [dict(row, **{key: local[row["video_id"]][key] for key in ("local_status", "media_path")})
                if row["video_id"] in local else row for row in self._results]
        self._search_model.sync(rows)

    def _search_finished(self, identifier, result):
        if identifier != self._search_pending:
            return
        self._search_pending = None
        self._results = result.get("results", [])
        self._sync_search()
        self.searchChanged.emit()

    def _search_failed(self, identifier, error):
        if identifier == self._search_pending:
            self._search_pending = None
            self._search_error = error["message"]
            self.searchChanged.emit()

    @Slot(str, "QVariantMap")
    def run(self, operation, payload):
        if self._busy:
            return
        if operation in {"reset_and_resync_library", "set_music_folder", "repair_library_metadata", "sync_apply", "remove_download"} and self.queueRunning:
            self._error = "Wait for the download queue to finish before changing the library."
            self.changed.emit()
            return
        if self.player and operation in {"reset_and_resync_library", "repair_library_metadata", "remove_download"}:
            self.player.close()
        self._busy, self._error = operation, ""
        if operation not in {"sync_preview", "sync_status"}:
            self._preview = {}
        self._pending = self.worker.request(operation, payload)
        self.poll.start()
        self.changed.emit()

    @Slot()
    def startQueue(self):
        if (self._closed or self.queueRunning or self._busy or not self.hasQueuedDownloads
                or self.account.busy or self.account.reconnect):
            return
        self._queue_error = ""
        self._data["queue_pause_reason"] = ""
        self._queue_id = self.downloader.request("run_queue", {"authenticated": self.account.connected})
        self.poll.start()
        self.changed.emit()

    @Slot(str)
    def cancelJob(self, identifier):
        if self._busy:
            return
        job = next((j for j in self._data.get("jobs", []) if j["id"] == identifier), {})
        if job.get("state") == "running" and self._queue_id is not None:
            self.downloader.cancel(self._queue_id)
            self._queue_id = None
        self.run("cancel_job", {"job_id": identifier})

    @Slot()
    def refresh(self):
        if not self._read_pending:
            self._read_pending = True
            self._read_revision = self._revision
            self.reader.request("dashboard")
            if self._busy == "sync_apply":
                self.reader.request("sync_status", {"mount_path": self._mount})

    def _set_data(self, result):
        if self._data != result:
            self._data = result
            if self._selected and not any(p["id"] == self._selected for p in result.get("playlists", [])):
                self._selected = ""
            self._sync_models()
            self.dataChanged.emit()
            self.changed.emit()

    def _read(self, identifier, result):
        if "tracks" in result:
            self._read_pending = False
            if self._read_revision != self._revision:
                self.refresh()
                return
            self._set_data(result)
            self._auto_start_queue()
        else:
            self._sync = result
            self.changed.emit()

    def _read_failed(self, identifier, error):
        self._read_pending = False
        if not self._busy:
            self._error = error["message"]
            self.changed.emit()

    def _finished(self, identifier, result):
        if identifier != self._pending:
            return
        operation = self._busy
        if operation == "retry_job":
            self._queue_error = ""
        self._error = result.pop("notice", "")
        self._revision += 1
        self._busy, self._pending = "", None
        if operation in {"sync_preview", "sync_apply"}:
            self._preview = result
        elif "tracks" in result:
            self._set_data(result)
        self._settled()

    def _failed(self, identifier, error):
        self._busy, self._pending = "", None
        self._error = error["message"]
        if needs_reconnect(error):
            self.account.requireReconnect(error["message"])
        self._settled()

    def _queue_finished(self, identifier, result):
        if identifier != self._queue_id:
            return
        self._revision += 1
        self._queue_id = None
        self._set_data(result)
        self._settled()

    def _queue_failed(self, identifier, error):
        if identifier != self._queue_id:
            return
        self._queue_id = None
        self._queue_error = error["message"]
        self._error = error["message"]
        if needs_reconnect(error):
            self.account.requireReconnect(error["message"])
        self._settled()

    def _settled(self):
        self._auto_start_queue()
        if not self.queueRunning and not self._busy:
            self.poll.stop()
        self.changed.emit()

    def _session_changed(self):
        # Provider sessions are process-local; do not let a worker reuse the previous identity.
        self.worker.reset()
        self.downloader.reset()
        self._queue_id = None
        self._queue_error = ""
        self._busy, self._pending = "", None
        self.run("initialize", {})

    def close(self):
        self._closed = True
        self.files_poll.stop()
        self.poll.stop()
        for worker in (self.worker, self.reader, self.downloader, self.catalog):
            worker.close()
