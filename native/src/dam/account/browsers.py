"""Reuse the YouTube Music sign-in from the user's own browser, where Google's sign-in really happens.

Detection runs in the UI process; cookie reading runs only in the provider worker.
"""

from functools import cache
import subprocess
import sys

from .session import SessionError, from_cookies

# yt-dlp browser names, in the order to try after the default browser.
ORDER = ("firefox", "chrome", "safari", "edge", "brave", "chromium", "vivaldi", "opera")
NAMES = {"firefox": "Firefox", "chrome": "Chrome", "safari": "Safari", "edge": "Edge", "brave": "Brave",
         "chromium": "Chromium", "vivaldi": "Vivaldi", "opera": "Opera"}
MAC_BUNDLES = {
    "org.mozilla.firefox": "firefox", "org.mozilla.firefoxdeveloperedition": "firefox", "org.mozilla.nightly": "firefox",
    "com.google.chrome": "chrome", "com.google.chrome.beta": "chrome", "com.apple.safari": "safari",
    "com.microsoft.edgemac": "edge", "com.brave.browser": "brave", "org.chromium.chromium": "chromium",
    "com.vivaldi.vivaldi": "vivaldi", "com.operasoftware.opera": "opera",
}
LINUX_DESKTOP = {"firefox": "firefox", "google-chrome": "chrome", "brave": "brave", "chromium": "chromium",
                 "microsoft-edge": "edge", "vivaldi": "vivaldi", "opera": "opera"}
WINDOWS_PROGIDS = {"firefox": "firefox", "chromehtml": "chrome", "msedgehtm": "edge", "bravehtml": "brave",
                   "chromiumhtm": "chromium", "vivaldihtm": "vivaldi", "operastable": "opera"}


class NoBrowserSession(SessionError):
    """No supported browser holds a signed-in YouTube Music session yet."""


class BrowserBlocked(SessionError):
    """The browser's cookies exist but macOS privacy settings keep Digital Audio Manager from reading them."""


def _mac_default():
    from AppKit import NSWorkspace
    from Foundation import NSBundle, NSURL

    url = NSWorkspace.sharedWorkspace().URLForApplicationToOpenURL_(NSURL.URLWithString_("https://music.youtube.com"))
    bundle = NSBundle.bundleWithURL_(url) if url else None
    return MAC_BUNDLES.get(str(bundle.bundleIdentifier() or "").lower()) if bundle else None


def _linux_default():
    desktop = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True, timeout=5).stdout.strip().lower()
    return next((name for prefix, name in LINUX_DESKTOP.items() if desktop.startswith(prefix)), None)


def _windows_default():
    import winreg

    key = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
        progid = str(winreg.QueryValueEx(handle, "ProgId")[0]).lower()
    return next((name for prefix, name in WINDOWS_PROGIDS.items() if progid.startswith(prefix)), None)


def default_browser(platform=None):
    platform = platform or sys.platform
    detect = {"darwin": _mac_default, "win32": _windows_default}.get(platform, _linux_default)
    try:
        return detect()
    except Exception:
        # Detection is a convenience; every supported browser is still tried.
        return None


def candidates(preferred=None, default=None):
    ordered = [name for name in (preferred, default) if name in NAMES]
    return list(dict.fromkeys(ordered + list(ORDER)))


def _quiet_logger():
    from yt_dlp.cookies import YDLLogger

    class Quiet(YDLLogger):
        # The worker's stdout is its protocol channel, and cookie logs could carry account details.
        def debug(self, message, *args, **kwargs):
            pass

        info = warning = error = debug

        def progress_bar(self):
            return None

    return Quiet()


def _remember_keychain_answers():
    # Ask macOS for each Chromium browser's cookie key once per worker, not on every sign-in check.
    import yt_dlp.cookies

    if not hasattr(yt_dlp.cookies._get_mac_keyring_password, "cache_info"):
        yt_dlp.cookies._get_mac_keyring_password = cache(yt_dlp.cookies._get_mac_keyring_password)


def _rows(name):
    from yt_dlp.cookies import extract_cookies_from_browser

    jar = extract_cookies_from_browser(name, logger=_quiet_logger())
    return [{
        "name": cookie.name, "value": cookie.value or "", "domain": cookie.domain, "path": cookie.path or "/",
        "secure": bool(cookie.secure), "expires": cookie.expires,
    } for cookie in jar if cookie.domain.lstrip(".") in {"youtube.com", "music.youtube.com"}]


WINDOWS_HINT = (" Chrome and Edge on Windows lock and encrypt their cookies while open;"
                " close the browser and try again, or sign in to YouTube Music in Firefox.")


def read_session(names, reader=_rows, platform=None):
    """Return (browser, session) for the first browser signed in to YouTube Music."""
    if reader is _rows and sys.platform == "darwin":
        _remember_keychain_answers()
    blocked = None
    for name in names:
        if name not in NAMES:
            continue
        try:
            rows = reader(name)
        except PermissionError:
            blocked = name
            continue
        except Exception:
            # Not installed, never used or unreadable: try the next browser.
            continue
        if {"SAPISID", "__Secure-3PAPISID"} <= {row["name"] for row in rows}:
            return name, from_cookies(rows)
    if blocked == "safari":
        raise BrowserBlocked("Allow Digital Audio Manager Full Disk Access in System Settings › Privacy & Security to use your Safari sign-in, or sign in with another browser.")
    hint = WINDOWS_HINT if (platform or sys.platform) == "win32" else ""
    raise NoBrowserSession("Sign in to YouTube Music in your browser to connect." + hint)
