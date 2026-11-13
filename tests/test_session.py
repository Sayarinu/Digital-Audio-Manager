import json
import time

import pytest

from dam.account.session import Session, SessionError, from_cookies, from_headers, read_browser_session


def test_import_keeps_credentials_out_of_representation_and_restricts_origin(tmp_path):
    path = tmp_path / "browser.json"
    path.write_text(json.dumps({
        "Cookie": "__Secure-3PAPISID=private-session; SID=another-secret",
        "Origin": "https://untrusted.example",
        "Host": "untrusted.example",
        "X-Goog-AuthUser": "1",
    }))
    session = read_browser_session(path)
    assert "private-session" not in repr(session)
    assert session.headers["origin"] == "https://music.youtube.com"
    assert session.headers["x-goog-authuser"] == "1"
    assert "host" not in session.headers
    jar = session.cookie_jar()
    assert {cookie.name for cookie in jar} == {"SID", "__Secure-3PAPISID"}
    next(iter(jar)).value = "changed"
    assert next(iter(session.cookie_jar())).value != "changed"


@pytest.mark.parametrize("value", [[], {"cookie": "SID=private"}, {"cookie": "__Secure-3PAPISID=private\r\nHost: evil"}])
def test_invalid_session_errors_do_not_expose_credentials(value):
    with pytest.raises(SessionError) as error:
        from_headers(value)
    assert "private" not in str(error.value)


def test_malformed_export_is_reported_without_its_contents(tmp_path):
    path = tmp_path / "browser.json"
    path.write_text("private malformed input")
    with pytest.raises(SessionError) as error:
        read_browser_session(path)
    assert "private" not in str(error.value)


def test_saved_payload_preserves_cookie_domain_and_expiry():
    from dam.account.session import Session

    original = from_headers({"cookie": "__Secure-3PAPISID=private-session"})
    original.cookies[0].expires = 2000000000
    restored = Session.from_payload(original.to_payload())
    assert restored.cookies[0].expires == 2000000000
    assert restored.cookies[0].domain == ".youtube.com"
    assert restored.headers["cookie"] == original.headers["cookie"]


def test_sign_in_cookies_keep_live_youtube_cookies_and_round_trip_with_capture_time():
    rows = [
        {"name": "__Secure-3PAPISID", "value": "private-sign-in", "domain": ".youtube.com", "path": "/", "secure": True, "expires": int(time.time()) + 3600},
        {"name": "SAPISID", "value": "private-sapisid", "domain": ".youtube.com", "path": "/", "secure": True, "expires": None},
        {"name": "SID", "value": "google-only", "domain": ".google.com", "path": "/", "secure": True, "expires": None},
        {"name": "OLD", "value": "expired", "domain": ".youtube.com", "path": "/", "secure": True, "expires": 1},
    ]
    session = from_cookies(rows, "Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36")
    assert "private-sign-in" not in repr(session)
    assert {cookie.name for cookie in session.cookies} == {"__Secure-3PAPISID", "SAPISID"}
    assert session.headers["user-agent"].startswith("Mozilla/5.0 Chrome")
    assert session.captured > time.time() - 60
    restored = Session.from_payload(json.loads(json.dumps(session.to_payload())))
    assert restored.captured == session.captured
    assert restored.headers["user-agent"] == session.headers["user-agent"]


@pytest.mark.parametrize("rows", [None, [{"name": "SID", "value": "private", "domain": ".youtube.com"}], [{"value": "private", "domain": ".youtube.com"}]])
def test_unusable_sign_in_cookies_are_rejected_without_their_contents(rows):
    with pytest.raises(SessionError) as error:
        from_cookies(rows)
    assert "private" not in str(error.value)


def test_sessions_saved_before_capture_times_still_restore():
    session = from_headers({"cookie": "__Secure-3PAPISID=private"})
    payload = session.to_payload()
    del payload["captured"]
    assert Session.from_payload(payload).captured == 0.
