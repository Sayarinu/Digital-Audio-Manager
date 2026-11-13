"""Asynchronous provider-process transport shared by account and catalog jobs."""

from collections import deque
import json
import os
import signal
import subprocess

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .launcher import process_command


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)
    progress = Signal(int, dict)

    def __init__(self, parent=None, idle_ms=0, warmup=None, timeout_ms=60000):
        super().__init__(parent)
        # An optional (operation, payload) sent first whenever the process starts, so
        # imports and credential reads happen before a user request needs them.
        self._warmup = warmup
        self._timeout_ms = timeout_ms
        self._internal = set()
        self._idle_stop = False
        self.process = QProcess(self)
        if os.name == "posix":
            self.process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        command = process_command("provider")
        self.process.setProgram(command[0])
        self.process.setArguments(command[1:])
        self.process.started.connect(self._pump)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.errorOccurred.connect(self._error)
        self.process.finished.connect(self._finished)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.setInterval(idle_ms)
        self.idle_timer.timeout.connect(self._hibernate)
        self._idle_ms, self._hibernating = idle_ms, False
        self._queue = deque()
        self._active = None
        self._buffer = b""
        self._counter = 0
        self._closed = False

    def request(self, operation, payload=None):
        if self._closed:
            raise RuntimeError("The provider worker is closed")
        self._counter += 1
        identifier = self._counter
        self._queue.append({"id": identifier, "operation": operation, "payload": payload or {}})
        self._pump()
        return identifier

    def prestart(self):
        """Start the process ahead of demand; does nothing without a warmup request."""
        if (self._warmup and not self._closed and not self._hibernating and not self._active and not self._queue
                and self.process.state() == QProcess.ProcessState.NotRunning):
            self._enqueue_warmup()
            self._pump()

    def keepWarm(self):
        """Hold a warm process back from idling out, or bring back one that already has."""
        if self._closed or not self._warmup:
            return
        if self._hibernating:
            # An idle stop already under way comes straight back warm once the process exits.
            self._idle_stop = False
        elif self.process.state() == QProcess.ProcessState.Running:
            if self._idle_ms and not self._active and not self._queue:
                self.idle_timer.start()
        else:
            self.prestart()

    def ready(self):
        """True when a running process has nothing to do, so a request starts at once."""
        return (not self._closed and not self._hibernating and not self._active and not self._queue
                and self.process.state() == QProcess.ProcessState.Running)

    def _enqueue_warmup(self):
        self._counter += 1
        self._internal.add(self._counter)
        operation, payload = self._warmup
        self._queue.appendleft({"id": self._counter, "operation": operation, "payload": dict(payload or {})})

    def cancelQueued(self, identifier):
        self._queue = deque(request for request in self._queue if request["id"] != identifier)

    def cancel(self, identifier):
        self.cancelQueued(identifier)
        if self._active and self._active["id"] == identifier:
            self.timer.stop()
            self._active = None
            self._hibernating = True
            if self.process.state() != QProcess.ProcessState.NotRunning:
                self._signal_process(force=True)
            else:
                QTimer.singleShot(0, self._restart_if_stopped)

    def _pump(self):
        if self._closed or self._hibernating or self._active or not self._queue:
            return
        self.idle_timer.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._buffer = b""
            if self._warmup and self._queue[0]["id"] not in self._internal:
                self._enqueue_warmup()
            self.process.start()
        elif self.process.state() == QProcess.ProcessState.Running:
            self._active = self._queue.popleft()
            self.process.write((json.dumps(self._active) + "\n").encode("utf-8"))
            self.timer.start(self._timeout_ms)

    def _read(self):
        incoming = bytes(self.process.readAllStandardOutput())
        if self._closed or self._hibernating:
            return
        self._buffer += incoming
        if len(self._buffer) > 32 * 1024 * 1024:
            self._protocol_error()
            return
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                response = json.loads(line)
                if not self._active or response.get("id") != self._active["id"]:
                    raise ValueError()
                if isinstance(response.get("progress"), dict):
                    self.timer.start(self._timeout_ms)
                    self.progress.emit(self._active["id"], response["progress"])
                    continue
                success = response.get("ok") and isinstance(response.get("result"), dict)
                failure = not response.get("ok") and isinstance(response.get("error"), dict)
                if not success and not failure:
                    raise ValueError()
                identifier = self._active["id"]
                self._active = None
                self.timer.stop()
                if identifier in self._internal:
                    self._internal.discard(identifier)
                elif success:
                    self.succeeded.emit(identifier, response["result"])
                else:
                    self.failed.emit(identifier, response["error"])
                QTimer.singleShot(0, self._pump)
                if self._idle_ms:
                    self.idle_timer.start()
            except (ValueError, TypeError, AttributeError):
                self._protocol_error()
                return

    def _fail_all(self, code, message, everything=True):
        self.timer.stop()
        pending = ([self._active] if self._active else []) + (list(self._queue) if everything else [])
        self._active = None
        if everything:
            self._queue.clear()
        for request in pending:
            if request["id"] in self._internal:
                self._internal.discard(request["id"])
                continue
            self.failed.emit(request["id"], {"code": code, "message": message})

    def _protocol_error(self):
        self._abort("provider_error", "This request could not be completed. Retry the operation.")

    def _timeout(self):
        self._abort("timeout", "The request timed out. Check your connection or unlock your system keyring.")

    def _error(self, error):
        if self._closed:
            return
        if self._hibernating:
            # A process killed while starting never emits finished; without this the
            # worker would stay hibernating and hold every later request forever.
            if self.process.state() == QProcess.ProcessState.NotRunning:
                QTimer.singleShot(0, self._restart_if_stopped)
            return
        # A worker that cannot start would otherwise restart forever for queued requests.
        self._abort("provider_error", "This request stopped. Retry the operation.",
                    everything=error == QProcess.ProcessError.FailedToStart)

    def _finished(self, exit_code, exit_status):
        self.timer.stop()
        if self._hibernating:
            idle, self._idle_stop = self._idle_stop, False
            self._hibernating = False
            if self._warmup and not idle and not self._closed and not self._queue:
                # A cancelled or reset worker comes straight back warm; an idle one stays down.
                self._enqueue_warmup()
            QTimer.singleShot(0, self._pump)
            return
        if not self._closed:
            self._abort("provider_error", "This request stopped. Retry the operation.")

    def _signal_process(self, force=False):
        pid = self.process.processId()
        if os.name == "posix" and pid:
            try:
                os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
                return
            except ProcessLookupError:
                return
        elif os.name == "nt" and pid:
            # The queue can own FFmpeg and extractor children; killing only Python leaves them writing.
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        # Windows delivers terminate() as WM_CLOSE, which a windowless worker ignores.
        self.process.kill() if force or os.name != "posix" else self.process.terminate()

    def _abort(self, code, message, everything=False):
        # Only the active request failed; queued requests (such as sidebar playlists
        # behind a slow Home load) run on the restarted worker.
        self._hibernating = True
        running = self.process.state() != QProcess.ProcessState.NotRunning
        self._fail_all(code, message, everything)
        if running:
            self._signal_process(force=True)
        else:
            QTimer.singleShot(0, self._restart_if_stopped)

    def _restart_if_stopped(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._hibernating = False
            self._pump()

    def _hibernate(self):
        if not self._active and not self._queue and self.process.state() == QProcess.ProcessState.Running:
            self._hibernating, self._idle_stop = True, True
            self._signal_process()
            QTimer.singleShot(1000, self._kill_idle)

    def _kill_idle(self):
        if self._hibernating and self.process.state() != QProcess.ProcessState.NotRunning:
            self._signal_process(force=True)

    def reset(self):
        self._abort("cancelled", "The account connection changed. Retry this request.", everything=True)

    def close(self):
        self._closed = True
        self.timer.stop()
        self.idle_timer.stop()
        self._queue.clear()
        self._internal.clear()
        self._active = None
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._signal_process()
            if not self.process.waitForFinished(500):
                self._signal_process(force=True)
                self.process.waitForFinished(500)
