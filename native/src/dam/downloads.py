"""Authenticated exact-video extraction with an in-memory cookie jar."""

from .engine import WorkerError


class QuietLogger:
    def debug(self, message):
        pass

    info = warning = error = debug


def authenticated_source(url, template, session, dependencies):
    from yt_dlp import YoutubeDL

    node = dependencies.get("node", {}).get("path")
    options = {
        "noplaylist": True, "continuedl": True, "retries": 3, "fragment_retries": 3,
        "socket_timeout": 30, "quiet": True, "no_warnings": True, "logger": QuietLogger(),
        "format": "bestaudio[ext=m4a]/bestaudio", "outtmpl": template,
        "writethumbnail": True, "cachedir": False,
        "js_runtimes": {"node": {"path": node}} if node else {},
    }
    ffmpeg = dependencies.get("ffmpeg", {}).get("path")
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg
    try:
        with YoutubeDL(options) as downloader:
            downloader.cookiejar = session.cookie_jar()
            return downloader.extract_info(url, download=True)
    except Exception as error:
        # Extractor failures may include signed URLs or cookies. Never persist the raw message.
        message = str(error).lower()
        if "429" in message or "too many requests" in message:
            raise WorkerError("Rate limited (429). Wait before retrying the queue.") from None
        if "proof of origin" in message or "po token" in message or "sign in to confirm" in message:
            raise WorkerError("YouTube requested proof of origin. Reconnect and retry later.") from None
        raise WorkerError("This exact video could not be downloaded. Reconnect your account, check the network and retry.") from None
