"""Reference existing audio in place and cache its embedded artwork."""

import base64
import hashlib
import os
from pathlib import Path

import mutagen
from mutagen.flac import Picture

from . import engine

EXTENSIONS = {".mp3", ".m4a", ".mp4", ".flac", ".ogg", ".opus", ".wav", ".aac", ".wma", ".aiff", ".aif"}
COLLECTION = "local:music"


def embedded_artwork(audio):
    pictures = getattr(audio, "pictures", [])
    if pictures:
        return pictures[0].data
    tags = audio.tags or {}
    if hasattr(tags, "getall"):
        pictures = tags.getall("APIC")
        if pictures:
            return pictures[0].data
    if tags.get("covr"):
        return bytes(tags["covr"][0])
    if tags.get("metadata_block_picture"):
        try:
            return Picture(base64.b64decode(tags["metadata_block_picture"][0], validate=True)).data
        except (ValueError, mutagen.MutagenError):
            pass
    return None


def metadata(path):
    audio = mutagen.File(path)
    if audio is None:
        raise ValueError("Unsupported audio file")
    tags = audio.tags or {}
    easy = mutagen.File(path, easy=True)
    values = (easy.tags if easy else None) or tags

    def first(*keys, fallback=""):
        for key in keys:
            value = values.get(key) or tags.get(key)
            if value:
                if isinstance(value, (list, tuple)):
                    value = value[0]
                return str(value)[:2000]
        return fallback

    artwork = embedded_artwork(audio)
    cover = ""
    if artwork and len(artwork) <= 16 * 1024 * 1024:
        extension = ".png" if artwork.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg" if artwork.startswith(b"\xff\xd8\xff") else ""
        if extension:
            target = engine.app_data() / "artwork" / (hashlib.sha256(artwork).hexdigest() + extension)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(artwork)
            cover = target.as_uri()
    if not cover:
        for candidate in (path.with_suffix('.jpg'), path.with_suffix('.png'), path.parent / 'cover.jpg', path.parent / 'folder.jpg', path.parent / 'cover.png'):
            if candidate.is_file() and candidate.stat().st_size <= 16 * 1024 * 1024:
                cover = candidate.as_uri()
                break
    return {"title": first("title", "TIT2", "\xa9nam", fallback=path.stem),
            "artist": first("artist", "TPE1", "\xa9ART", fallback="Unknown artist"),
            "album": first("album", "TALB", "\xa9alb", fallback="Local music"),
            "duration": engine.human_duration(getattr(audio.info, "length", 0)), "artwork_url": cover}


def selected_files(payload):
    values = payload.get("paths", [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise engine.WorkerError("Choose audio files or a music folder.")
    paths = set()
    for value in values:
        path = Path(value).expanduser()
        if not path.is_absolute() or not path.exists():
            raise engine.WorkerError("That music location is unavailable. Reconnect its drive and try again.")
        if path.is_dir():
            for directory, _, files in os.walk(path, followlinks=False):
                for name in files:
                    candidate = Path(directory) / name
                    if candidate.suffix.lower() in EXTENSIONS:
                        paths.add(candidate.resolve())
                if len(paths) > 50000:
                    raise engine.WorkerError("Choose a smaller folder with fewer than 50,000 audio files.")
        elif path.suffix.lower() in EXTENSIONS:
            paths.add(path.resolve())
    if not paths:
        raise engine.WorkerError("No supported audio files were found in that selection.")
    return sorted(paths)


def import_files(payload):
    paths = selected_files(payload)
    imported, skipped = [], 0
    try:
        for index, path in enumerate(paths):
            engine.write_activity("Reading local music", index, len(paths))
            try:
                imported.append((path, metadata(path)))
            except (OSError, ValueError, mutagen.MutagenError):
                skipped += 1
        if not imported:
            raise engine.WorkerError("Could not read those audio files. Choose supported, playable music files.")
        con = engine.connect()
        try:
            with con:
                now = engine.utcnow()
                con.execute("""INSERT INTO playlist(id,title,source,updated_at) VALUES (?, 'Local music', 'Local files', ?)
                               ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at""", (COLLECTION, now))
                existing = {row[0] for row in con.execute("SELECT video_id FROM playlist_item WHERE playlist_id=?", (COLLECTION,))}
                position = con.execute("SELECT COALESCE(MAX(position),0) FROM playlist_item WHERE playlist_id=?", (COLLECTION,)).fetchone()[0]
                for path, info in imported:
                    identity = "local:" + hashlib.sha256(os.path.normcase(str(path)).encode()).hexdigest()
                    con.execute("""INSERT INTO track(video_id,title,artist,album,duration,artwork_url,local_status,media_path,updated_at)
                                   VALUES (?,?,?,?,?,?,'ready',?,?) ON CONFLICT(video_id) DO UPDATE SET
                                   title=excluded.title,artist=excluded.artist,album=excluded.album,duration=excluded.duration,
                                   artwork_url=excluded.artwork_url,local_status='ready',media_path=excluded.media_path,updated_at=excluded.updated_at""",
                                (identity, info['title'], info['artist'], info['album'], info['duration'], info['artwork_url'], str(path), now))
                    if identity not in existing:
                        position += 1
                        con.execute("INSERT INTO playlist_item(playlist_id,position,video_id) VALUES (?,?,?)", (COLLECTION, position, identity))
        finally:
            con.close()
    finally:
        engine.clear_activity()
    result = engine.dashboard()
    if skipped:
        result['notice'] = f"Could not read {skipped} audio files. The other files were added to Local music."
    return result
