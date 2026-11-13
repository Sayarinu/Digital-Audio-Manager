from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtMultimedia import QMediaPlayer

from dam.player import Player


class Output:
    def setVolume(self, value):
        self.volume = value


class Media(QObject):
    playbackStateChanged = Signal()
    positionChanged = Signal()
    durationChanged = Signal()
    mediaStatusChanged = Signal(object)
    errorOccurred = Signal(object, str)

    def __init__(self):
        super().__init__()
        self.state = QMediaPlayer.PlaybackState.StoppedState
        self.offset = 0

    def setAudioOutput(self, output):
        self.output = output

    def setSource(self, url):
        self.url = url
        self.offset = 0

    def play(self):
        self.state = QMediaPlayer.PlaybackState.PlayingState
        self.playbackStateChanged.emit()

    def pause(self):
        self.state = QMediaPlayer.PlaybackState.PausedState
        self.playbackStateChanged.emit()

    def stop(self):
        self.state = QMediaPlayer.PlaybackState.StoppedState
        self.playbackStateChanged.emit()

    def playbackState(self):
        return self.state

    def duration(self):
        return 20000

    def position(self):
        return self.offset

    def setPosition(self, position):
        self.offset = position
        self.positionChanged.emit()


def test_local_playback_controls_artwork_and_end_of_track(tmp_path):
    _app = QCoreApplication.instance() or QCoreApplication([])
    media, output = Media(), Output()
    player = Player(tmp_path / 'settings.ini', media=media, output=output)
    rows = []
    for i in range(2):
        path = tmp_path / f'{i}.wav'
        path.write_bytes(b'fixture')
        rows.append(dict(video_id=str(i), media_path=str(path), local_status='ready', artwork_url=f'cover{i}'))
    player.play_rows(rows, '0')
    assert media.url.isLocalFile() and player.playing
    assert player.track['artwork_url'] == 'cover0'
    player.toggle()
    assert not player.playing
    player.toggle()
    player.seek(999)
    assert player.position == 20
    player.previous()
    assert player.position == 0
    media.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)
    assert player.track['video_id'] == '1' and player.playing
    player.setVolume(.3)
    assert output.volume == .3
    player.close()
    assert not player.playing
    lazy = Player(tmp_path / 'settings.ini')
    assert lazy.media is None and lazy.volume == .3
    lazy.close()


def test_missing_file_reports_error_without_opening_audio_device(tmp_path):
    _app = QCoreApplication.instance() or QCoreApplication([])
    player = Player(tmp_path / 'settings.ini')
    player.play_rows([dict(video_id='local:missing', media_path=str(tmp_path / 'missing.wav'), local_status='ready')], 'local:missing')
    assert player.media is None
    assert 'Reconnect' in player.message
    player.close()
