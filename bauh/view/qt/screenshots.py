import logging
import traceback
from io import BytesIO
from threading import Thread
from typing import List, Dict

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

        self.bt_close = QPushButton(self.i18n['screenshots.bt_close'])
        self.bt_close.setObjectName('close')
        self.bt_close.clicked.connect(self.close)
        self.bt_close.setCursor(QCursor(Qt.PointingHandCursor))

        self.upper_buttons = QWidget()
        self.upper_buttons.setObjectName('upper_buttons')
        self.upper_buttons.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.upper_buttons.setContentsMargins(0, 0, 0, 0)
        self.upper_buttons.setLayout(QHBoxLayout())
        self.upper_buttons.layout().setAlignment(Qt.AlignRight)
        self.upper_buttons.layout().addWidget(self.bt_close)
        self.layout().addWidget(self.upper_buttons)

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

        self.img_label = QLabel()
        self.img_label.setObjectName("image_label")
        self.container_buttons.layout().addWidget(self.img_label)

        self.container_buttons.layout().addWidget(self.progress_bar)
        self.container_buttons.layout().addWidget(new_spacer())

        self.bt_next = QPushButton(self.i18n['screenshots.bt_next.label'].capitalize() + ' > ')
        self.bt_next.setObjectName('next')
        self.bt_next.setProperty('control', 'true')
        self.bt_next.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_next.clicked.connect(self.next)
        self.container_buttons.layout().addWidget(self.bt_next)
        self.download_progress: Dict[int, float] = dict()

        self.layout().addWidget(self.container_buttons)

        self.img_idx = 0
        self.max_img_width = 800
        self.max_img_height = 600

        for idx, s in enumerate(self.screenshots):
            t = Thread(target=self._download_img, args=(idx, s), daemon=True)
            t.start()

        self.resize(self.max_img_width + 5, self.max_img_height + 5)
        self._load_img(self.img_idx)
        qt_utils.centralize(self)

    def _update_progress(self, val: int):
        self.progress_bar.setValue(val)

    def _load_img(self, img_idx: int):
        if img_idx != self.img_idx:
            return

        if len(self.loaded_imgs) > self.img_idx:
            img = self.loaded_imgs[self.img_idx]

            if isinstance(img, QPixmap):
                self.img_label.setText(f'{self.img_idx + 1}/{len(self.screenshots)}')
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

            progress = self.download_progress.get(self.img_idx, 0)
            self.img.setText(f"{self.i18n['screenshots.image.loading']} "
                             f"{self.img_idx + 1}/{len(self.screenshots)} ({progress:.2f}%)")
            self.progress_bar.setVisible(True)
            self.thread_progress.start()

        if len(self.screenshots) == 1:
            self.bt_back.setVisible(False)
            self.bt_next.setVisible(False)
        else:
            self.bt_back.setEnabled(self.img_idx != 0)
            self.bt_next.setEnabled(self.img_idx != len(self.screenshots) - 1)

    def _handle_download_exception(self, idx: int, url: str):
        self.logger.error(f"Unexpected exception while downloading screenshot from '{url}'")
        traceback.print_exc()
        self.loaded_imgs.append(self.i18n["screenshots.download.no_response"])
        self._load_img(idx)

    def _download_img(self, idx: int, url: str):
        self.logger.info(f"Downloading image [{idx}] from {url}")

        try:
            res = self.http_client.get(url=url, stream=True)
        except Exception:
            self._handle_download_exception(idx, url)
            return

        if not res:
            self.logger.info(f"Could not retrieve image [{idx}] from '{url}'")
            self.loaded_imgs.append(self.i18n["screenshots.download.no_response"])
            self._load_img(idx)
            return

        try:
            content_length = int(res.headers.get("content-length", 0))
        except Exception:
            content_length = 0
            self.logger.warning(f"Could not retrieve the content-length for file '{url}'")

        if content_length <= 0:
            self.logger.warning(f"Image [{idx}] has no content ({url})")
            self.loaded_imgs.append(self.i18n['screenshots.download.no_content'])
            self._load_img(idx)
        else:
            byte_stream = BytesIO()

            total_downloaded = 0
            try:
                for data in res.iter_content(chunk_size=1024):
                    byte_stream.write(data)
                    total_downloaded += len(data)
                    self.download_progress[idx] = (total_downloaded / content_length) * 100
                    self._load_img(idx)
            except Exception:
                self._handle_download_exception(idx, url)
                return

            self.logger.info(f"Image [{idx}] successfully downloaded ({url})")
            pixmap = QPixmap()
            pixmap.loadFromData(byte_stream.getvalue())

            if pixmap.size().height() > self.max_img_height or pixmap.size().width() > self.max_img_width:
                pixmap = pixmap.scaled(self.max_img_width, self.max_img_height, Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation)

            self.loaded_imgs.append(pixmap)
            self._load_img(idx)

    def back(self):
        self.img_idx -= 1
        self._load_img(self.img_idx)

    def next(self):
        self.img_idx += 1
        self._load_img(self.img_idx)
