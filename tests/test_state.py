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
    assert state.data == current
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
