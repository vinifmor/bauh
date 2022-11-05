from typing import Optional, Union

from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QWidget, QApplication, QDesktopWidget

from bauh.view.util import resource

desktop: Optional[QDesktopWidget] = None


def centralize(widget: QWidget):
    screen_geometry = get_current_screen_geometry()
    widget.frameGeometry().moveCenter(screen_geometry.center())
    widget.move(widget.frameGeometry().topLeft())


def load_icon(path: str, width: int, height: int = None) -> QIcon:
    return QIcon(QPixmap(path).scaled(width, height if height else width, Qt.KeepAspectRatio, Qt.SmoothTransformation))


def load_resource_icon(path: str, width: int, height: int = None) -> QIcon:
    return load_icon(resource.get_path(path), width, height)


def measure_based_on_width(percent: float) -> int:
    return round(percent * QApplication.primaryScreen().size().width())


def measure_based_on_height(percent: float) -> int:
    return round(percent * QApplication.primaryScreen().size().height())


def get_current_screen_geometry(source_widget: Optional[Union[QWidget, QPoint]] = None) -> QRect:
    global desktop

    if not desktop:
        desktop = QDesktopWidget()

    current_screen_idx = desktop.screenNumber(source_widget if source_widget else desktop.cursor().pos())
    return desktop.screen(current_screen_idx).geometry()
