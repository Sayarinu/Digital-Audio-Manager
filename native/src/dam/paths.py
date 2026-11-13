"""Standard platform locations, retaining existing catalogs without moving them."""

import os
from pathlib import Path

APP_NAME = "Digital Audio Manager"


def standard_location(kind):
    from PySide6.QtCore import QStandardPaths

    location = getattr(QStandardPaths.StandardLocation, kind)
    value = QStandardPaths.writableLocation(location)
    if not value:
        raise OSError("The system did not provide a writable folder.")
    return Path(value)


def data_directory():
    if os.environ.get("MP3_MAKER_APP_DATA"):
        return Path(os.environ["MP3_MAKER_APP_DATA"]).expanduser()
    # Older versions used these macOS-shaped paths on every OS.
    for name in ("MP3 Maker", APP_NAME):
        legacy = Path.home() / "Library" / "Application Support" / name
        if (legacy / "mp3-maker.sqlite3").is_file():
            return legacy
    base = standard_location("GenericDataLocation")
    previous_base = Path(os.environ.get("APPDATA", str(base))) if os.name == "nt" else base
    for name in ("MP3 Maker", APP_NAME):
        previous = previous_base / name
        if (previous / "mp3-maker.sqlite3").is_file():
            return previous
    return base / APP_NAME


def default_library():
    for name in ("MP3 Maker", APP_NAME):
        legacy = Path.home() / "Music" / name / "Library"
        if legacy.exists():
            return legacy
    return standard_location("MusicLocation") / APP_NAME / "Library"
