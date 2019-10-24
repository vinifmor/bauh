from glob import glob

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import QVBoxLayout, QDialog, QLabel, QWidget, QHBoxLayout

from bauh import __version__, __app_name__, ROOT_DIR
from bauh.view.util import resource

PROJECT_URL = 'https://github.com/vinifmor/' + __app_name__
LICENSE_URL = 'https://raw.githubusercontent.com/vinifmor/{}/master/LICENSE'.format(__app_name__)


class AboutDialog(QDialog):

    def __init__(self, locale_keys: dict):
        super(AboutDialog, self).__init__()
        self.setWindowTitle(locale_keys['tray.action.about'])
        layout = QVBoxLayout()
        self.setLayout(layout)

        label_logo = QLabel(self)
        label_logo.setPixmap(QPixmap(resource.get_path('img/logo.svg')))
        label_logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_logo)

        label_name = QLabel(__app_name__)
        label_name.setStyleSheet('font-weight: bold; font-size: 14px')
        label_name.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_name)

        layout.addWidget(QLabel(''))

        line_desc = QLabel(self)
        line_desc.setStyleSheet('font-size: 12px; font-weight: bold;')
        line_desc.setText(locale_keys['about.info.desc'])
        line_desc.setAlignment(Qt.AlignCenter)
        line_desc.setMinimumWidth(400)
        layout.addWidget(line_desc)

        layout.addWidget(QLabel(''))

        available_gems = [f for f in glob('{}/gems/*'.format(ROOT_DIR)) if not f.endswith('.py')]
        available_gems.sort()

        gems_widget = QWidget()
        gems_widget.setLayout(QHBoxLayout())

        for gem_path in available_gems:
            icon = QLabel()
            pxmap = QPixmap(gem_path + '/resources/img/{}.png'.format(gem_path.split('/')[-1]))
            icon.setPixmap(pxmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            gems_widget.layout().addWidget(icon)

        layout.addWidget(gems_widget)
        layout.addWidget(QLabel(''))

        label_version = QLabel(locale_keys['version'].lower() + ' ' + __version__)
        label_version.setStyleSheet('QLabel { font-size: 11px; font-weight: bold }')
        label_version.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_version)

        label_more_info = QLabel()
        label_more_info.setStyleSheet('font-size: 11px;')
        label_more_info.setText(locale_keys['about.info.link'] + ": <a href='{url}'>{url}</a>".format(url=PROJECT_URL))
        label_more_info.setOpenExternalLinks(True)
        label_more_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_more_info)

        label_license = QLabel()
        label_license.setStyleSheet('font-size: 11px;')
        label_license.setText("<a href='{}'>{}</a>".format(LICENSE_URL, locale_keys['about.info.license']))
        label_license.setOpenExternalLinks(True)
        label_license.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_license)

        layout.addWidget(QLabel(''))

        label_rate = QLabel()
        label_rate.setStyleSheet('font-size: 11px; font-weight: bold;')
        label_rate.setText(locale_keys['about.info.rate'] + ' :)')
        label_rate.setOpenExternalLinks(True)
        label_rate.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_rate)

        layout.addWidget(QLabel(''))

        self.adjustSize()
        self.setFixedSize(self.size())

    def closeEvent(self, event):
        event.ignore()
        self.hide()
