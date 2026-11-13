#!/usr/bin/env python3
"""Local JSON worker for Digital Audio Manager.

This process deliberately has no HTTP listener. The native client invokes one operation at a
time and passes a small JSON request in the MP3_MAKER_REQUEST environment
variable (stdin is accepted when it is unset); durable state lives in SQLite.
"""
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import platform
import subprocess
import sys
import tarfile
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

try:
    from ytmusicapi import YTMusic
except Exception:
    YTMusic = None

APP_NAME = "Digital Audio Manager"
LEGACY_APP_NAME = "MP3 Maker"
MAX_EXPORT_FILES = 8000
MIN_FREE_BYTES = 20 * 1024 ** 3
UNSORTED_COLLECTION_ID = "system:unsorted"
LIBRARY_MANIFEST = "library.json"
LIBRARY_MANIFEST_FORMAT = "digital-audio-manager.library"
NODE_INDEX_URL = "https://nodejs.org/dist/index.json"
YTDLP_RELEASE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"


class WorkerError(Exception):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def app_data():
    from .paths import data_directory
    return data_directory()


def library_root():
    configured = os.environ.get("MP3_MAKER_LIBRARY")
    if configured:
        return Path(configured).expanduser()
    from .paths import default_library
    con = connect()
    try:
        saved = con.execute("SELECT value FROM setting WHERE key='library_root'").fetchone()
        return Path(saved["value"]) if saved else default_library()
    finally:
        con.close()


def set_music_folder(payload):
    if os.environ.get("MP3_MAKER_LIBRARY"):
        raise WorkerError("The download folder is set by MP3_MAKER_LIBRARY. Remove that override before choosing a folder.")
    folder = Path(str(payload.get("path", ""))).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise WorkerError("Choose an existing Music folder on a connected device.")
    folder = folder.resolve()
    # Selecting an existing app folder must not nest another copy inside it.
    if folder.name == "Library" and folder.parent.name == APP_NAME:
        destination = folder
    else:
        destination = (folder if folder.name == APP_NAME else folder / APP_NAME) / "Library"
    if destination.is_symlink() or destination.parent.is_symlink():
        raise WorkerError("The managed download folder is a symbolic link. Choose a different Music folder.")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=destination):
        pass
    con = connect()
    try:
        if con.execute("SELECT 1 FROM download_job WHERE state='running'").fetchone():
            raise WorkerError("Wait for the current download to finish before changing folders.")
        con.execute("INSERT OR REPLACE INTO setting VALUES ('library_root', ?)", (str(destination),))
        con.execute("INSERT OR REPLACE INTO setting VALUES ('music_folder', ?)", (str(destination.parent.parent),))
        con.commit()
    finally:
        con.close()
    return dashboard()


def music_folder_available():
    if os.environ.get("MP3_MAKER_LIBRARY"):
        return True
    con = connect()
    try:
        row = con.execute("SELECT value FROM setting WHERE key='music_folder'").fetchone()
        return not row or Path(row["value"]).is_dir()
    finally:
        con.close()


def db_path():
    return app_data() / "mp3-maker.sqlite3"


def activity_path():
    return app_data() / "activity.json"


def dependency_status_path():
    return app_data() / "dependency-status.json"


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
        remote_id TEXT, loaded INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'collection'
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
    # Older libraries predate collection kinds. Keep every existing imported
    # playlist intact while making room for the persistent Unsorted collection.
    columns = {row["name"] for row in con.execute("PRAGMA table_info(playlist)")}
    if "kind" not in columns:
        con.execute("ALTER TABLE playlist ADD COLUMN kind TEXT NOT NULL DEFAULT 'collection'")
    # The size and modification time a checksum was taken at, so unchanged files are not hashed again.
    columns = {row["name"] for row in con.execute("PRAGMA table_info(track)")}
    for column in ("media_size", "media_mtime_ns"):
        if column not in columns:
            con.execute("ALTER TABLE track ADD COLUMN {} INTEGER".format(column))
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


def staging_path(destination):
    """A hidden name beside destination, so a half-written file is never seen under its final name."""
    destination = Path(destination)
    return destination.with_name(".{}.{}.partial{}".format(destination.stem, uuid.uuid4().hex[:8], destination.suffix))


def library_manifest_entries(con, root):
    """Ready downloads inside root, with checksums cached against each file's size and modification time."""
    root = root.resolve()
    playlists = {}
    for row in con.execute("""SELECT i.video_id, p.id, p.title, i.position FROM playlist_item i JOIN playlist p ON p.id=i.playlist_id
                              ORDER BY p.title COLLATE NOCASE, p.id, i.position"""):
        playlists.setdefault(row["video_id"], []).append({"id": row["id"], "title": row["title"], "position": row["position"]})
    entries = []
    rows = con.execute("""SELECT video_id, media_path, checksum, media_size, media_mtime_ns FROM track
                          WHERE local_status='ready' AND media_path IS NOT NULL ORDER BY video_id""").fetchall()
    for row in rows:
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", row["video_id"]):
            continue
        path = Path(row["media_path"])
        try:
            stat = path.stat()
            relative = path.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        digest = row["checksum"]
        if not digest or row["media_size"] != stat.st_size or row["media_mtime_ns"] != stat.st_mtime_ns:
            try:
                digest = checksum(path)
            except OSError:
                continue
            con.execute("UPDATE track SET checksum=?, media_size=?, media_mtime_ns=? WHERE video_id=?",
                        (digest, stat.st_size, stat.st_mtime_ns, row["video_id"]))
        entries.append({"path": relative.as_posix(), "videoId": row["video_id"], "sha256": digest,
                        "size": stat.st_size, "playlists": playlists.get(row["video_id"], [])})
    return entries


def write_library_manifest(con):
    """Replace library.json atomically when the library's downloads or playlists changed.

    It lists only paths, video ids, checksums, sizes and playlist positions: no account data or URLs.
    """
    if not music_folder_available():
        return
    root = library_root()
    if not root.is_dir():
        return
    entries = library_manifest_entries(con, root)
    con.commit()
    target = root / LIBRARY_MANIFEST
    try:
        current = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current = None
    if (isinstance(current, dict) and current.get("format") == LIBRARY_MANIFEST_FORMAT
            and current.get("version") == 1 and current.get("entries") == entries):
        return
    document = {"format": LIBRARY_MANIFEST_FORMAT, "version": 1, "updated_at": utcnow(), "entries": entries}
    staged = staging_path(target)
    try:
        with open(staged, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, target)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def refresh_library_manifest(con):
    """Keep library.json current without letting a read-only or busy folder break the caller."""
    try:
        write_library_manifest(con)
    except (OSError, sqlite3.Error):
        pass


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


def managed_bin_dir():
    directory = app_data() / "bin"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def managed_tool_path(name):
    return managed_bin_dir() / (name + (".exe" if os.name == "nt" else ""))


def host_platform():
    system = platform.system().lower()
    machine = platform.machine().lower()
    normalized_system = {"darwin": "darwin", "windows": "win", "linux": "linux"}.get(system)
    normalized_arch = "arm64" if machine in ("arm64", "aarch64") else "x64" if machine in ("x86_64", "amd64") else None
    if not normalized_system or not normalized_arch:
        raise WorkerError("Automatic tool setup is not supported on this platform ({} {}).".format(system, machine))
    return normalized_system, normalized_arch


def download_bytes(url, timeout=90):
    request = Request(url, headers={"User-Agent": "DigitalAudioManager/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def write_managed_executable(destination, content):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.chmod(0o755)
    temporary.replace(destination)


def install_managed_ytdlp():
    system, _arch = host_platform()
    asset = {"darwin": "yt-dlp_macos", "linux": "yt-dlp", "win": "yt-dlp.exe"}[system]
    destination = managed_tool_path("yt-dlp")
    write_managed_executable(destination, download_bytes(YTDLP_RELEASE_URL + asset))
    return str(destination)


def node_archive_details(release, system, arch):
    platform_name = {"darwin": "darwin", "linux": "linux", "win": "win"}[system]
    extension = "zip" if system == "win" else "tar.gz" if system == "darwin" else "tar.xz"
    filename = "node-{}-{}-{}.{}".format(release, platform_name, arch, extension)
    return filename, "https://nodejs.org/dist/{}/{}".format(release, filename)


def install_managed_node():
    system, arch = host_platform()
    releases = json.loads(download_bytes(NODE_INDEX_URL).decode("utf-8"))
    release = next((item["version"] for item in releases if item.get("lts")), None)
    if not release:
        raise WorkerError("Node.js did not publish an LTS runtime for automatic setup.")
    filename, archive_url = node_archive_details(release, system, arch)
    checksums = download_bytes("https://nodejs.org/dist/{}/SHASUMS256.txt".format(release)).decode("utf-8")
    expected = next((line.split()[0] for line in checksums.splitlines() if line.endswith("  " + filename)), None)
    archive = download_bytes(archive_url)
    if not expected or hashlib.sha256(archive).hexdigest().lower() != expected.lower():
        raise WorkerError("The downloaded Node.js runtime failed its official checksum verification.")
    binary_name = "node.exe" if system == "win" else "node"
    if system == "win":
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            member = next((entry for entry in package.namelist() if entry.endswith("/" + binary_name)), None)
            content = package.read(member) if member else None
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as package:
            member = next((entry for entry in package.getmembers() if entry.isfile() and entry.name.endswith("/bin/" + binary_name)), None)
            source = package.extractfile(member) if member else None
            content = source.read() if source else None
    if not content:
        raise WorkerError("The Node.js archive did not contain its runtime executable.")
    destination = managed_tool_path("node")
    write_managed_executable(destination, content)
    return str(destination)


def save_dependency_status(status):
    app_data().mkdir(parents=True, exist_ok=True)
    dependency_status_path().write_text(json.dumps(status))


def read_dependency_status():
    try:
        return json.loads(dependency_status_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def bootstrap_dependencies(_payload=None):
    """Install managed downloader runtimes once for clean desktop installs."""
    status = {}
    for name, executable, installer in (("yt_dlp", "yt-dlp", install_managed_ytdlp), ("node", "node", install_managed_node)):
        if (name == "yt_dlp" and importlib.util.find_spec("yt_dlp")) or find_tool(executable, [managed_tool_path(executable)]):
            status[name] = {"state": "ready"}
            continue
        try:
            installer()
            status[name] = {"state": "ready"}
        except Exception as exc:
            status[name] = {"state": "failed", "detail": str(exc)[-240:]}
    save_dependency_status(status)
    return dashboard()


def dependency_health():
    managed = managed_tool_path("yt-dlp")
    managed_node = managed_tool_path("node")
    ffmpeg = find_tool("ffmpeg", [Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")])
    ffprobe = find_tool("ffprobe", [Path("/opt/homebrew/bin/ffprobe"), Path("/usr/local/bin/ffprobe")])
    node = find_tool("node", [managed_node])
    ytdlp = "bundled" if importlib.util.find_spec("yt_dlp") else find_tool("yt-dlp", [managed])
    status = read_dependency_status()
    return {
        "yt_dlp": {"available": bool(ytdlp), "path": ytdlp, "detail": status.get("yt_dlp", {}).get("detail") or "Bundled exact-video downloader."},
        "ffmpeg": {"available": bool(ffmpeg and ffprobe), "path": ffmpeg, "detail": "Used for verified MP3 fallback and device copy tags."},
        "node": {"available": bool(node), "path": node, "detail": status.get("node", {}).get("detail") or "Managed automatically for yt-dlp proof-of-origin support."},
    }


def ytdlp_command(arguments):
    """Run yt-dlp with the managed Node runtime when it is available."""
    deps = dependency_health()
    ytdlp = deps["yt_dlp"].get("path")
    if not ytdlp:
        raise WorkerError("yt-dlp is still being set up. Check Settings and retry shortly.")
    node = deps["node"].get("path")
    from .launcher import process_command
    command = process_command("extractor") if ytdlp == "bundled" else [ytdlp]
    return [*command, *(["--js-runtimes", "node:" + node] if node else []), *arguments]


def health_check(_payload=None):
    root = library_root()
    available = music_folder_available()
    try:
        if available:
            root.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(str(root))
    except OSError:
        available = False
    return {
        "app_data": str(app_data()), "library_root": str(root), "storage_available": available,
        "free_bytes": usage.free if available else 0,
        "minimum_free_bytes": max(MIN_FREE_BYTES, int(usage.total * .10)) if available else MIN_FREE_BYTES,
        "dependencies": dependency_health(),
    }


def dashboard(_payload=None):
    con = connect()
    try:
        reconcile_files(con)
        con.commit()
        refresh_library_manifest(con)
        playlists = [dict(row) for row in con.execute("""
          SELECT p.id, p.title, p.source, p.loaded, p.updated_at, p.kind, COUNT(i.video_id) AS track_count
          FROM playlist p LEFT JOIN playlist_item i ON p.id = i.playlist_id
          GROUP BY p.id ORDER BY CASE p.kind WHEN 'unsorted' THEN 0 ELSE 1 END, p.updated_at DESC, p.title COLLATE NOCASE
        """)]
        tracks = [dict(row) for row in con.execute("""
          SELECT p.id || ':' || i.position AS id, p.id AS playlist_id, i.position, t.video_id,
                 t.title, t.artist, CASE WHEN p.kind='unsorted' OR t.video_id LIKE 'local:%' THEN t.album ELSE p.title END AS album, t.duration, t.artwork_url,
                 CASE WHEN t.local_status='failed' AND t.video_id LIKE 'unavailable:%' THEN 'unavailable' ELSE t.local_status END AS local_status,
                 t.media_path
          FROM playlist_item i JOIN playlist p ON p.id=i.playlist_id JOIN track t ON t.video_id=i.video_id
          ORDER BY p.title COLLATE NOCASE, i.position
        """)]
        tracks.extend(dict(row) for row in con.execute("""
          SELECT 'file:' || t.video_id AS id, '' AS playlist_id, 0 AS position,
                 t.video_id, t.title, t.artist, t.album, t.duration, t.artwork_url, t.local_status, t.media_path
          FROM track t WHERE t.video_id NOT LIKE 'local:%'
          AND NOT EXISTS (SELECT 1 FROM playlist_item i WHERE i.video_id=t.video_id)
        """))
        jobs = [dict(row) for row in con.execute("""
          SELECT j.id, j.video_id, t.title, t.artist, j.state, j.attempts, j.error_code,
                 j.error_message, j.updated_at
          FROM download_job j JOIN track t ON t.video_id = j.video_id
          WHERE j.state NOT IN ('completed', 'cancelled')
          ORDER BY CASE j.state WHEN 'running' THEN 0 WHEN 'queued' THEN 1 WHEN 'retry' THEN 2 WHEN 'failed' THEN 3 ELSE 4 END,
                   j.updated_at DESC
        """)]
        profile = con.execute("SELECT value FROM setting WHERE key='public_profile_url'").fetchone()
        sync_notice = con.execute("SELECT value FROM setting WHERE key='last_sync_notice'").fetchone()
        queue_pause = con.execute("SELECT value FROM setting WHERE key='queue_pause_reason'").fetchone()
        return {"playlists": playlists, "tracks": tracks, "jobs": jobs, "health": health_check(),
                "queue_pause_reason": queue_pause["value"] if queue_pause else "",
                "public_profile_url": profile["value"] if profile else None,
                "sync_notice": sync_notice["value"] if sync_notice and sync_notice["value"] else None,
                "activity": read_activity()}
    finally:
        con.close()


def reconcile_files(con):
    """Keep retained paths so a reconnected drive restores availability."""
    for row in con.execute("SELECT video_id, media_path, local_status FROM track WHERE local_status IN ('ready','missing')").fetchall():
        path = row['media_path']
        exists = bool(path and Path(path).is_file())
        status = 'ready' if exists else 'missing'
        if status != row['local_status']:
            con.execute('UPDATE track SET local_status=? WHERE video_id=?', (status, row['video_id']))


def remove_download(payload):
    video_id = str(payload.get('video_id', ''))
    con = connect()
    try:
        con.execute('BEGIN IMMEDIATE')
        track = con.execute('SELECT * FROM track WHERE video_id=?', (video_id,)).fetchone()
        if not track or video_id.startswith('local:'):
            raise WorkerError('Only downloads made by this app can be deleted here. Imported originals are kept.')
        if con.execute("SELECT 1 FROM download_job WHERE video_id=? AND state='running'", (video_id,)).fetchone():
            raise WorkerError('Wait for this song to finish downloading before removing it.')
        path = Path(track['media_path']) if track['media_path'] else None
        if path:
            protected = {Path(row[0]).resolve() for row in con.execute(
                'SELECT media_path FROM track WHERE video_id!=? AND media_path IS NOT NULL', (video_id,))}
            if not path.is_absolute() or path.resolve() in protected:
                raise WorkerError('This file is also used by another library entry. Remove that reference before deleting the download.')
            try:
                path.unlink(missing_ok=True)
                cover = path.with_suffix('.jpg')
                if cover.resolve() not in protected:
                    cover.unlink(missing_ok=True)
            except OSError as exc:
                raise WorkerError('Could not delete the download. Close other players and check folder permissions, then try again.') from exc
        con.execute("UPDATE download_job SET state='cancelled', updated_at=? WHERE video_id=? AND state IN ('queued','retry','failed')", (utcnow(), video_id))
        con.execute("""UPDATE track SET local_status='missing', media_path=NULL, checksum=NULL,
                       artwork_url=CASE WHEN artwork_url LIKE 'file:%' THEN NULL ELSE artwork_url END,
                       updated_at=? WHERE video_id=?""", (utcnow(), video_id))
        con.commit()
    finally:
        con.close()
    return dashboard()


def require_url_playlist(url):
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("https", "http") or "youtube" not in parsed.netloc:
        raise WorkerError("Use a YouTube or YouTube Music playlist URL.")
    playlist_id = parse_qs(parsed.query).get("list", [None])[0]
    if not playlist_id:
        raise WorkerError("That link does not contain a playlist ID (the `list` parameter).")
    return playlist_id


def require_import_source(url):
    """Return a supported public import source: a playlist or Music album."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split(":")[0]
    if parsed.scheme not in ("https", "http") or host not in ("youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com"):
        raise WorkerError("Use a public YouTube Music playlist or album URL.")
    playlist_id = parse_qs(parsed.query).get("list", [None])[0]
    if playlist_id:
        return "playlist", playlist_id
    browse_id = parse_qs(parsed.query).get("browseId", [None])[0]
    if not browse_id and host == "music.youtube.com":
        match = re.fullmatch(r"/browse/([^/]+)", parsed.path.rstrip("/"))
        browse_id = match.group(1) if match else None
    if browse_id:
        return "album", browse_id
    raise WorkerError("Use a public YouTube Music playlist or album URL.")


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
    result = subprocess.run(ytdlp_command(["--no-warnings", "--flat-playlist", "--dump-single-json", url]), capture_output=True, text=True, timeout=timeout)
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
    result = subprocess.run(ytdlp_command(["--no-warnings", "--flat-playlist", "--dump-json", url]), capture_output=True, text=True, timeout=timeout)
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
    entries = (music_payload or {}).get("tracks") if music_payload else ytdlp_public_entries(playlist_url)
    return store_playlist(con, playlist_id, title, entries, bool(music_payload))


def store_playlist(con, playlist_id, title, entries, music=True, source="Public YouTube Music"):
    local_id, now = "public:" + playlist_id, utcnow()
    con.execute("""INSERT INTO playlist (id,title,source,remote_id,updated_at) VALUES (?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title, source=excluded.source, updated_at=excluded.updated_at""",
                (local_id, title, source, playlist_id, now))
    con.execute("DELETE FROM playlist_item WHERE playlist_id=?", (local_id,))
    position = 1
    for item in entries or []:
        video_id = item.get("videoId") if music else item.get("id")
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
                    (video_id, item.get("title") or "Unavailable video", artist, title, item.get("duration") if music else human_duration(item.get("duration")), artwork, "unavailable" if unavailable else "missing", now))
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
        con.commit()
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


def ensure_unsorted_collection(con):
    now = utcnow()
    con.execute("""INSERT INTO playlist (id, title, source, remote_id, loaded, updated_at, kind)
                   VALUES (?, 'Unsorted', 'Quick import', NULL, 0, ?, 'unsorted')
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title, source=excluded.source,
                   kind='unsorted', updated_at=excluded.updated_at""", (UNSORTED_COLLECTION_ID, now))


def queue_video_ids(con, video_ids, missing_only=True):
    """Queue known, playable tracks once and return the number newly queued."""
    queued, now = 0, utcnow()
    reconcile_files(con)
    for video_id in dict.fromkeys(video_ids):
        track = con.execute("SELECT local_status FROM track WHERE video_id=?", (video_id,)).fetchone()
        if not track or track["local_status"] == "unavailable" or video_id.startswith(("unavailable:", "local:")):
            continue
        if missing_only and track["local_status"] == "ready":
            continue
        present = con.execute("SELECT id FROM download_job WHERE video_id=? AND state IN ('queued','running','retry')", (video_id,)).fetchone()
        if present:
            continue
        con.execute("INSERT INTO download_job (id, video_id, state, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)",
                    (str(uuid.uuid4()), video_id, now, now))
        con.execute("UPDATE track SET local_status='queued', updated_at=? WHERE video_id=?", (now, video_id))
        queued += 1
    return queued


def add_unsorted_entries(con, entries, album_title=None, artwork_url=None):
    """Append playable public entries to Unsorted without duplicating video IDs."""
    ensure_unsorted_collection(con)
    next_position = con.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_item WHERE playlist_id=?", (UNSORTED_COLLECTION_ID,)).fetchone()[0]
    existing = {row["video_id"] for row in con.execute("SELECT video_id FROM playlist_item WHERE playlist_id=?", (UNSORTED_COLLECTION_ID,))}
    added = []
    now = utcnow()
    for item in entries or []:
        video_id = item.get("videoId") or item.get("id")
        if not video_id or video_id in existing:
            continue
        thumbnails = item.get("thumbnails") or []
        item_artwork = thumbnails[-1].get("url") if thumbnails else item.get("thumbnail")
        title = item.get("title") or "Untitled track"
        artist = artist_from_metadata(item)
        duration = item.get("duration")
        if not isinstance(duration, str) or not re.fullmatch(r"\d+:\d{2}(?::\d{2})?", duration):
            duration = human_duration(duration)
        con.execute("""INSERT INTO track (video_id, title, artist, album, duration, artwork_url, local_status, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, 'missing', ?)
                       ON CONFLICT(video_id) DO UPDATE SET title=excluded.title, artist=excluded.artist,
                       album=COALESCE(excluded.album, track.album), duration=COALESCE(excluded.duration, track.duration),
                       artwork_url=COALESCE(excluded.artwork_url, track.artwork_url), updated_at=excluded.updated_at""",
                    (video_id, title, artist, album_title or item.get("album"), duration, item_artwork or artwork_url, now))
        con.execute("INSERT INTO playlist_item (playlist_id, position, video_id) VALUES (?, ?, ?)",
                    (UNSORTED_COLLECTION_ID, next_position, video_id))
        existing.add(video_id)
        added.append(video_id)
        next_position += 1
    if added:
        con.execute("UPDATE playlist SET updated_at=? WHERE id=?", (now, UNSORTED_COLLECTION_ID))
    return added


def import_to_unsorted(payload):
    source_kind, source_id = require_import_source(str(payload.get("url", "")))
    entries, album_title, artwork = [], None, None
    if source_kind == "playlist":
        playlist_url = "https://www.youtube.com/playlist?list=" + source_id
        music_payload = None
        if YTMusic:
            try:
                music_payload = YTMusic().get_playlist(source_id, limit=None)
            except Exception:
                music_payload = None
        if music_payload:
            entries = music_payload.get("tracks") or []
            album_title = music_payload.get("title")
            thumbs = music_payload.get("thumbnails") or []
            artwork = thumbs[-1].get("url") if thumbs else None
        else:
            metadata = ytdlp_public_json(playlist_url)
            entries = ytdlp_public_entries(playlist_url)
            album_title = metadata.get("title")
            artwork = metadata.get("thumbnail")
    else:
        if not YTMusic:
            raise WorkerError("Album import requires the bundled YouTube Music metadata provider.")
        try:
            album = YTMusic().get_album(source_id)
        except Exception as exc:
            raise WorkerError("Could not read that public YouTube Music album: " + str(exc))
        entries = album.get("tracks") or []
        album_title = album.get("title") or "Imported album"
        thumbs = album.get("thumbnails") or []
        artwork = thumbs[-1].get("url") if thumbs else None
    if not entries:
        raise WorkerError("That public source did not expose any playable tracks.")
    con = connect()
    try:
        added = add_unsorted_entries(con, entries, album_title, artwork)
        if payload.get("queue", True):
            queue_video_ids(con, added)
        con.commit()
    finally:
        con.close()
    return dashboard()


def delete_library_collection(payload):
    collection_id = str(payload.get("collection_id", ""))
    if collection_id == UNSORTED_COLLECTION_ID:
        raise WorkerError("Unsorted is a protected system collection and cannot be removed.")
    con = connect()
    try:
        collection = con.execute("SELECT kind FROM playlist WHERE id=?", (collection_id,)).fetchone()
        if not collection:
            raise WorkerError("Library collection was not found.")
        if collection["kind"] != "collection":
            raise WorkerError("This library collection cannot be removed.")
        con.execute("DELETE FROM playlist WHERE id=?", (collection_id,))
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
        if track["local_status"] == "unavailable" or video_id.startswith(("unavailable:", "local:")):
            raise WorkerError("This public playlist entry has no playable video ID.")
        queue_video_ids(con, [video_id])
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
        queue_video_ids(con, [track["video_id"] for track in tracks], missing_only)
        con.commit()
    finally:
        con.close()
    return dashboard()


def classify_error(message):
    lowered = message.lower()
    if "429" in lowered or "too many requests" in lowered:
        return "rate_limited", "Rate limited; queue paused for review."
    if "proof of origin" in lowered or "po token" in lowered or "sign in to confirm" in lowered or "bot" in lowered:
        return "proof_of_origin", "YouTube requested proof-of-origin or a bot check. Reconnect or retry later."
    if "private" in lowered:
        return "private", "This item is private or restricted."
    if "not available" in lowered or "unavailable" in lowered:
        return "unavailable", "This item is unavailable in the current region or was removed."
    return "download_failed", message[-300:] or "The downloader did not provide a reason."


def storage_guard():
    if not music_folder_available():
        raise WorkerError("Reconnect the drive holding your Music folder before downloading.")
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
    result = subprocess.run(ytdlp_command(["--no-playlist", "--skip-download", "--no-warnings", "--print-json",
                                            "https://www.youtube.com/watch?v=" + video_id]), capture_output=True, text=True, timeout=180)
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


def run_download(track, session=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(track["video_id"])):
        raise WorkerError("This track has an invalid video ID. Refresh its playlist before downloading.")
    storage_guard()
    deps = dependency_health()
    if not deps["yt_dlp"].get("path"):
        raise WorkerError("yt-dlp is still being set up. Check Settings and retry shortly.")
    work = app_data() / "downloads" / track["video_id"]
    work.mkdir(parents=True, exist_ok=True)
    template = str(work / "source.%(ext)s")
    url = "https://www.youtube.com/watch?v=" + track["video_id"]
    command = ytdlp_command([
        "--no-playlist", "--continue", "--retries", "3", "--fragment-retries", "3",
        "--sleep-interval", "1", "--max-sleep-interval", "4", "--no-warnings", "--print-json", "--embed-metadata",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-f", "bestaudio[ext=m4a]/bestaudio", "-o", template, url,
    ])
    if session is None:
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise WorkerError(result.stderr or result.stdout)
        info = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
    else:
        from .downloads import authenticated_source
        info = authenticated_source(url, template, session, deps)
    media_extensions = {"m4a", "aac", "opus", "ogg", "webm", "mp3", "wav"}
    sources = [item for item in work.iterdir() if item.is_file() and item.suffix.lower().lstrip(".") in media_extensions and not item.name.endswith(".part")]
    if not sources:
        raise WorkerError("yt-dlp reported success but did not create a media file.")
    source = max(sources, key=lambda item: item.stat().st_mtime)
    ext = source.suffix.lower().lstrip(".")
    ffmpeg = deps["ffmpeg"].get("path")
    direct = ext in ("m4a", "aac")
    metadata = resolved_track_metadata(track, info)
    target_track = {**dict(track), **metadata}
    artwork = prepare_artwork(work, ffmpeg)
    destination = build_output_path(target_track, "m4a" if direct else "mp3")
    # Every file is finished under a hidden name and renamed into place, so other apps never see it half-written.
    staged = staging_path(destination)
    cover = destination.with_suffix(".jpg")
    staged_cover = staging_path(cover)
    try:
        if direct:
            embedded = None
            if artwork and ffmpeg:
                embedded = subprocess.run([ffmpeg, "-y", "-i", str(source), "-i", str(artwork), "-map", "0:a", "-map", "1:v",
                                            "-c:a", "copy", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic",
                                            "-metadata", "title=" + metadata["title"], "-metadata", "artist=" + metadata["artist"], str(staged)], capture_output=True, text=True, timeout=600)
            if embedded is None or embedded.returncode != 0:
                staged.unlink(missing_ok=True)
                shutil.move(str(source), str(staged))
            codec = ext
        else:
            if not ffmpeg:
                raise WorkerError("The source is not an approved direct M4A/AAC file and ffmpeg is unavailable for MP3 fallback.")
            command = [ffmpeg, "-y", "-i", str(source)]
            if artwork:
                command += ["-i", str(artwork), "-map", "0:a", "-map", "1:v", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
            else:
                command += ["-vn"]
            command += ["-c:a", "libmp3lame", "-b:a", "320k", "-metadata", "title=" + metadata["title"], "-metadata", "artist=" + metadata["artist"], str(staged)]
            converted = subprocess.run(command, capture_output=True, text=True, timeout=1800)
            if converted.returncode != 0:
                raise WorkerError(converted.stderr[-500:])
            codec = "mp3-320-cbr"
        if staged.stat().st_size < 1024:
            raise WorkerError("Downloaded file was implausibly small and was removed.")
        digest = checksum(staged)
        if artwork and artwork.is_file():
            shutil.copy2(artwork, staged_cover)
            os.replace(staged_cover, cover)
        os.replace(staged, destination)
    except BaseException:
        staged.unlink(missing_ok=True)
        staged_cover.unlink(missing_ok=True)
        raise
    if not direct:
        source.unlink(missing_ok=True)
    return destination, codec, digest, metadata


def run_queue(_payload=None, session=None):
    con = connect()
    completed, total = 0, con.execute("SELECT COUNT(*) FROM download_job WHERE state IN ('queued','retry')").fetchone()[0]
    write_activity("Downloading", 0, total)
    try:
        con.execute("DELETE FROM setting WHERE key='queue_pause_reason'")
        con.commit()
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
                destination, codec, digest, metadata = run_download(job, session=session) if session else run_download(job)
                cover = destination.with_suffix(".jpg")
                artwork_url = cover.resolve().as_uri() if cover.is_file() else None
                stat = destination.stat()
                con.execute("""UPDATE track SET title=?, artist=?, album=?, local_status='ready', media_path=?, source_codec=?, checksum=?,
                               media_size=?, media_mtime_ns=?, artwork_url=COALESCE(?, artwork_url), updated_at=? WHERE video_id=?""",
                            (metadata["title"], metadata["artist"], metadata["album"], str(destination), codec, digest,
                             stat.st_size, stat.st_mtime_ns, artwork_url, utcnow(), job["video_id"]))
                con.execute("UPDATE download_job SET state='completed', error_code=NULL, error_message=NULL, updated_at=? WHERE id=?", (utcnow(), job["id"]))
            except Exception as exc:
                code, message = classify_error(str(exc))
                con.execute("UPDATE track SET local_status='failed', updated_at=? WHERE video_id=?", (utcnow(), job["video_id"]))
                con.execute("UPDATE download_job SET state='failed', error_code=?, error_message=?, updated_at=? WHERE id=?", (code, message, utcnow(), job["id"]))
                if code in ("rate_limited", "proof_of_origin"):
                    con.execute("INSERT OR REPLACE INTO setting VALUES ('queue_pause_reason', ?)", (message,))
                    con.commit()
                    break
            con.commit()
            refresh_library_manifest(con)
            completed += 1
            write_activity("Downloading", completed, total)
    finally:
        con.close()
        clear_activity()
    return dashboard()


def repair_library_metadata(_payload=None):
    con = connect()
    try:
        tracks = con.execute("SELECT * FROM track WHERE local_status='ready' AND video_id NOT LIKE 'local:%' AND lower(artist) IN ('unknown artist','unknown') ORDER BY updated_at").fetchall()
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
    if not music_folder_available():
        raise WorkerError("Reconnect your Music folder before resetting the library.")
    masters = library_root()
    temporary = app_data() / "downloads"
    con = connect()
    try:
        protected = {Path(row[0]).resolve() for row in con.execute(
            "SELECT media_path FROM track WHERE video_id LIKE 'local:%' AND media_path IS NOT NULL")}
    finally:
        con.close()
    write_activity("Clearing library", 0, 2)
    for index, target in enumerate((masters, temporary), 1):
        if target.exists():
            if any(path.is_relative_to(target.resolve()) for path in protected):
                for directory, folders, files in os.walk(target, topdown=False):
                    for name in files:
                        path = Path(directory) / name
                        if path.resolve() not in protected:
                            path.unlink()
                    for name in folders:
                        path = Path(directory) / name
                        if path.is_symlink():
                            path.unlink()
                        elif not any(path.iterdir()):
                            path.rmdir()
            else:
                shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        write_activity("Clearing library", index, 2)
    con = connect()
    try:
        con.execute("DELETE FROM download_job")
        con.execute("DELETE FROM playlist_item")
        con.execute("DELETE FROM track")
        con.execute("DELETE FROM playlist")
        con.execute("DELETE FROM setting WHERE key IN ('last_sync_notice', 'queue_pause_reason')")
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
        con.execute("DELETE FROM setting WHERE key='queue_pause_reason'")
        con.commit()
    finally:
        con.close()
    return dashboard()


def set_loaded_playlist(payload):
    playlist_id = str(payload.get("playlist_id", ""))
    con = connect()
    try:
        collection = con.execute("SELECT kind FROM playlist WHERE id=?", (playlist_id,)).fetchone()
        if collection and collection["kind"] == "unsorted":
            raise WorkerError("Unsorted is not a device playlist.")
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
                         JOIN track t ON t.video_id=i.video_id WHERE p.loaded=1 AND p.kind!='unsorted' ORDER BY p.title COLLATE NOCASE, i.position""").fetchall()
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
    if not mount.is_absolute():
        raise WorkerError("Choose a device folder before previewing or syncing.")
    if (mount / APP_NAME).is_symlink():
        raise WorkerError("The device's managed folder is a symbolic link. Choose a different folder.")
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
        (stage / "Playlists").mkdir(parents=True)
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
        manifest = {"version": 1, "updated_at": utcnow(), "entries": [{key: entry[key] for key in ("relative", "checksum", "playlist", "position", "title", "artist")} for entry in desired]}
        pending_manifest = stage / "manifest.json"
        pending_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        (root / ".mp3-maker-device.json").write_text(json.dumps({"app": APP_NAME, "created_at": utcnow()}, indent=2))
        if playlists_dir.exists():
            playlists_dir.rename(backup)
        try:
            staged_playlists.rename(playlists_dir)
            pending_manifest.replace(root / "manifest.json")
        except OSError:
            if playlists_dir.exists():
                shutil.rmtree(playlists_dir)
            if backup.exists():
                backup.rename(playlists_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        journal.unlink(missing_ok=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return sync_preview(payload)


OPERATIONS = {"dashboard": dashboard, "health_check": health_check, "bootstrap_dependencies": bootstrap_dependencies, "import_public_profile": import_public_profile,
              "set_music_folder": set_music_folder, "remove_download": remove_download,
              "import_playlist_url": import_playlist_url, "import_to_unsorted": import_to_unsorted,
              "seed_demo": seed_demo, "queue_track": queue_track, "queue_playlist": queue_playlist,
              "run_queue": run_queue, "repair_library_metadata": repair_library_metadata, "reset_and_resync_library": reset_and_resync_library,
              "cancel_job": cancel_job, "retry_job": retry_job, "delete_library_collection": delete_library_collection,
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
