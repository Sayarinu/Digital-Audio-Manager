import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_queue_deduplicates_exact_video_id(self):
        worker.seed_demo()
        worker.queue_track({"video_id": "demo_fog"})
        worker.queue_track({"video_id": "demo_fog"})
        state = worker.dashboard()
        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["video_id"], "demo_fog")

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
