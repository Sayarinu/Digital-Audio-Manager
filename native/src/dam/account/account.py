"""Non-blocking account state exposed to QML; credentials remain in the worker."""

import json
import time

from PySide6.QtCore import QCoreApplication, QObject, Property, QSettings, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from . import browsers
from ..jobs import Worker
from ..util import needs_reconnect

MUSIC_URL = "https://music.youtube.com/"
RENEW_AFTER = 7 * 24 * 3600
RENEW_COOLDOWN = 10 * 60
POLL_MS = 4000
WAIT_LIMIT = 5 * 60


class Account(QObject):
    changed = Signal()
    connectedChanged = Signal()
    sessionChanged = Signal()
    signedOut = Signal()

    def __init__(self, settings_path, fixture=False, worker=None, parent=None, clock=time.time,
                 open_url=QDesktopServices.openUrl, default_browser=browsers.default_browser):
        super().__init__(parent)
        self._clock, self._open_url = clock, open_url
        # "", "interactive" (first try), "waiting" (browser opened, watching for sign-in) or "silent" (renewal).
        self._mode = ""
        self._renew_message = ""
        self._last_renewal = None
        self._wait_started = 0.
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._check_browser)
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self._fixture = fixture
        self.worker = None if fixture else (worker if worker is not None else Worker(self))
        self._request = None
        self._verify_request = None
        self._operation = ""
        self._busy = False
        self._connected = False
        self._reconnect = False
        self._message = ""
        self._default_browser = None if fixture else default_browser()
        try:
            self._profile = json.loads(self.settings.value("accountProfile", "{}"))
            if not isinstance(self._profile, dict):
                self._profile = {}
        except (ValueError, TypeError):
            self._profile = {}
        if fixture:
            self._profile = {"name": "Your music", "handle": "", "avatar": ""}
        else:
            self.worker.succeeded.connect(self._succeeded)
            self.worker.failed.connect(self._failed)
            QTimer.singleShot(0, self.restore)
            application = QCoreApplication.instance()
            if hasattr(application, "applicationStateChanged"):
                # Returning from the browser is the natural moment to look for the new sign-in.
                application.applicationStateChanged.connect(self._activated)

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=connectedChanged)
    def connected(self):
        return self._connected and not self._reconnect

    @Property(bool, notify=changed)
    def reconnect(self):
        return self._reconnect

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property("QVariantMap", notify=changed)
    def profile(self):
        return self._profile

    @Property(bool, constant=True)
    def fixtureMode(self):
        return self._fixture

    @Property(bool, constant=True)
    def signInAvailable(self):
        return not self._fixture

    @Property(bool, notify=changed)
    def signingIn(self):
        return self._mode in {"interactive", "waiting"}

    def _send(self, operation, payload=None, keep_message=False):
        if self.worker is None or self._busy:
            return False
        self._operation = operation
        self._busy = True
        if not keep_message:
            self._message = ""
        self._request = self.worker.request(operation, payload)
        self.changed.emit()
        return True

    @Slot()
    def restore(self):
        # Asks once: reading a keyring entry another build made can prompt for approval on macOS.
        self._send("restore")

    @Slot(QUrl)
    def importFile(self, url):
        if url.isLocalFile():
            self._send("import_session", {"path": url.toLocalFile()})

    @Slot()
    def signIn(self):
        """Connect with the browser's own YouTube Music sign-in, opening the browser if it has none yet."""
        if self._fixture or self.signingIn:
            return
        names = browsers.candidates(self.settings.value("signInBrowser", ""), self._default_browser)
        if self._send("import_browser", {"browsers": names}):
            self._mode = "interactive"
            self.changed.emit()

    @Slot()
    def cancelSignIn(self):
        if self._mode == "waiting":
            self._stop_waiting("")

    def _wait_for_browser(self):
        self._mode = "waiting"
        self._wait_started = self._clock()
        self._message = "Sign in to YouTube Music in your browser. Digital Audio Manager connects as soon as you’re signed in."
        self._open_url(QUrl(MUSIC_URL))
        self._poll.start()
        self.changed.emit()

    def _stop_waiting(self, message):
        self._poll.stop()
        self._mode = ""
        self._message = message
        self.changed.emit()

    def _activated(self, state):
        from PySide6.QtCore import Qt

        if state == Qt.ApplicationState.ApplicationActive and self._mode == "waiting":
            self._check_browser()

    def _check_browser(self):
        if self._mode != "waiting" or self._busy:
            return
        if self._clock() - self._wait_started > WAIT_LIMIT:
            self._stop_waiting("No YouTube Music sign-in was found in your browser. Sign in there, then try again.")
            return
        # Only the opened browser is watched, so other browsers' keychain prompts never repeat.
        names = browsers.candidates(None, self._default_browser)[:1]
        self._send("import_browser", {"browsers": names}, keep_message=True)

    def renew(self, message=""):
        """Re-read the remembered browser's current cookies; False if no renewal was attempted."""
        now = self._clock()
        browser = self.settings.value("signInBrowser", "")
        if (self._fixture or self._mode or not browser or self._busy
                or self._last_renewal is not None and now - self._last_renewal < RENEW_COOLDOWN):
            return False
        self._last_renewal = now
        self._renew_message = message
        self._mode = "silent"
        self._send("import_browser", {"browsers": [browser]}, keep_message=True)
        return True

    def _renewal_failed(self):
        message, self._renew_message = self._renew_message, ""
        if message:
            # Only a renewal triggered by an expired session raises the banner.
            self._set_reconnect(message)
        else:
            self.changed.emit()

    @Slot()
    def signOut(self):
        self._poll.stop()
        self._mode = ""
        # Forget the browser too, so renewal cannot reconnect a signed-out account.
        self.settings.remove("signInBrowser")
        self._send("sign_out")

    @Slot(str)
    def requireReconnect(self, message):
        if self._mode == "silent":
            return
        if not self.renew(message):
            self._set_reconnect(message)

    def _set_reconnect(self, message):
        self._reconnect = True
        self._message = message
        self.changed.emit()
        self.connectedChanged.emit()

    def _succeeded(self, identifier, result):
        if identifier == self._verify_request:
            self._verify_request = None
            captured = result.get("captured") or 0
            if captured and self._clock() - captured > RENEW_AFTER:
                # Refresh rotating Google cookies before they lapse; failure leaves the current session alone.
                self.renew()
            return
        if identifier != self._request:
            return
        self._request = None
        self._busy = False
        self._connected = bool(result.get("connected"))
        self._reconnect = False
        self._profile = result.get("profile") or {}
        self._message = "Connected to YouTube Music." if self._connected else ""
        self.settings.setValue("accountProfile", json.dumps(self._profile))
        if self._operation == "import_browser":
            self._poll.stop()
            self._mode, self._renew_message = "", ""
            self.settings.setValue("signInBrowser", result.get("browser", ""))
        elif self._operation == "import_session":
            self.settings.remove("signInBrowser")
        self.settings.sync()
        self.changed.emit()
        self.connectedChanged.emit()
        if self._operation in {"import_session", "import_browser", "sign_out"}:
            self.sessionChanged.emit()
        if self._operation == "sign_out":
            self.signedOut.emit()
        if self._operation == "restore" and self._connected:
            # The browser may have rotated the saved cookies while the app was closed. This doesn't hold
            # up the account state, and being offline says nothing about the session.
            self._verify_request = self.worker.request("verify_session")

    def _failed(self, identifier, error):
        if identifier == self._verify_request:
            self._verify_request = None
            # A sign-in or sign-out in progress settles the session itself.
            if needs_reconnect(error) and not self._busy:
                self.requireReconnect(error.get("message", "Your session needs reconnecting."))
            return
        if identifier != self._request:
            return
        self._request = None
        self._busy = False
        message = error.get("message", "Reconnect YouTube Music.")
        if self._operation == "import_browser":
            self._browser_failed(error.get("code"), message)
            return
        self._message = message
        if self._operation == "restore" and not self.renew(message):
            # An unreadable saved session is replaced from the browser before asking the user.
            self._reconnect = True
        self.changed.emit()
        self.connectedChanged.emit()

    def _browser_failed(self, code, message):
        mode = self._mode
        if mode == "silent":
            self._mode = ""
            self._renewal_failed()
        elif mode == "interactive" and code == "NoBrowserSession":
            self._wait_for_browser()
        elif mode == "waiting":
            # Keep watching; only problems other than "not signed in yet" are worth showing.
            if code != "NoBrowserSession":
                self._message = message
            self.changed.emit()
        else:
            self._mode = ""
            self._message = message
            self.changed.emit()

    def close(self):
        self._poll.stop()
        if self.worker:
            self.worker.close()
