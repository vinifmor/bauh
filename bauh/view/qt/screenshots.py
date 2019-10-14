from typing import List

from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QDialog, QLabel, QGridLayout, QPushButton

from bauh.api.abstract.cache import MemoryCache
from bauh.view.qt import qt_utils
from bauh.view.qt.view_model import PackageView


class ScreenshotsDialog(QDialog):

    def __init__(self, pkg: PackageView, icon_cache: MemoryCache, i18n: dict, screenshots: List[QPixmap]):
        super(ScreenshotsDialog, self).__init__()
        self.setWindowTitle(str(pkg))
        self.screenshots = screenshots
        self.resize(1280, 720)
        self.i18n = i18n

        icon_data = icon_cache.get(pkg.model.icon_url)

        if icon_data and icon_data.get('icon'):
            self.setWindowIcon(icon_data.get('icon'))
        else:
            self.setWindowIcon(QIcon(pkg.model.get_type_icon_path()))

        self.grid = QGridLayout()
        self.setLayout(self.grid)
        self.bt_back = QPushButton(self.i18n['screenshots.bt_back.label'].capitalize())
        self.bt_back.clicked.connect(self.back)
        self.bt_next = QPushButton(self.i18n['screenshots.bt_next.label'].capitalize())
        self.bt_next.clicked.connect(self.next)

        self.grid.addWidget(self.bt_back, 0, 0)
        self.grid.addWidget(self.bt_next, 0, 2)

        self.img = QLabel()
        self.layout().addWidget(self.img, 1, 1)

        self.idx = 0
        self._load_img()

    def _load_img(self):
        pixmap = self.screenshots[self.idx]
        self.img.setPixmap(pixmap)

        if len(self.screenshots) == 1:
            self.bt_back.setVisible(False)
            self.bt_next.setVisible(False)
        else:
            self.bt_back.setVisible(self.idx != 0)
            self.bt_next.setVisible(self.idx != len(self.screenshots) - 1)

        self.adjustSize()
        qt_utils.centralize(self)

    def back(self):
        self.idx -= 1
        self._load_img()

    def next(self):
        self.idx += 1
        self._load_img()


