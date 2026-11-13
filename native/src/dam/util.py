"""Credential-safe provider error classification."""

import sys


def needs_reconnect(error):
    return error.get("code") in {"reconnect", "AuthError", "SessionExpired"}


def session_rejected(error):
    exceptions = sys.modules.get("ytmusicapi.exceptions")
    return (exceptions is not None and isinstance(error, exceptions.YTMusicServerError)
            and str(error).startswith(("Server returned HTTP 401", "Server returned HTTP 403")))
