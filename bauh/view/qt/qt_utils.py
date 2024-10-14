from typing import Optional, Union

from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QScreen, QGuiApplication
from PyQt6.QtWidgets import QWidget, QApplication

from bauh.view.util import resource

desktop: Optional[QScreen] = None


def centralize(widget: QWidget, align_top_left: bool = True):
    widget_frame = widget.frameGeometry()
    screen_geometry = get_current_screen_geometry()
    widget_frame.moveCenter(screen_geometry.center())

    if align_top_left:
        widget.move(widget_frame.topLeft())


def load_icon(path: str, width: int, height: int = None) -> QIcon:
    return QIcon(QPixmap(path).scaled(width, height if height else width, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


def load_resource_icon(path: str, width: int, height: int = None) -> QIcon:
    return load_icon(resource.get_path(path), width, height)


def measure_based_on_width(percent: float) -> int:
    return round(percent * QApplication.primaryScreen().size().width())


def measure_based_on_height(percent: float) -> int:
    return round(percent * QApplication.primaryScreen().size().height())


def get_current_screen_geometry(source_widget: Optional[Union[QWidget, QPoint]] = None) -> QRect:
    return QGuiApplication.primaryScreen().geometry()
