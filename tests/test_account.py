from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer, QUrl, Signal
import sys

from dam.account.account import Account
from dam.jobs import Worker


class FakeWorker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.requests = []

    def request(self, operation, payload=None):
        self.requests.append((operation, payload))
        return len(self.requests)


def test_export_import_forgets_the_previous_accounts_browser(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    account = Account(tmp_path / "settings.ini", worker=worker, default_browser=lambda: None)
    app.processEvents()
    worker.succeeded.emit(1, {"connected": False})
    account.settings.setValue("signInBrowser", "firefox")
    account.importFile(QUrl.fromLocalFile(str(tmp_path / "browser.json")))
    worker.succeeded.emit(2, {"connected": True, "profile": {"name": "New account"}})
    assert account.connected
    assert not account.settings.value("signInBrowser", "")


def test_restore_and_failed_reconnect_keep_cached_identity(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    account = Account(tmp_path / "settings.ini", worker=worker)
    changes = []
    account.sessionChanged.connect(lambda: changes.append(True))
    app.processEvents()
    assert worker.requests == [("restore", None)]
    worker.succeeded.emit(1, {"connected": True, "profile": {"name": "Listener"}})
    account.requireReconnect("Session expired")
    assert not account.connected and account.reconnect
    account.importFile(QUrl.fromLocalFile(str(tmp_path / "browser.json")))
    worker.failed.emit(3, {"code": "offline", "message": "Offline"})
    assert account.profile["name"] == "Listener"
    assert account.reconnect and not account.busy
    assert changes == []
    account.importFile(QUrl.fromLocalFile(str(tmp_path / "browser.json")))
    worker.succeeded.emit(4, {"connected": True, "profile": {"name": "Listener"}})
    assert account.connected and not account.reconnect
    assert changes == [True]
    signed_out = []
    account.signedOut.connect(lambda: signed_out.append(True))
    account.signOut()
    assert not signed_out, "Nothing is removed until sign-out has succeeded"
    worker.succeeded.emit(5, {"connected": False, "profile": {}})
    assert not account.connected and account.profile == {}
    assert changes == [True, True] and signed_out == [True]


def test_provider_requests_are_asynchronous_and_errors_are_sanitized():
    _app = QCoreApplication.instance() or QCoreApplication([])
    worker = Worker()
    loop = QEventLoop()
    results = []
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(1)

    def failed(identifier, error):
        results.append((identifier, error))
        if len(results) == 2:
            loop.quit()

    worker.failed.connect(failed)
    worker.request("unknown", {"private": "never echo this"})
    cancelled = worker.request("unknown")
    worker.cancelQueued(cancelled)
    worker.request("unknown")
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    timer.stop()
    worker.close()
    assert [identifier for identifier, _ in results] == [1, 3]
    assert ticks
    assert "never echo" not in str(results)
    assert all(error["code"] == "operation_failed" for _, error in results)


def test_idle_worker_releases_process_and_starts_again_for_next_request():
    _app = QCoreApplication.instance() or QCoreApplication([])
    worker = Worker(idle_ms=5)
    loop = QEventLoop()
    results, starts = [], []
    worker.process.started.connect(lambda: starts.append(True))

    def failed(identifier, error):
        results.append(identifier)
        if identifier == 1:
            QTimer.singleShot(100, lambda: worker.request("unknown"))
        else:
            loop.quit()

    worker.failed.connect(failed)
    worker.request("unknown")
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    worker.close()
    assert results == [1, 2] and len(starts) == 2


def test_cancelling_an_active_job_preserves_later_queued_work():
    _app = QCoreApplication.instance() or QCoreApplication([])
    worker = Worker()
    worker.process.setArguments(["-u", "-c", "import json,sys,time\nfor line in sys.stdin:\n r=json.loads(line)\n if r['operation']=='slow': time.sleep(5)\n print(json.dumps({'id':r['id'],'ok':True,'result':{}}),flush=True)"])
    worker.process.setProgram(sys.executable)
    loop = QEventLoop()
    results, failures = [], []
    worker.succeeded.connect(lambda identifier, value: (results.append(identifier), loop.quit() if len(results) == 2 else None))
    worker.failed.connect(lambda identifier, error: failures.append(identifier))
    slow = worker.request("slow")
    second = worker.request("fast")
    def cancel_active():
        if not worker._active:
            QTimer.singleShot(10, cancel_active)
            return
        worker.cancel(slow)
        worker.request("fast")
    QTimer.singleShot(30, cancel_active)
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    worker.close()
    assert results == [second, 3] and not failures


def scripted_worker(**options):
    worker = Worker(**options)
    worker.process.setProgram(sys.executable)
    worker.process.setArguments(["-u", "-c", "import json,sys\nfor line in sys.stdin:\n r=json.loads(line)\n print(json.dumps({'id':r['id'],'ok':True,'result':{'operation':r['operation']}}),flush=True)"])
    return worker


def test_warm_worker_sends_its_warmup_first_without_reporting_it():
    _app = QCoreApplication.instance() or QCoreApplication([])
    worker = scripted_worker(warmup=("warmup", {"data_dir": "fixture"}))
    loop = QEventLoop()
    results, starts = [], []
    worker.process.started.connect(lambda: starts.append(True))

    def succeeded(identifier, result):
        results.append(result["operation"])
        if len(results) == 1:
            # A cancelled active request restarts the process, which warms up again.
            worker.cancel(worker.request("slow"))
            QTimer.singleShot(300, lambda: worker.request("resolve"))
        else:
            loop.quit()

    worker.succeeded.connect(succeeded)
    worker.prestart()
    QTimer.singleShot(200, lambda: worker.request("resolve"))
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    worker.close()
    assert results == ["resolve", "resolve"] and len(starts) == 2


def test_cold_request_on_a_warm_worker_answers_under_its_own_identifier():
    _app = QCoreApplication.instance() or QCoreApplication([])
    worker = scripted_worker(warmup=("warmup", {}))
    loop = QEventLoop()
    results = []
    worker.succeeded.connect(lambda identifier, result: (results.append((identifier, result["operation"])), loop.quit()))
    identifier = worker.request("resolve")
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    worker.close()
    assert results == [(identifier, "resolve")]


def test_idle_warm_worker_stays_stopped_until_needed():
    _app = QCoreApplication.instance() or QCoreApplication([])
    worker = scripted_worker(idle_ms=5, warmup=("warmup", {}))
    loop = QEventLoop()
    starts = []
    worker.process.started.connect(lambda: starts.append(True))
    worker.prestart()
    QTimer.singleShot(1500, loop.quit)
    loop.exec()
    assert len(starts) == 1 and worker.process.state() == worker.process.ProcessState.NotRunning
    worker.close()


def test_kept_warm_worker_comes_back_after_idling_out_and_reports_ready():
    _app = QCoreApplication.instance() or QCoreApplication([])
    worker = scripted_worker(idle_ms=5, warmup=("warmup", {}))
    loop = QEventLoop()
    starts, interrupted = [], []
    worker.process.started.connect(lambda: starts.append(True))

    def interrupt_first_idle_stop():
        # Activity during an idle stop already under way brings the process straight back.
        if not interrupted:
            interrupted.append(worker._hibernating)
            worker.keepWarm()

    worker.idle_timer.timeout.connect(interrupt_first_idle_stop)
    assert not worker.ready()
    worker.prestart()
    QTimer.singleShot(2500, loop.quit)
    loop.exec()
    assert interrupted == [True] and len(starts) == 2 and not worker.ready()
    assert worker.process.state() == worker.process.ProcessState.NotRunning
    # Hovering or a starting track re-warms a worker that idled out.
    worker.idle_timer.setInterval(60000)
    worker.keepWarm()
    QTimer.singleShot(1500, loop.quit)
    loop.exec()
    assert len(starts) == 3 and worker.ready()
    worker.idle_timer.stop()
    worker.keepWarm()
    assert worker.idle_timer.isActive()  # A running, idle worker only extends its idle time.
    worker.request("resolve")
    assert not worker.ready()
    worker.close()



def browser_account(tmp_path, clock, default="firefox"):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker, opened = FakeWorker(), []
    account = Account(tmp_path / "settings.ini", worker=worker, clock=lambda: clock[0], open_url=opened.append, default_browser=lambda: default)
    app.processEvents()
    return account, worker, opened


def test_browser_sign_in_connects_from_the_default_browser_first(tmp_path):
    clock = [1000.]
    account, worker, opened = browser_account(tmp_path, clock)
    worker.succeeded.emit(1, {"connected": False, "profile": {}})
    account.signIn()
    assert account.signingIn and worker.requests[-1][0] == "import_browser"
    assert worker.requests[-1][1]["browsers"][:2] == ["firefox", "chrome"]
    changes = []
    account.sessionChanged.connect(lambda: changes.append(True))
    worker.succeeded.emit(2, {"connected": True, "profile": {"name": "Listener"}, "captured": clock[0], "browser": "firefox"})
    assert account.connected and not account.signingIn and changes == [True] and opened == []
    assert account.settings.value("signInBrowser") == "firefox"


def test_unsigned_browser_is_opened_and_watched_until_sign_in_or_timeout(tmp_path):
    clock = [1000.]
    account, worker, opened = browser_account(tmp_path, clock, default="chrome")
    worker.succeeded.emit(1, {"connected": False, "profile": {}})
    account.signIn()
    worker.failed.emit(2, {"code": "NoBrowserSession", "message": "Sign in to YouTube Music in your browser to connect."})
    assert [url.toString() for url in opened] == ["https://music.youtube.com/"]
    assert account.signingIn and "your browser" in account.message
    account._check_browser()
    assert worker.requests[-1] == ("import_browser", {"browsers": ["chrome"]})
    worker.failed.emit(3, {"code": "NoBrowserSession", "message": "not yet"})
    assert account.signingIn and "your browser" in account.message
    account._check_browser()
    worker.succeeded.emit(4, {"connected": True, "profile": {"name": "Listener"}, "browser": "chrome"})
    assert account.connected and not account.signingIn
    account.signOut()
    worker.succeeded.emit(5, {"connected": False, "profile": {}})
    assert not account.settings.value("signInBrowser")
    account.signIn()
    worker.failed.emit(6, {"code": "NoBrowserSession", "message": "none"})
    clock[0] += 3600
    account._check_browser()
    assert not account.signingIn and "No YouTube Music sign-in" in account.message
    assert len(worker.requests) == 6


def test_blocked_browser_reports_why_instead_of_waiting(tmp_path):
    account, worker, opened = browser_account(tmp_path, [1000.], default="safari")
    worker.succeeded.emit(1, {"connected": False, "profile": {}})
    account.signIn()
    worker.failed.emit(2, {"code": "BrowserBlocked", "message": "Allow Tubify Full Disk Access"})
    assert not account.signingIn and opened == [] and "Full Disk Access" in account.message
    account.signIn()
    worker.failed.emit(3, {"code": "NoBrowserSession", "message": "none"})
    account.cancelSignIn()
    assert not account.signingIn and account.message == ""


def test_expired_session_is_renewed_from_the_browser_before_asking(tmp_path):
    clock = [10 * 24 * 3600.]
    account, worker, opened = browser_account(tmp_path, clock)
    account.settings.setValue("signInBrowser", "firefox")
    worker.succeeded.emit(1, {"connected": True, "profile": {"name": "Listener"}, "captured": 1.})
    assert worker.requests[-1] == ("verify_session", None)
    worker.succeeded.emit(2, {"captured": 1.})
    assert worker.requests[-1] == ("import_browser", {"browsers": ["firefox"]})
    worker.failed.emit(3, {"code": "NoBrowserSession", "message": "none"})
    assert account.connected and not account.reconnect and opened == []
    account.requireReconnect("Session expired")
    assert len(worker.requests) == 3 and account.reconnect and account.message == "Session expired"
    clock[0] += 3600
    account._reconnect = False
    account.requireReconnect("Session expired")
    assert worker.requests[-1][0] == "import_browser" and not account.reconnect
    worker.succeeded.emit(4, {"connected": True, "profile": {"name": "Listener"}, "browser": "firefox"})
    assert account.connected and not account.reconnect


def restored_account(tmp_path):
    account, worker, opened = browser_account(tmp_path, [1000.])
    account.settings.setValue("signInBrowser", "firefox")
    worker.succeeded.emit(1, {"connected": True, "profile": {"name": "Listener"}, "captured": 900.})
    assert worker.requests[-1] == ("verify_session", None) and account.connected and not account.busy
    return account, worker


def test_session_youtube_music_no_longer_accepts_is_renewed_at_launch(tmp_path):
    account, worker = restored_account(tmp_path)
    worker.failed.emit(2, {"code": "AuthError", "message": "Signed out"})
    assert worker.requests[-1] == ("import_browser", {"browsers": ["firefox"]}) and not account.reconnect
    worker.succeeded.emit(3, {"connected": True, "profile": {"name": "Listener"}, "browser": "firefox", "captured": 1000.})
    assert account.connected and not account.reconnect
    # A renewed session has just been validated, so it isn't checked again.
    assert len(worker.requests) == 3


def test_session_that_cannot_be_renewed_at_launch_asks_to_sign_in_again(tmp_path):
    account, worker = restored_account(tmp_path)
    worker.failed.emit(2, {"code": "reconnect", "message": "Session rejected"})
    worker.failed.emit(3, {"code": "NoBrowserSession", "message": "none"})
    assert account.reconnect and account.message == "Session rejected"


def test_valid_session_is_not_read_from_the_browser_at_launch(tmp_path):
    account, worker = restored_account(tmp_path)
    worker.succeeded.emit(2, {"captured": 900.})
    assert len(worker.requests) == 2 and account.connected


def test_offline_launch_keeps_the_saved_session(tmp_path):
    for code in ("offline", "provider_error", "timeout", "cancelled"):
        account, worker = restored_account(tmp_path)
        message = account.message
        worker.failed.emit(2, {"code": code, "message": "Try later"})
        assert len(worker.requests) == 2 and account.connected and not account.reconnect and account.message == message


def test_launch_check_does_not_interrupt_a_sign_in_under_way(tmp_path):
    account, worker = restored_account(tmp_path)
    account.signIn()
    assert worker.requests[-1][0] == "import_browser"
    worker.failed.emit(2, {"code": "AuthError", "message": "Signed out"})
    assert not account.reconnect and len(worker.requests) == 3
    worker.succeeded.emit(3, {"connected": True, "profile": {"name": "Listener"}, "browser": "firefox"})
    assert account.connected and not account.reconnect


def test_unreadable_saved_session_is_replaced_from_the_browser_without_a_banner(tmp_path):
    account, worker, opened = browser_account(tmp_path, [1000.])
    account.settings.setValue("signInBrowser", "firefox")
    worker.failed.emit(1, {"code": "CredentialError", "message": "The saved session could not be read."})
    assert worker.requests[-1] == ("import_browser", {"browsers": ["firefox"]}) and not account.reconnect
    worker.succeeded.emit(2, {"connected": True, "profile": {"name": "Listener"}, "browser": "firefox"})
    assert account.connected and not account.reconnect


def test_timed_out_job_fails_alone_and_queued_work_continues():
    _app = QCoreApplication.instance() or QCoreApplication([])
    worker = Worker()
    loop = QEventLoop()
    results = []

    def failed(identifier, error):
        results.append((identifier, error["code"]))
        if len(results) == 2:
            loop.quit()

    worker.failed.connect(failed)
    worker.request("unknown")
    worker.request("unknown")

    def expire_first():
        if worker._active is None:
            QTimer.singleShot(5, expire_first)
        else:
            worker._timeout()

    expire_first()
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    worker.close()
    assert results[0] == (1, "timeout")
    assert results[1][0] == 2 and results[1][1] != "timeout"
