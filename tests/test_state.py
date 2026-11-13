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
    changed = Signal()
    busy = False
    reconnect = False
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
    state._data["jobs"] = [{"id": "active", "state": "queued"}]
    state.startQueue()
    state.startQueue()
    assert len(state.downloader.requests) == 1
    state._data["jobs"][0]["state"] = "running"
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


def queued_snapshot(*identifiers, pause=''):
    return dict(tracks=[], playlists=[], health={}, queue_pause_reason=pause,
                jobs=[dict(id=identifier, state='queued') for identifier in identifiers])


def test_queued_download_starts_after_enqueue_and_resumes_on_launch(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    for operation in ('initialize', 'queue_track', 'queue_playlist', 'queue_search_track', 'import_to_unsorted', 'retry_job'):
        state = make_state(tmp_path, monkeypatch)
        state._fixture = False
        state.run(operation, {})
        state.worker.succeeded.emit(1, queued_snapshot('song'))
        assert state.downloader.requests == [('run_queue', {'authenticated': False})]
        state._read(1, queued_snapshot('song'))
        assert len(state.downloader.requests) == 1
        state.downloader.succeeded.emit(1, queued_snapshot())
        assert not state.queueRunning
        state.close()


def test_auto_queue_waits_for_account_restore_and_file_operations(tmp_path, monkeypatch):
    app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state._fixture = False
    state.account.busy = True
    state._read(1, queued_snapshot('song'))
    assert not state.downloader.requests
    state.account.busy = False
    state.run('sync_apply', {})
    state.account.changed.emit()
    app.processEvents()
    assert not state.downloader.requests
    state.worker.succeeded.emit(1, {'physical_files_after': 0})
    assert len(state.downloader.requests) == 1
    state.close()


def test_queue_processes_new_work_after_a_previous_run_finishes(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state._fixture = False
    state._read(1, queued_snapshot('first'))
    state.run('queue_track', {})
    state.downloader.succeeded.emit(1, queued_snapshot())
    assert len(state.downloader.requests) == 1
    state.worker.succeeded.emit(1, queued_snapshot('new'))
    assert len(state.downloader.requests) == 2
    state.close()


def test_failed_worker_does_not_loop_and_manual_resume_is_possible(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state._fixture = False
    state._read(1, queued_snapshot('song'))
    state.downloader.failed.emit(1, {'code': 'provider_error', 'message': 'Check your connection.'})
    state._read(2, queued_snapshot('song'))
    state._auto_start_queue()
    assert len(state.downloader.requests) == 1 and state.queuePauseReason
    state.startQueue()
    assert len(state.downloader.requests) == 2 and not state.queuePauseReason
    state.close()


def test_rate_limit_pause_survives_refresh_and_cancellation_moves_to_next_song(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state._fixture = False
    state._read(1, queued_snapshot('first', 'next', pause='Rate limited. Retry later.'))
    assert not state.downloader.requests
    state.startQueue()
    state._data['jobs'][0]['state'] = 'running'
    state.cancelJob('first')
    state.downloader.succeeded.emit(1, queued_snapshot('stale'))
    assert [j['id'] for j in state.data['jobs']] == ['first', 'next']
    state.worker.succeeded.emit(1, queued_snapshot('next'))
    assert len(state.downloader.requests) == 2
    assert state.downloader.cancelled == [1]
    state.close()


def test_failed_only_and_synthetic_queues_never_start_automatically(tmp_path, monkeypatch):
    _app = QCoreApplication.instance() or QCoreApplication([])
    state = make_state(tmp_path, monkeypatch)
    state._read(1, queued_snapshot('synthetic'))
    assert not state.downloader.requests
    state._fixture = False
    snapshot = queued_snapshot('failed')
    snapshot['jobs'][0]['state'] = 'failed'
    state._read(2, snapshot)
    assert not state.downloader.requests
    state.close()
    state._read(3, queued_snapshot('after-close'))
    assert not state.downloader.requests
