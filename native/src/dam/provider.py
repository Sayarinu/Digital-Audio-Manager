"""Private process protocol. Secrets and provider errors never cross into QML."""

import contextlib
import json
from pathlib import Path
import sys

from . import engine
from .account.auth import AuthError, AuthService
from .account.credentials import CredentialError
from .account.session import SessionError
from .util import session_rejected


def import_account_library(service):
    catalog = service.catalog()
    playlists = catalog.get_library_playlists(limit=None)
    # Resolve before opening a write transaction: a failed refresh preserves the previous snapshot.
    snapshots = []
    try:
        for index, playlist in enumerate(playlists):
            engine.write_activity("Reading your playlists", index, len(playlists))
            identifier = playlist.get("playlistId")
            if identifier:
                snapshots.append((identifier, catalog.get_playlist(identifier, limit=None)))
        con = engine.connect()
        try:
            with con:
                for identifier, collection in snapshots:
                    engine.store_playlist(con, identifier, collection.get("title") or "Playlist",
                                          collection.get("tracks") or [], source="YouTube Music account")
        finally:
            con.close()
    finally:
        engine.clear_activity()
    return engine.dashboard()


def initialize():
    con = engine.connect()
    try:
        with con:
            con.execute("UPDATE download_job SET state='retry' WHERE state='running'")
            con.execute("UPDATE track SET local_status='queued' WHERE local_status='downloading'")
            for row in con.execute("SELECT video_id, media_path FROM track WHERE local_status='ready' AND media_path IS NOT NULL AND COALESCE(artwork_url, '') NOT LIKE 'file:%'").fetchall():
                cover = Path(row["media_path"]).with_suffix(".jpg")
                if cover.is_file():
                    con.execute("UPDATE track SET artwork_url=? WHERE video_id=?", (cover.resolve().as_uri(), row["video_id"]))
    finally:
        con.close()
    engine.clear_activity()
    return engine.dashboard()


def perform(service, operation, payload, progress=None):
    if operation == "maintenance":
        from .updates.maintenance import perform as maintain
        return maintain(payload, progress=progress)
    if operation == "search_music":
        from .catalog import search_music
        return search_music(payload)
    if operation == "queue_search_track":
        from .catalog import queue_search_track
        return queue_search_track(payload)
    if operation == "import_local_files":
        from .local_music import import_files
        return import_files(payload)
    if operation == "restore":
        return service.restore()
    if operation == "import_session":
        return service.import_session(payload["path"])
    if operation == "import_browser":
        return service.import_browser(payload.get("browsers", []))
    if operation == "verify_session":
        return service.verify()
    if operation == "sign_out":
        return service.sign_out()
    if operation == "import_account_library":
        return import_account_library(service)
    if operation == "initialize":
        return initialize()
    if operation == "run_queue" and payload.get("authenticated"):
        service.restore()
        service.verify()
        return engine.run_queue(payload, session=service.session)
    if operation in engine.OPERATIONS and operation != "seed_demo":
        return engine.OPERATIONS[operation](payload)
    raise engine.WorkerError("This operation is unavailable. Restart the app and retry.")


def error_result(error):
    if session_rejected(error):
        return {"code": "reconnect", "message": "Your YouTube Music session expired. Reconnect in Settings."}
    if isinstance(error, (AuthError, CredentialError, SessionError)):
        return {"code": type(error).__name__, "message": str(error)}
    if isinstance(error, engine.WorkerError):
        return {"code": "operation_failed", "message": str(error)}
    return {"code": "provider_error", "message": "Could not complete this request. Check your connection, storage and tools, then retry."}


def main():
    service = AuthService()
    output = sys.stdout
    for line in sys.stdin:
        identifier = None
        try:
            request = json.loads(line)
            identifier = request["id"]
            # Libraries sometimes print diagnostics; this process has no log of provider output.
            with contextlib.redirect_stdout(None), contextlib.redirect_stderr(None):
                def progress(value):
                    output.write(json.dumps({"id": identifier, "progress": value}) + "\n")
                    output.flush()
                result = perform(service, request["operation"], request.get("payload") or {}, progress)
            response = {"id": identifier, "ok": True, "result": result}
        except Exception as error:
            response = {"id": identifier, "ok": False, "error": error_result(error)}
        output.write(json.dumps(response, ensure_ascii=False) + "\n")
        output.flush()
    return 0
