import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from dam import engine, paths, provider
from dam.account.credentials import SERVICE
from dam.account.session import from_headers
from dam.downloads import authenticated_source


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv("MP3_MAKER_APP_DATA", str(tmp_path / "state"))
    monkeypatch.delenv("MP3_MAKER_LIBRARY", raising=False)
    monkeypatch.setattr(paths, "default_library", lambda: tmp_path / "Music" / engine.APP_NAME / "Library")
    return tmp_path


def test_existing_catalog_precedes_new_platform_path(tmp_path, monkeypatch):
    monkeypatch.delenv("MP3_MAKER_APP_DATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(paths, "standard_location", lambda kind: tmp_path / kind)
    assert paths.data_directory() == tmp_path / "GenericDataLocation" / engine.APP_NAME
    previous = tmp_path / "Library/Application Support/MP3 Maker"
    previous.mkdir(parents=True)
    (previous / "mp3-maker.sqlite3").touch()
    assert paths.data_directory() == previous


def test_standard_music_directory_and_legacy_library_are_respected(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(paths, "standard_location", lambda kind: tmp_path / "Localized Music")
    assert paths.default_library() == tmp_path / "Localized Music" / engine.APP_NAME / "Library"
    old = tmp_path / "Music/MP3 Maker/Library"
    old.mkdir(parents=True)
    assert paths.default_library() == old


def test_new_music_location_preserves_downloads_and_persists(library):
    engine.seed_demo()
    previous = engine.library_root() / "existing.m4a"
    previous.write_bytes(b"existing audio")
    con = engine.connect()
    with con:
        con.execute("UPDATE track SET media_path=?, local_status='ready' WHERE video_id='demo_fog'", (str(previous),))
    con.close()
    music = library / "Removable Music"
    music.mkdir()
    result = engine.set_music_folder({"path": str(music)})
    expected = music / engine.APP_NAME / "Library"
    assert result["health"]["library_root"] == str(expected)
    assert engine.library_root() == expected
    assert previous.read_bytes() == b"existing audio"
    assert any(t["media_path"] == str(previous) for t in result["tracks"])
    assert engine.set_music_folder({"path": str(expected)})["health"]["library_root"] == str(expected)


def test_folder_selection_respects_explicit_environment_override(library, monkeypatch):
    monkeypatch.setenv("MP3_MAKER_LIBRARY", str(library / "fixed"))
    with pytest.raises(engine.WorkerError, match="MP3_MAKER_LIBRARY"):
        engine.set_music_folder({"path": str(library)})


def test_missing_or_relative_music_location_is_refused(library):
    for value in ("", "relative", str(library / "disconnected")):
        with pytest.raises(engine.WorkerError):
            engine.set_music_folder({"path": value})


def test_queue_recovery_keeps_completed_files(library):
    engine.seed_demo()
    engine.queue_track({"video_id": "demo_fog"})
    con = engine.connect()
    with con:
        con.execute("UPDATE download_job SET state='running'")
        con.execute("UPDATE track SET local_status='downloading' WHERE video_id='demo_fog'")
    con.close()
    result = provider.initialize()
    assert result["jobs"][0]["state"] == "retry"
    assert next(t for t in result["tracks"] if t["video_id"] == "demo_fog")["local_status"] == "queued"


def test_account_sync_failure_preserves_previous_collections(library):
    engine.seed_demo()
    before = engine.dashboard()["playlists"]
    catalog = Mock()
    catalog.get_library_playlists.return_value = [{"playlistId": "one"}, {"playlistId": "two"}]
    catalog.get_playlist.side_effect = [{"title": "One", "tracks": []}, RuntimeError("offline")]
    service = Mock()
    service.catalog.return_value = catalog
    with pytest.raises(RuntimeError):
        provider.import_account_library(service)
    assert engine.dashboard()["playlists"] == before


def test_account_playlists_preserve_duplicate_entries_and_exact_ids(library):
    catalog = Mock()
    catalog.get_library_playlists.return_value = [{"playlistId": "private"}]
    track = {"videoId": "exact-id", "title": "Track", "artists": [{"name": "Artist"}]}
    catalog.get_playlist.return_value = {"title": "My playlist", "tracks": [track, track]}
    service = Mock()
    service.catalog.return_value = catalog
    result = provider.import_account_library(service)
    assert [t["video_id"] for t in result["tracks"]] == ["exact-id", "exact-id"]
    assert result["playlists"][0]["source"] == "YouTube Music account"


def test_protocol_never_echoes_unknown_request_or_secret(monkeypatch):
    incoming = io.StringIO(json.dumps({"id": 7, "operation": "unknown", "payload": {"cookie": "secret-value"}}) + "\n")
    output = io.StringIO()
    monkeypatch.setattr("sys.stdin", incoming)
    monkeypatch.setattr("sys.stdout", output)
    provider.main()
    result = json.loads(output.getvalue())
    assert result["id"] == 7 and not result["ok"]
    assert "secret-value" not in output.getvalue()


def test_authenticated_extraction_keeps_secrets_in_memory(monkeypatch):
    from yt_dlp.cookies import YoutubeDLCookieJar

    session = from_headers({"cookie": "__Secure-3PAPISID=synthetic-secret"})
    downloader = Mock()
    downloader.cookiejar = YoutubeDLCookieJar()
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    downloader.extract_info.return_value = {"id": "exact"}
    constructor = Mock(return_value=downloader)
    monkeypatch.setattr("yt_dlp.YoutubeDL", constructor)
    assert authenticated_source("https://www.youtube.com/watch?v=exact", "source.%(ext)s", session, {}) == {"id": "exact"}
    assert "synthetic-secret" not in repr(constructor.call_args)
    assert next(iter(downloader.cookiejar)).value == "synthetic-secret"
    downloader.extract_info.side_effect = RuntimeError("signed-url synthetic-secret")
    with pytest.raises(engine.WorkerError) as error:
        authenticated_source("https://www.youtube.com/watch?v=exact", "source.%(ext)s", session, {})
    assert "synthetic-secret" not in str(error.value)
    downloader.extract_info.side_effect = RuntimeError("HTTP 429 signed-url synthetic-secret")
    with pytest.raises(engine.WorkerError) as error:
        authenticated_source("https://www.youtube.com/watch?v=exact", "source.%(ext)s", session, {})
    assert engine.classify_error(str(error.value))[0] == "rate_limited"
    assert "synthetic-secret" not in str(error.value)
    assert SERVICE != "studio.nouvellelune.tubify"


def test_authenticated_extractor_retains_real_downloader_cookie_interface(monkeypatch):
    from yt_dlp import YoutubeDL
    from yt_dlp.cookies import YoutubeDLCookieJar
    from yt_dlp.extractor.youtube import YoutubeIE

    session = from_headers({"cookie": "__Secure-3PAPISID=synthetic-session"})
    def extract(downloader, url, download):
        assert download is True
        assert isinstance(downloader.cookiejar, YoutubeDLCookieJar)
        cookies = YoutubeIE(downloader)._get_cookies(url)
        assert cookies['__Secure-3PAPISID'].value == 'synthetic-session'
        assert downloader.cookiejar.get_cookies_for_url(url)
        assert not downloader.cookiejar.get_cookie_header('https://example.org/')
        assert downloader.params.get('cookiefile') is None
        assert downloader.params.get('cookiesfrombrowser') is None
        next(iter(downloader.cookiejar)).value = 'rotated-in-downloader'
        return {'id': 'abcdefghijk'}

    monkeypatch.setattr(YoutubeDL, 'extract_info', extract)
    assert authenticated_source('https://www.youtube.com/watch?v=abcdefghijk',
                                'source.%(ext)s', session, {}) == {'id': 'abcdefghijk'}
    assert session.cookies[0].value == 'synthetic-session'


def test_empty_device_snapshot_is_valid_and_never_touches_other_files(library, monkeypatch):
    mount = library / "device"
    mount.mkdir()
    unrelated = mount / "keep.txt"
    unrelated.write_text("keep")
    monkeypatch.setattr(engine, "dependency_health", lambda: {"ffmpeg": {"path": "unused"}})
    result = engine.sync_apply({"mount_path": str(mount)})
    assert result["physical_files_after"] == 0
    assert unrelated.read_text() == "keep"
    assert (mount / engine.APP_NAME / "Playlists").is_dir()


def test_device_sync_rejects_missing_destination(library):
    with pytest.raises(engine.WorkerError):
        engine.sync_preview({})


def test_download_rejects_untrusted_video_id_before_touching_storage(library):
    with pytest.raises(engine.WorkerError, match="invalid video ID"):
        engine.run_download({"video_id": "../../outside"})
    assert not (library / "outside").exists()


def test_disconnected_music_folder_does_not_block_catalog_or_get_recreated(library):
    engine.seed_demo()
    music = library / "removable"
    music.mkdir()
    engine.set_music_folder({"path": str(music)})
    music.rename(library / "disconnected")
    result = engine.dashboard()
    assert result["playlists"]
    assert result["health"]["storage_available"] is False
    assert not music.exists()
    with pytest.raises(engine.WorkerError, match="Reconnect"):
        engine.storage_guard()
    with pytest.raises(engine.WorkerError, match="Reconnect"):
        engine.reset_and_resync_library()


def test_failed_manifest_swap_restores_previous_device_library(library, monkeypatch):
    mount = library / "device"
    root = mount / engine.APP_NAME
    previous = root / "Playlists"
    previous.mkdir(parents=True)
    (previous / "keep.m4a").write_bytes(b"previous export")
    (root / "manifest.json").write_text('{"entries": []}')
    monkeypatch.setattr(engine, "dependency_health", lambda: {"ffmpeg": {"path": "unused"}})
    original = Path.replace

    def fail_manifest(path, target):
        if path.name == "manifest.json":
            raise OSError("disk disconnected")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", fail_manifest)
    with pytest.raises(OSError):
        engine.sync_apply({"mount_path": str(mount)})
    assert (previous / "keep.m4a").read_bytes() == b"previous export"
    assert json.loads((root / "manifest.json").read_text()) == {"entries": []}
    assert not list(root.glob(".staging-*"))
