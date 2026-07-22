#!/usr/bin/env python3
"""Local JSON worker for Digital Audio Manager.

This process deliberately has no HTTP listener. Tauri invokes one operation at a
time and passes a small JSON document on stdin; durable state lives in SQLite.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
try:
    from ytmusicapi import YTMusic
except Exception:
    YTMusic = None

APP_NAME = "Digital Audio Manager"
LEGACY_APP_NAME = "MP3 Maker"
MAX_EXPORT_FILES = 8000
MIN_FREE_BYTES = 20 * 1024 ** 3


class WorkerError(Exception):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def app_data():
    configured = os.environ.get("MP3_MAKER_APP_DATA")
    if configured:
        return Path(configured).expanduser()
    preferred = Path.home() / "Library" / "Application Support" / APP_NAME
    legacy = Path.home() / "Library" / "Application Support" / LEGACY_APP_NAME
    # Keep existing local catalogs available after the product rename.
    return legacy if (legacy / "mp3-maker.sqlite3").is_file() else preferred


def library_root():
    configured = os.environ.get("MP3_MAKER_LIBRARY")
    if configured:
        return Path(configured).expanduser()
    preferred = Path.home() / "Music" / APP_NAME / "Library"
    legacy = Path.home() / "Music" / LEGACY_APP_NAME / "Library"
    return legacy if legacy.exists() else preferred


def db_path():
    return app_data() / "mp3-maker.sqlite3"


def activity_path():
    return app_data() / "activity.json"


def write_activity(label, completed=0, total=0):
    app_data().mkdir(parents=True, exist_ok=True)
    activity_path().write_text(json.dumps({"label": label, "completed": completed, "total": total}))


def read_activity():
    try:
        return json.loads(activity_path().read_text())
    except (OSError, json.JSONDecodeError):
        return None


def clear_activity():
    activity_path().unlink(missing_ok=True)


def connect():
    app_data().mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path()))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS playlist (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
        remote_id TEXT, loaded INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS track (
        video_id TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
        album TEXT, duration TEXT, artwork_url TEXT, local_status TEXT NOT NULL DEFAULT 'missing',
        media_path TEXT, source_codec TEXT, checksum TEXT, updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS playlist_item (
        playlist_id TEXT NOT NULL REFERENCES playlist(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, video_id TEXT NOT NULL REFERENCES track(video_id) ON DELETE CASCADE,
        PRIMARY KEY (playlist_id, position)
      );
      CREATE TABLE IF NOT EXISTS download_job (
        id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES track(video_id), state TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, error_code TEXT, error_message TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    return con


def canonical_filename(value, limit=100):
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", " ", value or "Unknown")
    value = re.sub(r"\s+", " ", value).strip(" .")
    return (value or "Unknown")[:limit]


def checksum(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_tool(name, extra=None):
    candidates = list(extra or [])
    resolved = shutil.which(name)
    if resolved:
        candidates.append(Path(resolved))
    for candidate in candidates:
        candidate = Path(candidate)
        if candidate.exists() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


def dependency_health():
    managed = app_data() / "bin" / "yt-dlp"
    ffmpeg = find_tool("ffmpeg", [Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")])
    ffprobe = find_tool("ffprobe", [Path("/opt/homebrew/bin/ffprobe"), Path("/usr/local/bin/ffprobe")])
    node = find_tool("node")
    ytdlp = find_tool("yt-dlp", [managed])
    return {
        "yt_dlp": {"available": bool(ytdlp), "path": ytdlp, "detail": "Anonymous downloader; no browser cookies are used."},
        "ffmpeg": {"available": bool(ffmpeg and ffprobe), "path": ffmpeg, "detail": "Used for verified MP3 fallback and device copy tags."},
        "node": {"available": bool(node), "path": node, "detail": "Optional helper dependency for yt-dlp proof-of-origin support."},
    }


def health_check(_payload=None):
    root = library_root()
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(str(root))
    return {
        "app_data": str(app_data()), "library_root": str(root), "free_bytes": usage.free,
        "minimum_free_bytes": max(MIN_FREE_BYTES, int(usage.total * .10)), "dependencies": dependency_health(),
    }


def local_status(con, video_id):
    row = con.execute("SELECT local_status FROM track WHERE video_id = ?", (video_id,)).fetchone()
    return row["local_status"] if row else "missing"


def dashboard(_payload=None):
    con = connect()
    try:
        playlists = [dict(row) for row in con.execute("""
          SELECT p.id, p.title, p.source, p.loaded, p.updated_at, COUNT(i.video_id) AS track_count
          FROM playlist p LEFT JOIN playlist_item i ON p.id = i.playlist_id
          GROUP BY p.id ORDER BY p.updated_at DESC, p.title COLLATE NOCASE
        """)]
        tracks = [dict(row) for row in con.execute("""
          SELECT p.id || ':' || i.position AS id, p.id AS playlist_id, i.position, t.video_id,
                 t.title, t.artist, p.title AS album, t.duration, t.artwork_url,
                 CASE WHEN t.local_status='failed' AND t.video_id LIKE 'unavailable:%' THEN 'unavailable' ELSE t.local_status END AS local_status,
                 t.media_path
          FROM playlist_item i JOIN playlist p ON p.id=i.playlist_id JOIN track t ON t.video_id=i.video_id
          ORDER BY p.title COLLATE NOCASE, i.position
        """)]
        jobs = [dict(row) for row in con.execute("""
          SELECT j.id, j.video_id, t.title, t.artist, j.state, j.attempts, j.error_code,
                 j.error_message, j.updated_at
          FROM download_job j JOIN track t ON t.video_id = j.video_id
          ORDER BY CASE j.state WHEN 'running' THEN 0 WHEN 'queued' THEN 1 WHEN 'retry' THEN 2 WHEN 'failed' THEN 3 ELSE 4 END,
                   j.updated_at DESC LIMIT 100
        """)]
        profile = con.execute("SELECT value FROM setting WHERE key='public_profile_url'").fetchone()
        sync_notice = con.execute("SELECT value FROM setting WHERE key='last_sync_notice'").fetchone()
        return {"playlists": playlists, "tracks": tracks, "jobs": jobs, "health": health_check(),
                "public_profile_url": profile["value"] if profile else None,
                "sync_notice": sync_notice["value"] if sync_notice and sync_notice["value"] else None,
                "activity": read_activity()}
    finally:
        con.close()


def require_url_playlist(url):
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("https", "http") or "youtube" not in parsed.netloc:
        raise WorkerError("Use a YouTube or YouTube Music playlist URL.")
    playlist_id = parse_qs(parsed.query).get("list", [None])[0]
    if not playlist_id:
        raise WorkerError("That link does not contain a playlist ID (the `list` parameter).")
    return playlist_id


def require_public_profile_url(url):
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split(":")[0]
    if parsed.scheme not in ("https", "http") or host not in ("youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com"):
        raise WorkerError("Use a public youtube.com or music.youtube.com profile URL.")
    path = parsed.path.rstrip("/")
    if not path or path.startswith("/playlist") or path.startswith("/watch"):
        raise WorkerError("Use a public channel or @handle URL, not an individual video or playlist.")
    return parsed


def ytdlp_public_json(url, timeout=300):
    ytdlp = dependency_health()["yt_dlp"].get("path")
    if not ytdlp:
        raise WorkerError("yt-dlp is required for anonymous public-profile imports. Install it, then retry.")
    result = subprocess.run([ytdlp, "--no-warnings", "--flat-playlist", "--dump-single-json", url], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise WorkerError("Could not read that public profile: " + (result.stderr.strip() or result.stdout.strip() or "yt-dlp failed"))
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise WorkerError("That profile did not expose any public playlist data.")
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        raise WorkerError("The public profile returned an unexpected response.")


def ytdlp_public_entries(url, timeout=900):
    """Read every playlist entry as its own JSON line, including continuations."""
    ytdlp = dependency_health()["yt_dlp"].get("path")
    if not ytdlp:
        raise WorkerError("yt-dlp is required for anonymous public-playlist imports. Install it, then retry.")
    result = subprocess.run([ytdlp, "--no-warnings", "--flat-playlist", "--dump-json", url], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise WorkerError("Could not read that public playlist: " + (result.stderr.strip() or result.stdout.strip() or "yt-dlp failed"))
    entries = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        # --dump-json normally yields an entry per line. Retain this fallback
        # for extractor versions that return a complete playlist object instead.
        entries.extend(item.get("entries") or [item])
    if not entries:
        raise WorkerError("That public playlist did not expose any playable entries.")
    return entries


def human_duration(value):
    try:
        total = int(float(value))
    except (TypeError, ValueError):
        return None
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return "{}:{:02d}:{:02d}".format(hours, minutes, seconds) if hours else "{}:{:02d}".format(minutes, seconds)


def first_metadata_text(value):
    """Normalize the different artist shapes returned by YouTube extractors."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("name") or value.get("title") or value.get("artist") or "").strip()
    if isinstance(value, list):
        values = [first_metadata_text(item) for item in value]
        return " & ".join(item for item in values if item)
    return ""


def artist_from_metadata(item, fallback=""):
    """Favor actual music artists while retaining exact-video channel metadata as a fallback."""
    for field in ("artists", "artist", "creator", "uploader", "channel", "channel_name", "uploader_id", "author"):
        artist = first_metadata_text(item.get(field))
        if artist:
            return artist
    return fallback or "Unknown artist"


def refresh_public_playlist(con, playlist_url, title_hint=None):
    playlist_id = require_url_playlist(playlist_url)
    music_payload = None
    music_error = None
    if YTMusic:
        try:
            music_payload = YTMusic().get_playlist(playlist_id, limit=None)
        except Exception as exc:
            # Some public playlists return a sparse Music browse response. The
            # public yt-dlp extractor is a lower-fidelity but useful fallback.
            music_error = str(exc)
    try:
        payload = ytdlp_public_json(playlist_url) if not music_payload else None
    except WorkerError:
        if music_error:
            raise WorkerError("Could not refresh this public playlist: " + music_error)
        raise
    title = title_hint or (music_payload or {}).get("title") or (payload or {}).get("title") or "Imported playlist"
    local_id, now = "public:" + playlist_id, utcnow()
    con.execute("""INSERT INTO playlist (id,title,source,remote_id,updated_at) VALUES (?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title, source=excluded.source, updated_at=excluded.updated_at""",
                (local_id, title, "Public YouTube Music", playlist_id, now))
    con.execute("DELETE FROM playlist_item WHERE playlist_id=?", (local_id,))
    position = 1
    entries = (music_payload or {}).get("tracks") if music_payload else ytdlp_public_entries(playlist_url)
    for item in entries or []:
        video_id = item.get("videoId") if music_payload else item.get("id")
        unavailable = not video_id
        if unavailable:
            # Preserve the visible playlist position/count for removed or
            # otherwise unavailable public entries without pretending it is downloadable.
            video_id = "unavailable:{}:{}".format(playlist_id, position)
        artist = artist_from_metadata(item)
        thumbs = item.get("thumbnails") or []
        artwork = (thumbs[-1].get("url") if thumbs else item.get("thumbnail"))
        con.execute("""INSERT INTO track (video_id,title,artist,album,duration,artwork_url,local_status,updated_at)
                       VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET
                       title=excluded.title, artist=excluded.artist, artwork_url=excluded.artwork_url, updated_at=excluded.updated_at""",
                    (video_id, item.get("title") or "Unavailable video", artist, title, item.get("duration") if music_payload else human_duration(item.get("duration")), artwork, "unavailable" if unavailable else "missing", now))
        con.execute("INSERT INTO playlist_item (playlist_id,position,video_id) VALUES (?,?,?)", (local_id, position, video_id))
        position += 1
    return local_id


def import_public_profile(payload):
    original_url = str(payload.get("url", ""))
    parsed = require_public_profile_url(original_url)
    host = "www.youtube.com" if parsed.netloc.lower().startswith("music.") else parsed.netloc
    profile_path = parsed.path.rstrip("/")
    playlist_tab = "https://{}{}{}".format(host, profile_path, "" if profile_path.endswith("/playlists") else "/playlists")
    profile = ytdlp_public_json(playlist_tab)
    entries = profile.get("entries") or []
    con = connect()
    try:
        imported, skipped = 0, []
        write_activity("Syncing playlists", 0, len(entries))
        for index, entry in enumerate(entries, 1):
            playlist_id = entry.get("id")
            if not playlist_id:
                continue
            try:
                refresh_public_playlist(con, "https://www.youtube.com/playlist?list=" + playlist_id, entry.get("title"))
                imported += 1
            except WorkerError as exc:
                skipped.append("{} ({})".format(entry.get("title") or playlist_id, str(exc)[:160]))
            con.commit()
            write_activity("Syncing playlists", index, len(entries))
        if not imported:
            raise WorkerError("No public playlists were found on that profile. Check that its Playlists tab is public.")
        con.execute("INSERT INTO setting (key,value) VALUES ('public_profile_url',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (original_url,))
        con.execute("INSERT INTO setting (key,value) VALUES ('last_sync_notice',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("Skipped {} unreadable playlist{} during sync.".format(len(skipped), "s" if len(skipped) != 1 else "") if skipped else "",))
    finally:
        con.close()
        clear_activity()
    return dashboard()


def sync_status(payload):
    mount = Path(str(payload.get("mount_path", ""))).expanduser()
    journal = mount / APP_NAME / "sync-journal.json"
    if not journal.is_file():
        return {"active": False, "state": "idle", "completed": 0, "total": 0, "current": None}
    try:
        data = json.loads(journal.read_text())
        return {"active": data.get("state") in ("staging", "applying"), "state": data.get("state", "working"),
                "completed": data.get("completed", 0), "total": data.get("total", 0), "current": data.get("current")}
    except (OSError, json.JSONDecodeError):
        return {"active": True, "state": "working", "completed": 0, "total": 0, "current": None}


def import_playlist_url(payload):
    playlist_id = require_url_playlist(str(payload.get("url", "")))
    con = connect()
    try:
        refresh_public_playlist(con, "https://www.youtube.com/playlist?list=" + playlist_id)
        con.commit()
    finally:
        con.close()
    return dashboard()


def seed_demo(_payload=None):
    con = connect()
    try:
        now = utcnow()
        playlist_id = "demo:night-drive"
        con.execute("""INSERT INTO playlist (id, title, source, remote_id, loaded, updated_at)
                     VALUES (?, 'Night drive · pilot', 'Sample catalog', 'PL_demo_night', 1, ?)
                     ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at""", (playlist_id, now))
        con.execute("""INSERT INTO playlist (id, title, source, remote_id, loaded, updated_at)
                     VALUES ('demo:liked', 'Liked Music', 'Sample catalog', 'LL_demo', 0, ?)
                     ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at""", (now,))
        samples = [
            ("demo_fog", "Fog Signal", "Orchid Coast", "Night drive · pilot", "3:42", "missing"),
            ("demo_tide", "Tide Pool", "North Loop", "Night drive · pilot", "4:08", "missing"),
            ("demo_neon", "Neon Hours", "Crown Shyness", "Night drive · pilot", "3:18", "missing"),
            ("demo_after", "Afterimage", "Parade Rest", "Liked Music", "2:56", "missing"),
        ]
        for video_id, title, artist, album, duration, state in samples:
            con.execute("""INSERT INTO track (video_id, title, artist, album, duration, local_status, updated_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?)
                         ON CONFLICT(video_id) DO UPDATE SET title=excluded.title, artist=excluded.artist,
                         album=excluded.album, duration=excluded.duration, updated_at=excluded.updated_at""",
                        (video_id, title, artist, album, duration, state, now))
        con.execute("DELETE FROM playlist_item WHERE playlist_id IN ('demo:night-drive','demo:liked')")
        for pos, video_id in enumerate(["demo_fog", "demo_tide", "demo_neon"], 1):
            con.execute("INSERT INTO playlist_item (playlist_id, position, video_id) VALUES (?, ?, ?)", (playlist_id, pos, video_id))
        con.execute("INSERT INTO playlist_item (playlist_id, position, video_id) VALUES ('demo:liked', 1, 'demo_after')")
        con.commit()
    finally:
        con.close()
    return dashboard()


def queue_track(payload):
    video_id = str(payload.get("video_id", ""))
    con = connect()
    try:
        track = con.execute("SELECT video_id, local_status FROM track WHERE video_id = ?", (video_id,)).fetchone()
        if not track:
            raise WorkerError("This exact video is no longer in the local catalog.")
        if track["local_status"] == "unavailable" or video_id.startswith("unavailable:"):
            raise WorkerError("This public playlist entry has no playable video ID.")
        if track["local_status"] == "ready":
            return dashboard()
        outstanding = con.execute("SELECT id FROM download_job WHERE video_id=? AND state IN ('queued','running','retry')", (video_id,)).fetchone()
        if not outstanding:
            now = utcnow()
            con.execute("INSERT INTO download_job (id, video_id, state, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)", (str(uuid.uuid4()), video_id, now, now))
            con.execute("UPDATE track SET local_status='queued', updated_at=? WHERE video_id=?", (now, video_id))
            con.commit()
    finally:
        con.close()
    return dashboard()


def queue_playlist(payload):
    playlist_id = str(payload.get("playlist_id", ""))
    missing_only = bool(payload.get("missing_only", True))
    con = connect()
    try:
        tracks = con.execute("""SELECT t.video_id, t.local_status FROM playlist_item i JOIN track t ON t.video_id=i.video_id
                                WHERE i.playlist_id=? ORDER BY i.position""", (playlist_id,)).fetchall()
        if not tracks:
            raise WorkerError("This playlist has no local items yet. Refresh the public profile first.")
        now = utcnow()
        for track in tracks:
            if track["local_status"] == "unavailable" or track["video_id"].startswith("unavailable:"):
                continue
            if missing_only and track["local_status"] == "ready":
                continue
            present = con.execute("SELECT id FROM download_job WHERE video_id=? AND state IN ('queued','running','retry')", (track["video_id"],)).fetchone()
            if not present:
                con.execute("INSERT INTO download_job (id, video_id, state, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)", (str(uuid.uuid4()), track["video_id"], now, now))
                con.execute("UPDATE track SET local_status='queued', updated_at=? WHERE video_id=?", (now, track["video_id"]))
        con.commit()
    finally:
        con.close()
    return dashboard()


def classify_error(message):
    lowered = message.lower()
    if "429" in lowered or "too many requests" in lowered:
        return "rate_limited", "Rate limited; queue paused for review."
    if "proof of origin" in lowered or "po token" in lowered or "sign in to confirm" in lowered or "bot" in lowered:
        return "proof_of_origin", "YouTube requested proof-of-origin or a bot check; no cookies were used."
    if "private" in lowered:
        return "private", "This item is private or restricted."
    if "not available" in lowered or "unavailable" in lowered:
        return "unavailable", "This item is unavailable in the current region or was removed."
    return "download_failed", message[-300:] or "The downloader did not provide a reason."


def storage_guard():
    root = library_root()
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(str(root))
    minimum = max(MIN_FREE_BYTES, int(usage.total * .10))
    if usage.free < minimum:
        raise WorkerError("Download blocked: free storage is below the safety reserve of {}.".format(minimum))


def build_output_path(track, ext):
    artist = canonical_filename(track["artist"], 80)
    title = canonical_filename(track["title"], 100)
    folder = library_root() / artist
    folder.mkdir(parents=True, exist_ok=True)
    return folder / ("{} — {} [{}].{}".format(artist, title, track["video_id"], ext))


def resolved_track_metadata(track, info):
    """Prefer music fields, then exact-video channel fields, never a search substitute."""
    artist = artist_from_metadata(info, track["artist"])
    title = info.get("track") or info.get("title") or track["title"]
    album = info.get("album") or (track["album"] if "album" in track.keys() else None)
    return {"title": title or "Untitled video", "artist": artist or "Unknown artist", "album": album}


def exact_video_info(video_id):
    ytdlp = dependency_health()["yt_dlp"].get("path")
    if not ytdlp:
        raise WorkerError("yt-dlp is required to resolve library metadata.")
    result = subprocess.run([ytdlp, "--no-playlist", "--skip-download", "--no-warnings", "--print-json",
                             "https://www.youtube.com/watch?v=" + video_id], capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise WorkerError(result.stderr.strip() or "Could not resolve exact video metadata.")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    try:
        return json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        raise WorkerError("The exact video did not return readable metadata.")


def relocate_asset(track, metadata):
    old = Path(track["media_path"])
    if not old.is_file():
        return str(old)
    destination = build_output_path({**dict(track), **metadata}, old.suffix.lower().lstrip("."))
    if old.resolve() != destination.resolve():
        if destination.exists():
            if checksum(destination) == checksum(old):
                old.unlink()
            else:
                destination = destination.with_name(destination.stem + "-copy" + destination.suffix)
                shutil.move(str(old), str(destination))
        else:
            shutil.move(str(old), str(destination))
    return str(destination)


def prepare_artwork(work, ffmpeg):
    candidates = [item for item in work.iterdir() if item.is_file() and item.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    if not candidates:
        return None
    source = max(candidates, key=lambda item: item.stat().st_mtime)
    artwork = work / "cover-500.jpg"
    if ffmpeg:
        converted = subprocess.run([ffmpeg, "-y", "-i", str(source), "-vf", "scale=500:500:force_original_aspect_ratio=decrease,pad=500:500:(ow-iw)/2:(oh-ih)/2",
                                    "-frames:v", "1", "-q:v", "3", str(artwork)], capture_output=True, text=True, timeout=180)
        if converted.returncode == 0 and artwork.is_file():
            return artwork
    return source


def run_download(track):
    storage_guard()
    deps = dependency_health()
    ytdlp = deps["yt_dlp"].get("path")
    if not ytdlp:
        raise WorkerError("yt-dlp is not installed. Add it to Digital Audio Manager's managed bin folder or your PATH, then retry.")
    work = app_data() / "downloads" / track["video_id"]
    work.mkdir(parents=True, exist_ok=True)
    template = str(work / "source.%(ext)s")
    url = "https://www.youtube.com/watch?v=" + track["video_id"]
    command = [
        ytdlp, "--no-playlist", "--continue", "--retries", "3", "--fragment-retries", "3",
        "--sleep-interval", "1", "--max-sleep-interval", "4", "--no-warnings", "--print-json", "--embed-metadata",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-f", "bestaudio[ext=m4a]/bestaudio", "-o", template, url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise WorkerError(result.stderr or result.stdout)
    media_extensions = {"m4a", "aac", "opus", "ogg", "webm", "mp3", "wav"}
    sources = [item for item in work.iterdir() if item.is_file() and item.suffix.lower().lstrip(".") in media_extensions and not item.name.endswith(".part")]
    if not sources:
        raise WorkerError("yt-dlp reported success but did not create a media file.")
    source = max(sources, key=lambda item: item.stat().st_mtime)
    ext = source.suffix.lower().lstrip(".")
    ffmpeg = deps["ffmpeg"].get("path")
    direct = ext in ("m4a", "aac")
    info = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
    metadata = resolved_track_metadata(track, info)
    target_track = {**dict(track), **metadata}
    artwork = prepare_artwork(work, ffmpeg)
    if direct:
        destination = build_output_path(target_track, "m4a")
        if artwork and ffmpeg:
            embedded = subprocess.run([ffmpeg, "-y", "-i", str(source), "-i", str(artwork), "-map", "0:a", "-map", "1:v",
                                        "-c:a", "copy", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic",
                                        "-metadata", "title=" + metadata["title"], "-metadata", "artist=" + metadata["artist"], str(destination)], capture_output=True, text=True, timeout=600)
            if embedded.returncode != 0:
                shutil.move(str(source), str(destination))
        else:
            shutil.move(str(source), str(destination))
        codec = ext
    else:
        if not ffmpeg:
            raise WorkerError("The source is not an approved direct M4A/AAC file and ffmpeg is unavailable for MP3 fallback.")
        destination = build_output_path(target_track, "mp3")
        command = [ffmpeg, "-y", "-i", str(source)]
        if artwork:
            command += ["-i", str(artwork), "-map", "0:a", "-map", "1:v", "-c:v", "mjpeg", "-disposition:v:0"]
        else:
            command += ["-vn"]
        command += ["-c:a", "libmp3lame", "-b:a", "320k", "-metadata", "title=" + metadata["title"], "-metadata", "artist=" + metadata["artist"], str(destination)]
        converted = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if converted.returncode != 0:
            raise WorkerError(converted.stderr[-500:])
        source.unlink(missing_ok=True)
        codec = "mp3-320-cbr"
    if destination.stat().st_size < 1024:
        destination.unlink(missing_ok=True)
        raise WorkerError("Downloaded file was implausibly small and was removed.")
    if artwork and artwork.is_file():
        shutil.copy2(artwork, destination.with_suffix(".jpg"))
    return destination, codec, checksum(destination), metadata


def run_queue(_payload=None):
    con = connect()
    completed, total = 0, con.execute("SELECT COUNT(*) FROM download_job WHERE state IN ('queued','retry')").fetchone()[0]
    write_activity("Downloading", 0, total)
    try:
        while True:
            job = con.execute("""SELECT j.*, t.title, t.artist, t.album FROM download_job j JOIN track t ON t.video_id=j.video_id
                                 WHERE j.state IN ('queued','retry') ORDER BY j.created_at LIMIT 1""").fetchone()
            if not job:
                break
            now = utcnow()
            con.execute("UPDATE download_job SET state='running', attempts=attempts+1, updated_at=? WHERE id=?", (now, job["id"]))
            con.execute("UPDATE track SET local_status='downloading', updated_at=? WHERE video_id=?", (now, job["video_id"]))
            con.commit()
            try:
                destination, codec, digest, metadata = run_download(job)
                con.execute("UPDATE track SET title=?, artist=?, album=?, local_status='ready', media_path=?, source_codec=?, checksum=?, updated_at=? WHERE video_id=?",
                            (metadata["title"], metadata["artist"], metadata["album"], str(destination), codec, digest, utcnow(), job["video_id"]))
                con.execute("UPDATE download_job SET state='completed', error_code=NULL, error_message=NULL, updated_at=? WHERE id=?", (utcnow(), job["id"]))
            except Exception as exc:
                code, message = classify_error(str(exc))
                con.execute("UPDATE track SET local_status='failed', updated_at=? WHERE video_id=?", (utcnow(), job["video_id"]))
                con.execute("UPDATE download_job SET state='failed', error_code=?, error_message=?, updated_at=? WHERE id=?", (code, message, utcnow(), job["id"]))
                con.commit()
                if code in ("rate_limited", "proof_of_origin"):
                    break
            con.commit()
            completed += 1
            write_activity("Downloading", completed, total)
    finally:
        con.close()
        clear_activity()
    return dashboard()


def repair_library_metadata(_payload=None):
    con = connect()
    try:
        tracks = con.execute("SELECT * FROM track WHERE local_status='ready' AND lower(artist) IN ('unknown artist','unknown') ORDER BY updated_at").fetchall()
        for track in tracks:
            try:
                metadata = resolved_track_metadata(track, exact_video_info(track["video_id"]))
                media_path = relocate_asset(track, metadata)
                con.execute("UPDATE track SET title=?, artist=?, album=?, media_path=?, updated_at=? WHERE video_id=?",
                            (metadata["title"], metadata["artist"], metadata["album"], media_path, utcnow(), track["video_id"]))
                con.commit()
            except Exception:
                # Keep the existing verified file and make later retry possible.
                continue
    finally:
        con.close()
    return dashboard()


def reset_and_resync_library(_payload=None):
    """Destructively reset only local masters/state; sources remain for a later manual sync."""
    masters = library_root()
    temporary = app_data() / "downloads"
    # These are fixed app-owned directories; device exports deliberately remain untouched.
    write_activity("Clearing library", 0, 2)
    for index, target in enumerate((masters, temporary), 1):
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        write_activity("Clearing library", index, 2)
    con = connect()
    try:
        con.execute("DELETE FROM download_job")
        con.execute("DELETE FROM playlist_item")
        con.execute("DELETE FROM track")
        con.execute("DELETE FROM playlist")
        con.execute("DELETE FROM setting WHERE key='last_sync_notice'")
        con.commit()
    finally:
        con.close()
        clear_activity()
    return dashboard()


def cancel_job(payload):
    con = connect()
    try:
        job = con.execute("SELECT video_id FROM download_job WHERE id=?", (str(payload.get("job_id", "")),)).fetchone()
        if not job:
            raise WorkerError("Download job was not found.")
        con.execute("UPDATE download_job SET state='cancelled', updated_at=? WHERE id=?", (utcnow(), payload["job_id"]))
        con.execute("UPDATE track SET local_status='missing', updated_at=? WHERE video_id=?", (utcnow(), job["video_id"]))
        con.commit()
    finally:
        con.close()
    return dashboard()


def retry_job(payload):
    con = connect()
    try:
        job = con.execute("SELECT video_id FROM download_job WHERE id=?", (str(payload.get("job_id", "")),)).fetchone()
        if not job:
            raise WorkerError("Download job was not found.")
        con.execute("UPDATE download_job SET state='retry', error_code=NULL, error_message=NULL, updated_at=? WHERE id=?", (utcnow(), payload["job_id"]))
        con.execute("UPDATE track SET local_status='queued', updated_at=? WHERE video_id=?", (utcnow(), job["video_id"]))
        con.commit()
    finally:
        con.close()
    return dashboard()


def set_loaded_playlist(payload):
    playlist_id = str(payload.get("playlist_id", ""))
    con = connect()
    try:
        cursor = con.execute("UPDATE playlist SET loaded=?, updated_at=? WHERE id=?", (1 if payload.get("loaded") else 0, utcnow(), playlist_id))
        if cursor.rowcount != 1:
            raise WorkerError("Playlist was not found.")
        con.commit()
    finally:
        con.close()
    return dashboard()


def desired_export(con):
    rows = con.execute("""SELECT p.id playlist_id, p.title playlist_title, i.position, t.video_id, t.title, t.artist,
                                t.media_path, t.checksum FROM playlist p JOIN playlist_item i ON i.playlist_id=p.id
                         JOIN track t ON t.video_id=i.video_id WHERE p.loaded=1 ORDER BY p.title COLLATE NOCASE, i.position""").fetchall()
    desired, warnings = [], []
    for row in rows:
        if not row["media_path"] or not Path(row["media_path"]).is_file():
            warnings.append("{} — {} is not available locally and will be skipped.".format(row["artist"], row["title"]))
            continue
        suffix = Path(row["media_path"]).suffix.lower() or ".mp3"
        playlist = canonical_filename(row["playlist_title"], 80)
        filename = "{:04d} - {} - {}{}".format(row["position"], canonical_filename(row["artist"], 80), canonical_filename(row["title"], 100), suffix)
        desired.append({"relative": str(Path("Playlists") / playlist / filename), "source": row["media_path"], "checksum": row["checksum"] or checksum(row["media_path"]), "playlist": playlist, "position": row["position"], "title": row["title"], "artist": row["artist"]})
    if len(desired) > MAX_EXPORT_FILES:
        warnings.append("{} files exceed the {}-file Echo Nano guard; offload playlists before syncing.".format(len(desired), MAX_EXPORT_FILES))
    return desired, warnings


def existing_manifest(root):
    manifest = root / "manifest.json"
    if not manifest.is_file():
        return {"entries": []}
    try:
        return json.loads(manifest.read_text())
    except (json.JSONDecodeError, OSError):
        raise WorkerError("The existing Digital Audio Manager manifest is unreadable. Refusing to overwrite it.")


def sync_preview(payload):
    mount = Path(str(payload.get("mount_path", ""))).expanduser()
    con = connect()
    try:
        desired, warnings = desired_export(con)
    finally:
        con.close()
    root = mount / APP_NAME
    old = existing_manifest(root) if root.exists() else {"entries": []}
    old_by_path = {entry["relative"]: entry for entry in old.get("entries", [])}
    wanted_paths = {entry["relative"] for entry in desired}
    additions = [entry for entry in desired if old_by_path.get(entry["relative"], {}).get("checksum") != entry["checksum"]]
    removals = [entry for entry in old.get("entries", []) if entry.get("relative") not in wanted_paths]
    if not mount.is_dir():
        warnings.insert(0, "{} is not mounted. Preview is estimated; sync will remain disabled until it is available.".format(mount))
    if len(desired) > MAX_EXPORT_FILES:
        pass
    duplicates = len(desired) - len({entry["checksum"] for entry in desired})
    return {"device": mount.name or "Selected volume", "managed_root": str(root), "files_to_copy": len(additions), "files_to_remove": len(removals),
            "projected_bytes": sum(Path(entry["source"]).stat().st_size for entry in additions),
            "existing_bytes": sum(Path(entry["source"]).stat().st_size for entry in desired), "duplicate_files": duplicates,
            "physical_files_after": len(desired), "shuffle_bias": "{} duplicate {} will receive extra weight in Shuffle All.".format(duplicates, "copy" if duplicates == 1 else "copies"),
            "warnings": warnings, "additions": [entry["relative"] for entry in additions], "removals": [entry.get("relative", "") for entry in removals]}


def sync_apply(payload):
    preview = sync_preview(payload)
    mount = Path(str(payload.get("mount_path", ""))).expanduser()
    if not mount.is_dir():
        raise WorkerError("Mount the Echo Nano volume before syncing.")
    if preview["physical_files_after"] > MAX_EXPORT_FILES:
        raise WorkerError("Sync blocked by the {} physical-file guard.".format(MAX_EXPORT_FILES))
    root = mount / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    con = connect()
    try:
        desired, warnings = desired_export(con)
    finally:
        con.close()
    if warnings:
        raise WorkerError("Sync blocked until missing local tracks are resolved: " + warnings[0])
    journal = root / "sync-journal.json"
    stage = root / (".staging-" + uuid.uuid4().hex)
    journal.write_text(json.dumps({"state": "staging", "started_at": utcnow(), "stage": stage.name,
                                   "completed": 0, "total": len(desired), "current": None}, indent=2))
    try:
        ffmpeg = dependency_health()["ffmpeg"].get("path")
        if not ffmpeg:
            raise WorkerError("Sync blocked: ffmpeg is required to write playlist-copy tags for the Echo Nano.")
        for index, entry in enumerate(desired, 1):
            journal.write_text(json.dumps({"state": "staging", "started_at": utcnow(), "stage": stage.name,
                                           "completed": index - 1, "total": len(desired), "current": entry["relative"]}, indent=2))
            output = stage / entry["relative"]
            output.parent.mkdir(parents=True, exist_ok=True)
            tagged = subprocess.run([
                ffmpeg, "-y", "-i", entry["source"], "-map", "0", "-c", "copy",
                "-metadata", "album_artist=* PLAYLISTS *", "-metadata", "album=" + entry["playlist"],
                "-metadata", "track=" + str(entry["position"]), str(output),
            ], capture_output=True, text=True, timeout=600)
            if tagged.returncode != 0:
                raise WorkerError("Could not tag staged export {}: {}".format(entry["relative"], tagged.stderr[-240:]))
            if checksum(output) != entry["checksum"]:
                # Retagging legitimately changes container bytes. Decode failure is still unsafe.
                probe = find_tool("ffprobe", [Path("/opt/homebrew/bin/ffprobe")])
                verified = probe and subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1", str(output)], capture_output=True, text=True).returncode == 0
                if not verified:
                    raise WorkerError("Could not verify staged export {}.".format(entry["relative"]))
            journal.write_text(json.dumps({"state": "staging", "started_at": utcnow(), "stage": stage.name,
                                           "completed": index, "total": len(desired), "current": entry["relative"]}, indent=2))
        journal.write_text(json.dumps({"state": "applying", "started_at": utcnow(), "stage": stage.name}, indent=2))
        playlists_dir = root / "Playlists"
        staged_playlists = stage / "Playlists"
        backup = root / (".previous-" + uuid.uuid4().hex)
        if playlists_dir.exists():
            playlists_dir.rename(backup)
        staged_playlists.rename(playlists_dir)
        if backup.exists():
            shutil.rmtree(backup)
        manifest = {"version": 1, "updated_at": utcnow(), "entries": [{key: entry[key] for key in ("relative", "checksum", "playlist", "position", "title", "artist")} for entry in desired]}
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        (root / ".mp3-maker-device.json").write_text(json.dumps({"app": APP_NAME, "created_at": utcnow()}, indent=2))
        journal.unlink(missing_ok=True)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return sync_preview(payload)


OPERATIONS = {"dashboard": dashboard, "health_check": health_check, "import_public_profile": import_public_profile,
              "import_playlist_url": import_playlist_url,
              "seed_demo": seed_demo, "queue_track": queue_track, "queue_playlist": queue_playlist,
              "run_queue": run_queue, "repair_library_metadata": repair_library_metadata, "reset_and_resync_library": reset_and_resync_library,
              "cancel_job": cancel_job, "retry_job": retry_job,
              "set_loaded_playlist": set_loaded_playlist, "sync_preview": sync_preview, "sync_apply": sync_apply,
              "sync_status": sync_status}


def main():
    try:
        request = json.loads(os.environ["MP3_MAKER_REQUEST"]) if os.environ.get("MP3_MAKER_REQUEST") else json.load(sys.stdin)
        operation = request.get("method")
        if operation not in OPERATIONS:
            raise WorkerError("Unknown worker operation: {}".format(operation))
        response = OPERATIONS[operation](request.get("payload") or {})
        print(json.dumps({"ok": True, "data": response}, ensure_ascii=False))
    except WorkerError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "Unexpected worker error: " + str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
