import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import worker  # noqa: E402


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="mp3-maker-test-"))
        os.environ["MP3_MAKER_APP_DATA"] = str(self.temp / "data")
        os.environ["MP3_MAKER_LIBRARY"] = str(self.temp / "library")

    def tearDown(self):
        os.environ.pop("MP3_MAKER_APP_DATA", None)
        os.environ.pop("MP3_MAKER_LIBRARY", None)
        shutil.rmtree(self.temp)

    def test_filename_sanitizes_device_unsafe_characters(self):
        self.assertEqual(worker.canonical_filename(' a/b:c*?"<d>| '), "a b c d")

    def test_managed_node_archive_matches_platform_conventions(self):
        self.assertEqual(worker.node_archive_details("v22.16.0", "darwin", "arm64"),
                         ("node-v22.16.0-darwin-arm64.tar.gz", "https://nodejs.org/dist/v22.16.0/node-v22.16.0-darwin-arm64.tar.gz"))
        self.assertEqual(worker.node_archive_details("v22.16.0", "win", "x64")[0], "node-v22.16.0-win-x64.zip")

    def test_ytdlp_command_uses_managed_node_when_available(self):
        with patch.object(worker, "dependency_health", return_value={"yt_dlp": {"path": "/tools/yt-dlp"}, "node": {"path": "/tools/node"}}):
            self.assertEqual(worker.ytdlp_command(["--version"]), ["/tools/yt-dlp", "--js-runtimes", "node:/tools/node", "--version"])

    def test_bootstrap_uses_existing_managed_tools_without_network(self):
        bin_dir = self.temp / "data" / "bin"
        bin_dir.mkdir(parents=True)
        for name in ("yt-dlp", "node"):
            executable = bin_dir / name
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
        with patch.object(worker, "download_bytes", side_effect=AssertionError("should not download")):
            state = worker.bootstrap_dependencies()
        self.assertTrue(state["health"]["dependencies"]["yt_dlp"]["available"])
        self.assertTrue(state["health"]["dependencies"]["node"]["available"])

    def test_existing_library_migrates_collections_without_losing_them(self):
        data_dir = self.temp / "data"
        data_dir.mkdir()
        con = sqlite3.connect(data_dir / "mp3-maker.sqlite3")
        try:
            con.execute("""CREATE TABLE playlist (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
                remote_id TEXT, loaded INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
            )""")
            con.execute("INSERT INTO playlist VALUES ('legacy', 'Existing', 'Public', 'PL1', 0, ?)", (worker.utcnow(),))
            con.commit()
        finally:
            con.close()
        state = worker.dashboard()
        self.assertEqual(state["playlists"][0]["id"], "legacy")
        self.assertEqual(state["playlists"][0]["kind"], "collection")

    def test_artist_metadata_prefers_music_artist_lists(self):
        self.assertEqual(worker.artist_from_metadata({"artists": [{"name": "First"}, {"name": "Second"}]}), "First & Second")
        self.assertEqual(worker.artist_from_metadata({"uploader": "Exact video channel"}), "Exact video channel")

    def test_unavailable_catalog_entries_are_not_queueable(self):
        con = worker.connect()
        try:
            con.execute("INSERT INTO track (video_id, title, artist, local_status, updated_at) VALUES (?, ?, ?, ?, ?)",
                        ("unavailable:playlist:1", "Removed", "Unknown", "unavailable", worker.utcnow()))
            con.commit()
        finally:
            con.close()
        with self.assertRaises(worker.WorkerError):
            worker.queue_track({"video_id": "unavailable:playlist:1"})

    def test_playlist_url_requires_playlist_identifier(self):
        self.assertEqual(worker.require_url_playlist("https://music.youtube.com/playlist?list=PL123"), "PL123")
        with self.assertRaises(worker.WorkerError):
            worker.require_url_playlist("https://music.youtube.com/watch?v=one")

    def test_quick_import_accepts_playlists_and_music_albums(self):
        self.assertEqual(worker.require_import_source("https://music.youtube.com/playlist?list=PL123"), ("playlist", "PL123"))
        self.assertEqual(worker.require_import_source("https://music.youtube.com/browse/MPREb_example"), ("album", "MPREb_example"))
        with self.assertRaises(worker.WorkerError):
            worker.require_import_source("https://youtube.com/watch?v=one")

    def test_album_import_adds_unique_tracks_to_unsorted_and_queues_them(self):
        class FakeMusic:
            def get_album(self, browse_id):
                if browse_id != "MPREb_example":
                    raise AssertionError("unexpected browse id")
                return {"title": "Album title", "thumbnails": [{"url": "cover"}], "tracks": [
                    {"videoId": "album-one", "title": "One", "artists": [{"name": "Artist"}], "duration": "3:20"},
                    {"videoId": "album-two", "title": "Two", "artists": [{"name": "Artist"}], "duration": "4:10"},
                ]}

        with patch.object(worker, "YTMusic", FakeMusic):
            first = worker.import_to_unsorted({"url": "https://music.youtube.com/browse/MPREb_example", "queue": True})
            second = worker.import_to_unsorted({"url": "https://music.youtube.com/browse/MPREb_example", "queue": True})
        unsorted = next(item for item in first["playlists"] if item["id"] == worker.UNSORTED_COLLECTION_ID)
        self.assertEqual(unsorted["kind"], "unsorted")
        self.assertEqual(unsorted["track_count"], 2)
        self.assertEqual(len(first["jobs"]), 2)
        self.assertEqual(next(item for item in second["playlists"] if item["id"] == worker.UNSORTED_COLLECTION_ID)["track_count"], 2)
        self.assertEqual(len(second["jobs"]), 2)

    def test_profile_sync_saves_profile_url_and_skip_notice(self):
        profile = {"entries": [{"id": "PLgood", "title": "Good"}, {"id": "PLbad", "title": "Bad"}]}

        def refresh(con, url, title_hint=None):
            if url.endswith("PLbad"):
                raise worker.WorkerError("private")
            return "public:PLgood"

        with patch.object(worker, "ytdlp_public_json", return_value=profile), patch.object(worker, "refresh_public_playlist", side_effect=refresh):
            worker.import_public_profile({"url": "https://music.youtube.com/@example"})
        state = worker.dashboard()
        self.assertEqual(state["public_profile_url"], "https://music.youtube.com/@example")
        self.assertIn("Skipped 1 unreadable playlist", state["sync_notice"])

    def test_queue_deduplicates_exact_video_id(self):
        worker.seed_demo()
        worker.queue_track({"video_id": "demo_fog"})
        worker.queue_track({"video_id": "demo_fog"})
        state = worker.dashboard()
        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["video_id"], "demo_fog")

    def test_delete_collection_keeps_download_queue_and_protects_unsorted(self):
        worker.seed_demo()
        worker.queue_track({"video_id": "demo_fog"})
        media = self.temp / "library" / "saved.m4a"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"downloaded audio")
        con = worker.connect()
        try:
            con.execute("UPDATE track SET local_status='ready', media_path=? WHERE video_id='demo_tide'", (str(media),))
            con.commit()
        finally:
            con.close()
        worker.delete_library_collection({"collection_id": "demo:night-drive"})
        state = worker.dashboard()
        self.assertTrue(any(job["video_id"] == "demo_fog" for job in state["jobs"]))
        self.assertTrue(media.is_file())
        con = worker.connect()
        try:
            worker.ensure_unsorted_collection(con)
            con.commit()
        finally:
            con.close()
        with self.assertRaises(worker.WorkerError):
            worker.delete_library_collection({"collection_id": worker.UNSORTED_COLLECTION_ID})

    def test_dashboard_returns_the_full_active_queue(self):
        con = worker.connect()
        try:
            now = worker.utcnow()
            for index in range(125):
                video_id = "queued-{}".format(index)
                con.execute("INSERT INTO track (video_id, title, artist, local_status, updated_at) VALUES (?, ?, ?, 'queued', ?)",
                            (video_id, video_id, "Artist", now))
                con.execute("INSERT INTO download_job (id, video_id, state, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)",
                            ("job-{}".format(index), video_id, now, now))
            con.commit()
        finally:
            con.close()
        self.assertEqual(len(worker.dashboard()["jobs"]), 125)

    def test_sync_preview_counts_playlist_duplicates_and_missing_files(self):
        worker.seed_demo()
        state = worker.dashboard()
        con = worker.connect()
        try:
            media = self.temp / "library" / "song.mp3"
            media.parent.mkdir(parents=True, exist_ok=True)
            media.write_bytes(b"valid-enough-for-preview")
            con.execute("UPDATE track SET local_status='ready', media_path=?, checksum=? WHERE video_id='demo_fog'",
                        (str(media), worker.checksum(media)))
            con.execute("UPDATE playlist SET loaded=1 WHERE id='demo:liked'")
            con.execute("UPDATE playlist_item SET video_id='demo_fog' WHERE playlist_id='demo:liked'")
            con.commit()
        finally:
            con.close()
        preview = worker.sync_preview({"mount_path": str(self.temp / "card")})
        self.assertEqual(preview["physical_files_after"], 2)
        self.assertEqual(preview["duplicate_files"], 1)
        self.assertTrue(any("not mounted" in warning for warning in preview["warnings"]))

    def test_export_guard_is_enforced(self):
        self.assertEqual(worker.MAX_EXPORT_FILES, 8000)

    def test_reset_clears_local_files_tracks_jobs_and_collection(self):
        worker.seed_demo()
        worker.queue_track({"video_id": "demo_fog"})
        con = worker.connect()
        try:
            con.execute("INSERT INTO setting (key, value) VALUES ('public_profile_url', ?)", ("https://music.youtube.com/@example",))
            con.commit()
        finally:
            con.close()
        media = self.temp / "library" / "temporary.mp3"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"local master")
        state = worker.reset_and_resync_library()
        self.assertFalse(media.exists())
        self.assertEqual(state["tracks"], [])
        self.assertEqual(state["jobs"], [])
        self.assertEqual(state["playlists"], [])
        self.assertEqual(state["public_profile_url"], "https://music.youtube.com/@example")


if __name__ == "__main__":
    unittest.main()
