import logging
from threading import Thread
from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap, QCursor
from PyQt5.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QProgressBar, QApplication, QWidget, \
    QSizePolicy, QHBoxLayout

from bauh.api.abstract.cache import MemoryCache
from bauh.api.http import HttpClient
from bauh.view.qt import qt_utils
from bauh.view.qt.components import new_spacer
from bauh.view.qt.thread import AnimateProgress
from bauh.view.qt.view_model import PackageView
from bauh.view.util.translation import I18n


class ScreenshotsDialog(QDialog):

    def __init__(self, pkg: PackageView, http_client: HttpClient, icon_cache: MemoryCache, i18n: I18n, screenshots: List[QPixmap], logger: logging.Logger):
        super(ScreenshotsDialog, self).__init__()
        self.setWindowTitle(str(pkg))
        self.screenshots = screenshots
        self.logger = logger
        self.loaded_imgs = []
        self.download_threads = []
        self.i18n = i18n
        self.http_client = http_client
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName('progress_screenshots')
        self.progress_bar.setCursor(QCursor(Qt.WaitCursor))
        self.progress_bar.setMaximumHeight(10 if QApplication.instance().style().objectName().lower() == 'windows' else 6)
        self.progress_bar.setTextVisible(False)
        self.thread_progress = AnimateProgress()
        self.thread_progress.signal_change.connect(self._update_progress)
        self.thread_progress.start()

        # THERE ARE CRASHES WITH SOME RARE ICONS ( like insomnia ). IT CAN BE A QT BUG. IN THE MEANTIME, ONLY THE TYPE ICON WILL BE RENDERED
        #
        # icon_data = icon_cache.get(pkg.model.icon_url)
        #
        # if icon_data and icon_data.get('icon'):
        #     self.setWindowIcon(icon_data.get('icon'))
        # else:
        #     self.setWindowIcon(QIcon(pkg.model.get_type_icon_path()))
        self.setWindowIcon(QIcon(pkg.model.get_type_icon_path()))
        self.setLayout(QVBoxLayout())

        self.layout().addWidget(new_spacer())
        self.img = QLabel()
        self.img.setObjectName('image')
        self.layout().addWidget(self.img)
        self.layout().addWidget(new_spacer())

        self.container_buttons = QWidget()
        self.container_buttons.setObjectName('buttons_container')
        self.container_buttons.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.container_buttons.setContentsMargins(0, 0, 0, 0)
        self.container_buttons.setLayout(QHBoxLayout())

        self.bt_back = QPushButton(' < ' + self.i18n['screenshots.bt_back.label'].capitalize())
        self.bt_back.setObjectName('back')
        self.bt_back.setProperty('control', 'true')
        self.bt_back.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_back.clicked.connect(self.back)
        self.container_buttons.layout().addWidget(self.bt_back)
        self.container_buttons.layout().addWidget(new_spacer())

        self.container_buttons.layout().addWidget(self.progress_bar)
        self.container_buttons.layout().addWidget(new_spacer())

        self.bt_next = QPushButton(self.i18n['screenshots.bt_next.label'].capitalize() + ' > ')
        self.bt_next.setObjectName('next')
        self.bt_next.setProperty('control', 'true')
        self.bt_next.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_next.clicked.connect(self.next)
        self.container_buttons.layout().addWidget(self.bt_next)

        self.layout().addWidget(self.container_buttons)

        self.img_idx = 0
        self.max_img_width = 800
        self.max_img_height = 600

        for idx, s in enumerate(self.screenshots):
            t = Thread(target=self._download_img, args=(idx, s), daemon=True)
            t.start()

        self.resize(self.max_img_width + 5, self.max_img_height + 5)
        self._load_img()
        qt_utils.centralize(self)

    def _update_progress(self, val: int):
        self.progress_bar.setValue(val)

    def _load_img(self):
        if len(self.loaded_imgs) > self.img_idx:
            img = self.loaded_imgs[self.img_idx]

            if isinstance(img, QPixmap):
                self.img.setText('')
                self.img.setPixmap(img)
            else:
                self.img.setText(img)
                self.img.setPixmap(QPixmap())

            self.img.unsetCursor()
            self.thread_progress.stop = True
            self.progress_bar.setVisible(False)
        else:
            self.img.setPixmap(QPixmap())
            self.img.setCursor(QCursor(Qt.WaitCursor))
            self.img.setText('{} {}/{}...'.format(self.i18n['screenshots.image.loading'], self.img_idx + 1, len(self.screenshots)))
            self.progress_bar.setVisible(True)
            self.thread_progress.start()

        if len(self.screenshots) == 1:
            self.bt_back.setVisible(False)
            self.bt_next.setVisible(False)
        else:
            self.bt_back.setEnabled(self.img_idx != 0)
            self.bt_next.setEnabled(self.img_idx != len(self.screenshots) - 1)

    def _download_img(self, idx: int, url: str):
        self.logger.info('Downloading image [{}] from {}'.format(idx, url))
        res = self.http_client.get(url)

        if res:
            if not res.content:
                self.logger.warning('Image [{}] from {} has no content'.format(idx, url))
                self.loaded_imgs.append(self.i18n['screenshots.download.no_content'])
                self._load_img()
            else:
                self.logger.info('Image [{}] successfully downloaded'.format(idx))
                pixmap = QPixmap()
                pixmap.loadFromData(res.content)

                if pixmap.size().height() > self.max_img_height or pixmap.size().width() > self.max_img_width:
                    pixmap = pixmap.scaled(self.max_img_width, self.max_img_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                self.loaded_imgs.append(pixmap)

                if self.img_idx == idx:
                    self._load_img()
        else:
            self.logger.info("Could not retrieve image [{}] from {}".format(idx, url))
            self.loaded_imgs.append(self.i18n['screenshots.download.no_response'])
            self._load_img()

    def back(self):
        self.img_idx -= 1
        self._load_img()

    def next(self):
        self.img_idx += 1
        self._load_img()
