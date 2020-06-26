from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QWidget, QApplication

from bauh.view.util import resource


def centralize(widget: QWidget):
    geo = widget.frameGeometry()
    screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
    center_point = QApplication.desktop().screenGeometry(screen).center()
    geo.moveCenter(center_point)
    widget.move(geo.topLeft())


def load_icon(path: str, width: int, height: int = None) -> QIcon:
    return QIcon(QPixmap(path).scaled(width, height if height else width, Qt.KeepAspectRatio, Qt.SmoothTransformation))


def load_resource_icon(path: str, width: int, height: int = None) -> QIcon:
    return load_icon(resource.get_path(path), width, height)
