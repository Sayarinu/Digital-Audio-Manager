"""Screen sampling support for the appearance color picker."""

from PySide6.QtCore import QObject, QPoint, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication


class ColorSampler(QObject):
    colorPicked = Signal(str)
    pickFailed = Signal(str)

    @Property("QVariantMap", constant=True)
    def virtualGeometry(self):
        screen = QGuiApplication.primaryScreen()
        geometry = screen.virtualGeometry() if screen else None
        if geometry is None:
            return {"x": 0, "y": 0, "width": 1, "height": 1}
        return {"x": geometry.x(), "y": geometry.y(), "width": geometry.width(), "height": geometry.height()}

    @Slot(int, int)
    def sampleAt(self, x, y):
        QTimer.singleShot(100, lambda: self._capture(x, y))

    def _capture(self, x, y):
        screen = QGuiApplication.screenAt(QPoint(x, y))
        if screen is None:
            self.pickFailed.emit("That screen area is unavailable for color sampling.")
            return
        geometry = screen.geometry()
        pixel = screen.grabWindow(0, x - geometry.x(), y - geometry.y(), 1, 1).toImage()
        if pixel.isNull():
            self.pickFailed.emit("Screen color sampling is unavailable on this display.")
            return
        self.colorPicked.emit(pixel.pixelColor(0, 0).name())
