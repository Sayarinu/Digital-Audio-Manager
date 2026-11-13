from PySide6.QtCore import QCoreApplication, QObject, Signal

from dam.state import AppState


class FakeWorker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.requests = []
        self.cancelled = []

    def request(self, operation, payload=None):
        self.requests.append((operation, payload))
        return len(self.requests)

    def reset(self):
        pass

    def cancel(self, identifier):
        self.cancelled.append(identifier)

    def close(self):
        pass


class FakeAccount(QObject):
    sessionChanged = Signal()
    connected = False


def make_state(tmp_path, monkeypatch):
    monkeypatch.setattr("dam.state.Worker", FakeWorker)
    account = FakeAccount()
    state = AppState(tmp_path / "native.ini", account,
                     fixture={"playlists": [], "tracks": [], "jobs": [], "health": {}})
    return state


def test_stale_poll_cannot_replace_a_completed_change(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state.refresh()
    state.run("queue_track", {"video_id": "video"})
    current = {"tracks": [], "playlists": [], "jobs": [{"id": "new"}]}
    state.worker.succeeded.emit(1, current)
    state.reader.succeeded.emit(1, {"tracks": [], "playlists": [], "jobs": []})
    assert state.data["jobs"] == current["jobs"]
    assert state.tracks == []
    assert len(state.reader.requests) == 2
    state.close()


def test_queue_runs_once_and_cancel_stops_the_active_worker(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state._data["jobs"] = [{"id": "active", "state": "running"}]
    state.startQueue()
    state.startQueue()
    assert len(state.downloader.requests) == 1
    state.cancelJob("active")
    assert state.downloader.cancelled == [1]
    assert state.worker.requests == [("cancel_job", {"job_id": "active"})]
    assert not state.queueRunning
    state.close()


def test_closing_waits_for_device_file_operations(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state.run("sync_apply", {"mount_path": str(tmp_path)})
    assert not state.canClose()
    state.worker.succeeded.emit(1, {"physical_files_after": 0})
    assert state.canClose()
    state.close()


def catalog(count=100):
    return {"playlists": [{"id": "playlist", "title": "Test", "track_count": count}],
            "tracks": [{"id": str(i), "video_id": str(i), "playlist_id": "playlist", "title": f"Song {i}",
                        "artist": "Artist", "local_status": "missing"} for i in range(count)],
            "jobs": [], "health": {}}


def test_busy_feedback_and_identical_poll_do_not_rebuild_catalog(tmp_path, monkeypatch):
    from copy import deepcopy
    from PySide6.QtTest import QSignalSpy

    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    snapshot = catalog(8000)
    state._set_data(snapshot)
    reset = QSignalSpy(state.trackModel.modelReset)
    changed = QSignalSpy(state.trackModel.dataChanged)
    library = QSignalSpy(state.libraryChanged)
    state.run("queue_track", {"video_id": "1"})
    state._set_data(deepcopy(snapshot))
    assert reset.count() == changed.count() == library.count() == 0
    assert state.trackModel.rowCount() == 8000
    assert "tracks" not in state.data  # Shell progress bindings never serialize the song catalog.
    updated = deepcopy(snapshot)
    updated["tracks"][40]["local_status"] = "ready"
    state._set_data(updated)
    assert reset.count() == 0 and changed.count() == 1 and library.count() == 0
    assert changed.at(0)[0].row() == changed.at(0)[1].row() == 40
    state.close()


def test_search_and_back_use_local_catalog_without_worker_calls(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state._set_data(catalog())
    state.selectCollection("playlist")
    state.search("Song 42")
    assert [row["id"] for row in state.tracks] == ["42"]
    state.navigate("downloads")
    assert state.tracks == []
    state.back()
    assert state.collection["id"] == "playlist"
    assert state.searchQuery == "Song 42"
    assert [row["id"] for row in state.tracks] == ["42"]
    assert not state.worker.requests and not state.reader.requests
    state.close()


def test_new_search_cancels_old_request_and_ignores_stale_results(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state.searchMusic('first')
    state.searchMusic('second')
    assert state.catalog.cancelled == [1]
    state.catalog.succeeded.emit(1, {'results': [{'video_id': 'stale'}]})
    assert state.searchModel.rowCount() == 0 and state.searching
    track = dict(video_id='abcdefghijk', title='Selected', artist='Artist')
    state.catalog.succeeded.emit(2, {'results': [track]})
    assert state.searchModel.rowCount() == 1 and not state.searching
    state.queueSearchTrack('abcdefghijk')
    assert state.worker.requests == [('queue_search_track', {'track': track})]
    state.close()
