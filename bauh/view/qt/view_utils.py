from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap

from bauh.view.util import resource


def load_icon(path: str, width: int, height: int = None) -> QIcon:
    return QIcon(QPixmap(path).scaled(width, height if height else width, Qt.KeepAspectRatio, Qt.SmoothTransformation))


def load_resource_icon(path: str, width: int, height: int = None) -> QIcon:
    return load_icon(resource.get_path(path), width, height)

