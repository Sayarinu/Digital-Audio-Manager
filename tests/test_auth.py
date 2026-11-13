import json

import pytest

from dam.account.auth import AuthError, AuthService
from dam.account.credentials import Credentials
from dam.provider import error_result as safe_error


class MemoryVault:
    def __init__(self):
        self.values = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        self.values[service, username] = value

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


class Catalog:
    base_headers = {"X-Goog-Visitor-Id": "fixture-visitor"}

    def get_account_info(self):
        return {"accountName": "Listener", "channelHandle": "@listener", "accountPhotoUrl": "https://example.test/photo"}


def test_validated_import_restores_without_network_and_sign_out_clears_only_session(tmp_path):
    path = tmp_path / "browser.json"
    path.write_text(json.dumps({"cookie": "__Secure-3PAPISID=private-cookie"}))
    credentials = Credentials(MemoryVault(), inline=False)
    service = AuthService(credentials, lambda session: Catalog())
    result = service.import_session(path)
    assert result["connected"]
    assert "private-cookie" not in json.dumps(result)

    def no_network(*args):
        pytest.fail("Restoring a saved account must not require network access")

    restored = AuthService(credentials, no_network)
    assert restored.restore()["profile"]["name"] == "Listener"
    assert restored.sign_out() == {"connected": False, "profile": {}}
    assert credentials.load() is None


def test_expired_replacement_cannot_overwrite_existing_session(tmp_path):
    path = tmp_path / "browser.json"
    path.write_text(json.dumps({"cookie": "__Secure-3PAPISID=private-cookie"}))
    credentials = Credentials(MemoryVault(), inline=False)
    service = AuthService(credentials, lambda session: Catalog())
    service.import_session(path)
    previous = credentials.load().session.headers["cookie"]

    def expired(session):
        raise RuntimeError("provider exception with private-cookie")

    service.catalog_factory = expired
    with pytest.raises(RuntimeError) as error:
        service.import_session(path)
    assert "private-cookie" not in json.dumps(safe_error(error.value))
    assert credentials.load().session.headers["cookie"] == previous



def test_browser_sign_in_is_validated_before_replacing_the_saved_session(monkeypatch):
    from functools import partial

    from dam.account import auth

    from dam.account import browsers

    credentials = Credentials(MemoryVault(), inline=False)
    service = AuthService(credentials, lambda session: Catalog())
    value = ["private-first"]

    def reader(name):
        if name == "chrome":
            return []
        return [{"name": cookie, "value": value[0], "domain": ".youtube.com", "path": "/"} for cookie in ("__Secure-3PAPISID", "SAPISID")]

    monkeypatch.setattr(auth, "read_session", partial(browsers.read_session, reader=reader))
    result = service.import_browser(["chrome", "firefox"])
    assert result["connected"] and result["browser"] == "firefox" and result["captured"] > 0
    assert "private-first" not in json.dumps(result)

    def rejected(session):
        raise RuntimeError("HTTP 401 private-second")

    service.catalog_factory = rejected
    value[0] = "private-second"
    with pytest.raises(RuntimeError):
        service.import_browser(["firefox"])
    assert "private-first" in credentials.load().session.headers["cookie"]


def test_verify_tells_a_signed_out_reply_from_a_network_failure(tmp_path):
    path = tmp_path / "browser.json"
    path.write_text(json.dumps({"cookie": "__Secure-3PAPISID=private-cookie"}))
    service = AuthService(Credentials(MemoryVault(), inline=False), lambda session: Catalog())
    service.import_session(path)
    assert service.verify() == {"captured": service.session.captured}

    class SignedOut(Catalog):
        def get_account_info(self):
            raise KeyError("Unable to find 'accountName'")

    service.client = SignedOut()
    with pytest.raises(AuthError):
        service.verify()

    class Offline(Catalog):
        def get_account_info(self):
            raise ConnectionError()

    service.client = Offline()
    with pytest.raises(ConnectionError):
        service.verify()


def test_safe_error_asks_to_reconnect_only_for_rejected_sessions():
    from ytmusicapi.exceptions import YTMusicServerError

    assert safe_error(YTMusicServerError("Server returned HTTP 403: Forbidden.\nprivate"))["code"] == "reconnect"
    assert safe_error(YTMusicServerError("Server returned HTTP 500: Error.\nprivate"))["code"] == "provider_error"
    # Wording alone from another error type must not sign the account out.
    assert safe_error(RuntimeError("Server returned HTTP 401"))["code"] == "provider_error"
