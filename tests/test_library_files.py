import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native" / "src"))
from dam import engine as worker  # noqa: E402

VIDEO_ID = "abcdefghijk"
DEPENDENCIES = {"yt_dlp": {"path": "/tools/yt-dlp"}, "ffmpeg": {"path": "/tools/ffmpeg"}, "node": {}}


class LibraryFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="dam-library-test-"))
        os.environ["MP3_MAKER_APP_DATA"] = str(self.temp / "data")
        os.environ["MP3_MAKER_LIBRARY"] = str(self.temp / "library")
        self.library = self.temp / "library"
        self.library.mkdir()

    def tearDown(self):
        os.environ.pop("MP3_MAKER_APP_DATA", None)
        os.environ.pop("MP3_MAKER_LIBRARY", None)
        shutil.rmtree(self.temp)

    def add_track(self, video_id, path, playlist=None, position=1):
        con = worker.connect()
        try:
            con.execute("""INSERT INTO track (video_id, title, artist, artwork_url, local_status, media_path, updated_at)
                           VALUES (?, 'Song', 'Artist', 'https://example.invalid/art.jpg', 'ready', ?, ?)""",
                        (video_id, str(path), worker.utcnow()))
            if playlist:
                con.execute("""INSERT OR IGNORE INTO playlist (id, title, source, remote_id, updated_at)
                               VALUES (?, ?, 'Public YouTube Music', 'PL1', ?)""", (playlist[0], playlist[1], worker.utcnow()))
                con.execute("INSERT INTO playlist_item (playlist_id, position, video_id) VALUES (?, ?, ?)",
                            (playlist[0], position, video_id))
            con.commit()
        finally:
            con.close()

    def manifest(self):
        return json.loads((self.library / "library.json").read_text(encoding="utf-8"))

    def test_manifest_lists_only_downloads_inside_the_library(self):
        song = self.library / "Artist" / "Artist — Song [{}].m4a".format(VIDEO_ID)
        song.parent.mkdir()
        song.write_bytes(b"audio" * 400)
        outside = self.temp / "elsewhere.m4a"
        outside.write_bytes(b"other")
        self.add_track(VIDEO_ID, song, ("public:PL1", "Road Trip"), 3)
        self.add_track("lmnopqrstuv", outside)
        self.add_track("local:imported", song)
        worker.dashboard()
        manifest = self.manifest()
        self.assertEqual(set(manifest), {"format", "version", "updated_at", "entries"})
        self.assertEqual((manifest["format"], manifest["version"]), ("digital-audio-manager.library", 1))
        self.assertEqual(manifest["entries"], [{
            "path": "Artist/Artist — Song [{}].m4a".format(VIDEO_ID), "videoId": VIDEO_ID,
            "sha256": hashlib.sha256(song.read_bytes()).hexdigest(), "size": song.stat().st_size,
            "playlists": [{"id": "public:PL1", "title": "Road Trip", "position": 3}],
        }])
        self.assertNotIn("http", (self.library / "library.json").read_text(encoding="utf-8"))
        self.assertEqual([path.name for path in self.library.iterdir() if path.name.startswith(".")], [])

    def test_manifest_is_rewritten_only_when_the_library_changes(self):
        song = self.library / "song.m4a"
        song.write_bytes(b"first" * 400)
        self.add_track(VIDEO_ID, song)
        worker.dashboard()
        written = self.manifest()["updated_at"]
        with patch.object(worker, "checksum", side_effect=AssertionError("unchanged files are not hashed again")):
            worker.dashboard()
        self.assertEqual(self.manifest()["updated_at"], written)
        song.write_bytes(b"second, longer" * 400)
        worker.dashboard()
        self.assertEqual(self.manifest()["entries"][0]["sha256"], hashlib.sha256(song.read_bytes()).hexdigest())
        worker.remove_download({"video_id": VIDEO_ID})
        self.assertEqual(self.manifest()["entries"], [])

    def download(self, ffmpeg_result):
        """Run a download whose yt-dlp and ffmpeg steps are simulated, recording each ffmpeg command."""
        work = self.temp / "data" / "downloads" / VIDEO_ID
        commands, seen = [], []

        def run(command, **_kwargs):
            if command[0] == "/tools/yt-dlp":
                work.mkdir(parents=True, exist_ok=True)
                (work / "source.webm").write_bytes(b"opus" * 1000)
                (work / "source.jpg").write_bytes(b"jpeg")
                return CompletedProcess(command, 0, json.dumps({"title": "Song", "artist": "Artist"}), "")
            commands.append(command)
            output = Path(command[-1])
            if "-vf" in command:
                return CompletedProcess(command, 1, "", "no artwork conversion")
            seen.append(sorted(path.name for path in output.parent.iterdir()))
            output.write_bytes(b"mp3" * 1000)
            return CompletedProcess(command, ffmpeg_result, "", "conversion failed")

        track = {"video_id": VIDEO_ID, "title": "Song", "artist": "Artist", "album": None}
        with patch.object(worker, "dependency_health", return_value=DEPENDENCIES), \
                patch.object(worker, "storage_guard"), patch.object(worker.subprocess, "run", side_effect=run):
            return worker.run_download(track), commands, seen

    def test_download_is_finished_under_a_hidden_name_then_renamed_into_place(self):
        (destination, codec, digest, _metadata), commands, seen = self.download(0)
        self.assertEqual(codec, "mp3-320-cbr")
        command = commands[-1]
        self.assertEqual(command[command.index("-disposition:v:0") + 1], "attached_pic")
        staged = Path(command[-1])
        self.assertTrue(staged.name.startswith(".") and ".partial" in staged.name)
        self.assertEqual(seen[-1], [], "the final file must not exist while ffmpeg writes")
        self.assertTrue(destination.is_file() and destination.with_suffix(".jpg").is_file())
        self.assertEqual(digest, hashlib.sha256(destination.read_bytes()).hexdigest())
        self.assertEqual(sorted(path.name for path in destination.parent.iterdir()), sorted([destination.name, destination.with_suffix(".jpg").name]))

    def test_failed_download_leaves_no_partial_or_final_file(self):
        with self.assertRaises(worker.WorkerError):
            self.download(1)
        self.assertEqual([path for path in self.library.rglob("*") if path.is_file()], [])


if __name__ == "__main__":
    unittest.main()
