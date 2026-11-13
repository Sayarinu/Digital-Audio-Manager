"""Native playback of local audio; the catalog retains ownership of file paths."""

from pathlib import Path

from PySide6.QtCore import QObject, Property, QSettings, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class Player(QObject):
    changed = Signal()
    positionChanged = Signal()
    messageChanged = Signal()

    def __init__(self, config, parent=None, media=None, output=None):
        super().__init__(parent)
        self.settings = QSettings(str(config), QSettings.Format.IniFormat)
        self.output, self.media = output, media
        self._volume = max(0, min(1, self.settings.value('player/volume', .7, type=float)))
        self._queue, self._index, self._message = [], -1, ''
        if self.media is not None:
            self._connect_backend()

    def _connect_backend(self):
        self.media.setAudioOutput(self.output)
        self.output.setVolume(self._volume)
        self.media.playbackStateChanged.connect(self.changed)
        self.media.positionChanged.connect(self.positionChanged)
        self.media.durationChanged.connect(self.positionChanged)
        self.media.mediaStatusChanged.connect(self._status)
        self.media.errorOccurred.connect(self._error)

    def _ensure_backend(self):
        # Browsing and visual fixtures never need to initialize the system audio server.
        if self.media is None:
            self.media = QMediaPlayer(self)
            self.output = QAudioOutput(self)
            self._connect_backend()

    @Property('QVariantMap', notify=changed)
    def track(self):
        return self._queue[self._index] if 0 <= self._index < len(self._queue) else {}

    @Property(bool, notify=changed)
    def hasTrack(self):
        return bool(self.track)

    @Property(bool, notify=changed)
    def playing(self):
        return self.media is not None and self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @Property(float, notify=positionChanged)
    def position(self):
        return self.media.position() / 1000 if self.media is not None else 0.0

    @Property(float, notify=positionChanged)
    def duration(self):
        return self.media.duration() / 1000 if self.media is not None else 0.0

    @Property(float, notify=changed)
    def volume(self):
        return self._volume

    @Property(str, notify=messageChanged)
    def message(self):
        return self._message

    def play_rows(self, rows, identifier):
        queue = [dict(row) for row in rows if row.get('local_status') == 'ready' and row.get('media_path')]
        index = next((i for i, row in enumerate(queue) if row['video_id'] == identifier), None)
        if index is None:
            return
        self._queue, self._index = queue, index
        self._play_current()

    def _play_current(self):
        path = Path(self.track['media_path'])
        if not path.is_file():
            if self.media is not None:
                self.media.stop()
            self._message = 'This audio file is unavailable. Reconnect its drive or import it again.'
            self.messageChanged.emit()
            self.changed.emit()
            return
        self._message = ''
        self.messageChanged.emit()
        self._ensure_backend()
        self.media.setSource(QUrl.fromLocalFile(str(path)))
        self.media.play()
        self.changed.emit()

    @Slot()
    def toggle(self):
        if self.hasTrack and self.media is not None:
            self.media.pause() if self.playing else self.media.play()

    @Slot()
    def previous(self):
        if self.position > 3:
            self.seek(0)
        elif self._index > 0:
            self._index -= 1
            self._play_current()

    @Slot()
    def next(self):
        if self._index + 1 < len(self._queue):
            self._index += 1
            self._play_current()

    @Slot(float)
    def seek(self, seconds):
        if self.hasTrack and self.media is not None:
            self.media.setPosition(round(max(0, min(seconds, self.duration)) * 1000))

    @Slot(float)
    def setVolume(self, value):
        self._volume = max(0, min(1, value))
        if self.output is not None:
            self.output.setVolume(self._volume)
        self.changed.emit()
        self.settings.setValue('player/volume', self.volume)

    @Slot()
    def dismissMessage(self):
        self._message = ''
        self.messageChanged.emit()

    def _status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.next()

    def _error(self, error, message=''):
        if error != QMediaPlayer.Error.NoError:
            self._message = 'This audio could not be played. Check that its drive is connected and the file is playable.'
            self.messageChanged.emit()

    def close(self):
        self._queue, self._index = [], -1
        if self.media is not None:
            self.media.stop()
            self.media.setSource(QUrl())
        self.changed.emit()
        self.positionChanged.emit()
        self.settings.sync()


def decoder_smoke_test():
    """Decode generated audio without connecting to speakers or loading user data."""
    import tempfile
    import wave
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtMultimedia import QAudioBufferOutput

    app = QCoreApplication([])
    with tempfile.TemporaryDirectory(prefix='dam-decoder-') as folder:
        path = Path(folder) / 'silence.wav'
        with wave.open(str(path), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b'\0\0' * 8000)
        media, buffers = QMediaPlayer(), QAudioBufferOutput()
        media.setAudioBufferOutput(buffers)
        frames = []
        buffers.audioBufferReceived.connect(lambda buffer: frames.append(buffer.frameCount()))
        media.setSource(QUrl.fromLocalFile(str(path)))
        media.play()
        QTimer.singleShot(1800, app.quit)
        app.exec()
        success = media.duration() == 1000 and sum(frames) >= 8000
        media.stop()
        media.setSource(QUrl())
        if success:
            print('Native audio decoder passed.')
        return 0 if success else 1
