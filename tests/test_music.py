import base64
from pathlib import Path
import wave
from unittest.mock import Mock

import pytest
from mutagen.id3 import APIC, TALB, TIT2, TPE1
from mutagen.wave import WAVE

from dam import catalog, engine, local_music


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv('MP3_MAKER_APP_DATA', str(tmp_path / 'state'))
    monkeypatch.setenv('MP3_MAKER_LIBRARY', str(tmp_path / 'managed'))
    return tmp_path


def make_audio(path):
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b'\0\0' * 8000)
    audio = WAVE(path)
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text='A local song'))
    audio.tags.add(TPE1(encoding=3, text='Local artist'))
    audio.tags.add(TALB(encoding=3, text='Local album'))
    art = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=')
    audio.tags.add(APIC(encoding=3, mime='image/png', type=3, desc='Cover', data=art))
    audio.save()
    return art


def test_local_import_keeps_original_audio_and_embedded_cover(library):
    original = library / 'My existing song.wav'
    artwork = make_audio(original)
    before = original.read_bytes()
    result = local_music.import_files({'paths': [str(original)]})
    track = result['tracks'][0]
    assert (track['title'], track['artist'], track['album']) == ('A local song', 'Local artist', 'Local album')
    assert track['media_path'] == str(original)
    assert track['video_id'].startswith('local:')
    from PySide6.QtCore import QUrl
    assert Path(QUrl(track['artwork_url']).toLocalFile()).read_bytes() == artwork
    assert original.read_bytes() == before
    repeated = local_music.import_files({'paths': [str(original)]})
    assert len(repeated['tracks']) == 1
    with pytest.raises(engine.WorkerError):
        engine.queue_track({'video_id': track['video_id']})
    engine.delete_library_collection({'collection_id': local_music.COLLECTION})
    assert original.read_bytes() == before


def test_folder_import_skips_bad_audio_without_losing_good_files(library):
    folder = library / 'outside'
    folder.mkdir()
    make_audio(folder / 'good.wav')
    (folder / 'bad.mp3').write_bytes(b'not audio')
    (folder / 'unrelated.txt').write_text('keep')
    result = local_music.import_files({'paths': [str(folder)]})
    assert len(result['tracks']) == 1
    assert '1 audio files' in result['notice']
    assert (folder / 'unrelated.txt').read_text() == 'keep'


def test_search_import_preserves_the_selected_video_and_deduplicates(library, monkeypatch):
    client = Mock()
    client.search.return_value = [dict(videoId='abcdefghijk', title='Exact song', artists=[{'name': 'Artist'}],
                                      album={'name': 'Album'}, duration='3:00', thumbnails=[{'url': 'https://example.org/art.jpg'}]),
                                  dict(videoId='invalid', title='Unavailable')]
    monkeypatch.setattr(engine, 'YTMusic', lambda: client)
    result = catalog.search_music({'query': 'a song'})
    client.search.assert_called_once_with('a song', filter='songs', limit=50)
    assert len(result['results']) == 1
    queued = catalog.queue_search_track({'track': result['results'][0]})
    assert queued['tracks'][0]['video_id'] == 'abcdefghijk'
    assert queued['jobs'][0]['video_id'] == 'abcdefghijk'
    assert len(catalog.queue_search_track({'track': result['results'][0]})['jobs']) == 1
    with pytest.raises(engine.WorkerError):
        catalog.queue_search_track({'track': {'video_id': '../outside'}})


def test_search_errors_are_actionable_and_do_not_echo_provider_secrets(monkeypatch):
    client = Mock()
    client.search.side_effect = RuntimeError('private server response')
    monkeypatch.setattr(engine, 'YTMusic', lambda: client)
    with pytest.raises(engine.WorkerError, match='Check your connection') as error:
        catalog.search_music({'query': 'song'})
    assert 'private' not in str(error.value)


def test_reset_preserves_imported_audio_even_inside_managed_folder(library):
    folder = engine.library_root()
    folder.mkdir(parents=True)
    imported = folder / 'already owned.wav'
    make_audio(imported)
    before = imported.read_bytes()
    local_music.import_files({'paths': [str(imported)]})
    (folder / 'temporary-download.part').write_bytes(b'partial')
    engine.reset_and_resync_library()
    assert imported.read_bytes() == before
    assert not (folder / 'temporary-download.part').exists()


def test_previous_download_uses_local_cover_offline(library):
    from dam import provider
    engine.seed_demo()
    audio = library / 'previous.m4a'
    audio.write_bytes(b'existing downloaded audio')
    cover = audio.with_suffix('.jpg')
    cover.write_bytes(b'existing cover')
    con = engine.connect()
    with con:
        con.execute("UPDATE track SET media_path=?, local_status='ready', artwork_url='https://example.org/cover' WHERE video_id='demo_fog'", (str(audio),))
    con.close()
    result = provider.initialize()
    track = next(row for row in result['tracks'] if row['video_id'] == 'demo_fog')
    assert track['artwork_url'] == cover.as_uri()


def downloaded_song(library):
    engine.seed_demo()
    audio = library / 'download.m4a'
    audio.write_bytes(b'verified downloaded audio')
    audio.with_suffix('.jpg').write_bytes(b'cover')
    con = engine.connect()
    with con:
        con.execute("UPDATE track SET media_path=?,local_status='ready',checksum='digest',artwork_url=? WHERE video_id='demo_fog'", (str(audio), audio.with_suffix('.jpg').as_uri()))
    con.close()
    return audio


def test_download_availability_follows_disk_and_reconnection(library):
    audio = downloaded_song(library)
    def song():
        return next(t for t in engine.dashboard()['tracks'] if t['video_id'] == 'demo_fog')
    assert song()['local_status'] == 'ready'
    moved = audio.with_suffix('.disconnected')
    audio.rename(moved)
    assert song()['local_status'] == 'missing'
    assert song()['media_path'] == str(audio)
    moved.rename(audio)
    assert song()['local_status'] == 'ready'
    engine.delete_library_collection({'collection_id': 'demo:night-drive'})
    assert song()['local_status'] == 'ready'


def test_remove_download_deletes_audio_cover_and_allows_redownload(library):
    audio = downloaded_song(library)
    result = engine.remove_download({'video_id': 'demo_fog'})
    song = next(t for t in result['tracks'] if t['video_id'] == 'demo_fog')
    assert not audio.exists() and not audio.with_suffix('.jpg').exists()
    assert song['local_status'] == 'missing' and song['media_path'] is None
    assert song['artwork_url'] is None
    assert engine.queue_track({'video_id': 'demo_fog'})['jobs'][0]['video_id'] == 'demo_fog'


def test_remove_download_protects_imported_originals_and_active_download(library):
    original = library / 'original.wav'
    make_audio(original)
    song = local_music.import_files({'paths': [str(original)]})['tracks'][0]
    with pytest.raises(engine.WorkerError, match='Imported originals'):
        engine.remove_download({'video_id': song['video_id']})
    assert original.exists()
    audio = downloaded_song(library)
    con = engine.connect()
    with con:
        con.execute("INSERT INTO download_job(id, video_id, state, created_at, updated_at) VALUES ('active','demo_fog','running','now','now')")
    con.close()
    with pytest.raises(engine.WorkerError, match='finish downloading'):
        engine.remove_download({'video_id': 'demo_fog'})
    assert audio.exists()


def test_missing_download_can_be_queued_without_a_prior_refresh(library):
    audio = downloaded_song(library)
    audio.unlink()
    result = engine.queue_track({'video_id': 'demo_fog'})
    assert any(job['video_id'] == 'demo_fog' and job['state'] == 'queued' for job in result['jobs'])
