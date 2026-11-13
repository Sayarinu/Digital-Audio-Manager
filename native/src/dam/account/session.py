"""Read explicitly selected session exports without changing browser profiles."""

from copy import copy
from dataclasses import dataclass, field
from http.cookiejar import Cookie, CookieJar
from http.cookies import SimpleCookie
import json
from pathlib import Path
import time


class SessionError(ValueError):
    """An actionable import error that never includes credential contents."""


def make_cookie(name, value, domain=".youtube.com", path="/", secure=True, expires=None):
    return Cookie(
        0, name, value, None, False, domain, True, domain.startswith("."),
        path, True, secure, expires, expires is None, None, None, {}, False,
    )


@dataclass(repr=False)
class Session:
    headers: dict = field(repr=False)
    cookies: list[Cookie] = field(repr=False)
    captured: float = 0.

    def __repr__(self):
        return "Session(<redacted>)"

    def cookie_jar(self):
        jar = CookieJar()
        for cookie in self.cookies:
            jar.set_cookie(copy(cookie))
        return jar

    def to_payload(self):
        return {
            "headers": {k: v for k, v in self.headers.items() if k.lower() != "cookie"},
            "cookies": [{
                "name": c.name, "value": c.value, "domain": c.domain,
                "path": c.path, "secure": c.secure, "expires": c.expires,
            } for c in self.cookies],
            "captured": self.captured,
        }

    @classmethod
    def from_payload(cls, payload):
        try:
            rows = payload["cookies"]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
                raise ValueError()
            cookies = []
            for row in rows:
                if not all(isinstance(row.get(key), str) for key in ("name", "value", "domain", "path")):
                    raise ValueError()
                if row["domain"].lstrip(".") not in {"youtube.com", "music.youtube.com"}:
                    raise ValueError()
                if row.get("expires") is not None and not isinstance(row["expires"], int):
                    raise ValueError()
                cookies.append(make_cookie(row["name"], row["value"], row["domain"], row["path"], bool(row.get("secure", True)), row.get("expires")))
            headers = dict(payload["headers"])
            headers["cookie"] = "; ".join(f"{c.name}={c.value}" for c in cookies)
            session = from_headers(headers)
            session.cookies = cookies
            captured = payload.get("captured", 0.)
            session.captured = float(captured) if isinstance(captured, (int, float)) else 0.
            return session
        except (KeyError, TypeError, ValueError):
            raise SessionError("The saved session is invalid. Reconnect YouTube Music.") from None


def from_headers(value):
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise SessionError("Select a browser.json request-header export.")
    values = {key.lower(): item for key, item in value.items()}
    allowed = {"cookie", "user-agent", "accept-language", "x-goog-authuser", "x-goog-visitor-id"}
    for key in allowed & values.keys():
        item = values[key]
        if not isinstance(item, str) or "\r" in item or "\n" in item:
            raise SessionError("The session contains invalid request headers.")
    cookie = SimpleCookie()
    try:
        cookie.load(values.get("cookie", ""))
    except Exception:
        raise SessionError("The session cookie header is invalid.") from None
    if "__Secure-3PAPISID" not in cookie:
        raise SessionError("The session has no signed-in YouTube Music cookie. Reconnect first.")
    from ytmusicapi.helpers import initialize_headers

    headers = initialize_headers()
    headers.update({key: values[key] for key in allowed if key in values})
    headers.update({
        "authorization": "SAPISIDHASH",
        "x-origin": "https://music.youtube.com",
        "origin": "https://music.youtube.com",
        "x-goog-authuser": values.get("x-goog-authuser", "0"),
    })
    return Session(headers, [make_cookie(m.key, m.value) for m in cookie.values()])


def read_browser_session(path):
    try:
        path = Path(path)
        if path.stat().st_size > 1024 * 1024:
            raise SessionError("The selected session export is too large.")
        return from_headers(json.loads(path.read_text(encoding="utf-8")))
    except SessionError:
        raise
    except (OSError, ValueError, TypeError):
        raise SessionError("Could not read the selected browser.json export.") from None


def from_cookies(rows, user_agent=None):
    """Build a session from captured browser cookies, keeping only live YouTube cookies."""
    if not isinstance(rows, list) or len(rows) > 1000:
        raise SessionError("The sign-in did not return a usable session. Try again.")
    cookies = []
    try:
        for row in rows:
            domain = row["domain"]
            if not isinstance(domain, str) or domain.lstrip(".") not in {"youtube.com", "music.youtube.com"}:
                continue
            expires = row.get("expires")
            expires = int(expires) if isinstance(expires, (int, float)) else None
            if expires is not None and expires <= time.time():
                continue
            if not all(isinstance(row.get(key), str) for key in ("name", "value")):
                raise TypeError()
            cookies.append(make_cookie(row["name"], row["value"], domain, row.get("path") or "/", bool(row.get("secure", True)), expires))
    except (KeyError, TypeError, AttributeError):
        raise SessionError("The sign-in did not return a usable session. Try again.") from None
    if len(cookies) > 200:
        # Saved sessions are restored with the same bound.
        raise SessionError("The sign-in returned too many cookies. Try again.")
    headers = {"cookie": "; ".join(f"{c.name}={c.value}" for c in cookies)}
    if isinstance(user_agent, str) and user_agent:
        headers["user-agent"] = user_agent
    session = from_headers(headers)
    session.cookies = cookies
    session.captured = time.time()
    return session
