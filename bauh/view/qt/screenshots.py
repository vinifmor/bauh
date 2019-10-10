from typing import List

from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout

from bauh.api.abstract.cache import MemoryCache
from bauh.view.qt.view_model import PackageView


class ScreenshotsDialog(QDialog):

    def __init__(self, pkg: PackageView, icon_cache: MemoryCache, i18n: dict, screenshots: List[QPixmap]):
        super(ScreenshotsDialog, self).__init__()
        self.setWindowTitle(str(pkg))

        icon_data = icon_cache.get(pkg.model.icon_url)

        if icon_data and icon_data.get('icon'):
            self.setWindowIcon(icon_data.get('icon'))
        else:
            self.setWindowIcon(QIcon(pkg.model.get_type_icon_path()))

        self.setLayout(QVBoxLayout())

        if screenshots:
            lb = QLabel()
            lb.setPixmap(screenshots[0])
            self.layout().addWidget(lb)

        self.adjustSize()
