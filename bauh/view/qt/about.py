from glob import glob

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QVBoxLayout, QDialog, QLabel, QWidget, QHBoxLayout

from bauh import __version__, __app_name__, ROOT_DIR
from bauh.view.util import resource, util
from bauh.view.util.translation import I18n

PROJECT_URL = 'https://github.com/vinifmor/' + __app_name__
LICENSE_URL = 'https://raw.githubusercontent.com/vinifmor/{}/master/LICENSE'.format(__app_name__)


class AboutDialog(QDialog):

    def __init__(self, i18n: I18n):
        super(AboutDialog, self).__init__()
        self.setWindowTitle(i18n['tray.action.about'])
        layout = QVBoxLayout()
        self.setLayout(layout)

        label_logo = QLabel()
        icon = util.get_default_icon()[1].pixmap(64, 64)
        label_logo.setPixmap(icon)
        label_logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_logo)

        label_name = QLabel(__app_name__)
        label_name.setStyleSheet('font-weight: bold; font-size: 14px')
        label_name.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_name)

        label_version = QLabel(i18n['version'].lower() + ' ' + __version__)
        label_version.setStyleSheet('QLabel { font-size: 11px; font-weight: bold }')
        label_version.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_version)

        layout.addWidget(QLabel(''))

        line_desc = QLabel(i18n['about.info.desc'])
        line_desc.setStyleSheet('font-size: 12px; font-weight: bold;')
        line_desc.setAlignment(Qt.AlignCenter)
        line_desc.setMinimumWidth(400)
        layout.addWidget(line_desc)

        layout.addWidget(QLabel(''))

        available_gems = [f for f in glob('{}/gems/*'.format(ROOT_DIR)) if not f.endswith('.py') and not f.endswith('__pycache__')]
        available_gems.sort()

        gems_widget = QWidget()
        gems_widget.setLayout(QHBoxLayout())

        gems_widget.layout().addWidget(QLabel())
        for gem_path in available_gems:
            icon = QLabel()
            pxmap = QPixmap(gem_path + '/resources/img/{}.png'.format(gem_path.split('/')[-1]))
            icon.setPixmap(pxmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            gems_widget.layout().addWidget(icon)
        gems_widget.layout().addWidget(QLabel())

        layout.addWidget(gems_widget)
        layout.addWidget(QLabel(''))

        label_more_info = QLabel()
        label_more_info.setStyleSheet('font-size: 11px;')
        label_more_info.setText(i18n['about.info.link'] + " <a href='{url}'>{url}</a>".format(url=PROJECT_URL))
        label_more_info.setOpenExternalLinks(True)
        label_more_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_more_info)

        label_license = QLabel()
        label_license.setStyleSheet('font-size: 11px;')
        label_license.setText("<a href='{}'>{}</a>".format(LICENSE_URL, i18n['about.info.license']))
        label_license.setOpenExternalLinks(True)
        label_license.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_license)

        layout.addWidget(QLabel(''))

        label_trouble_question = QLabel(i18n['about.info.trouble.question'])
        label_trouble_question.setStyleSheet('font-size: 10px; font-weight: bold')
        label_trouble_question.setAlignment(Qt.AlignCenter)

        layout.addWidget(label_trouble_question)

        label_trouble_answer = QLabel(i18n['about.info.trouble.answer'])
        label_trouble_answer.setStyleSheet('font-size: 10px;')
        label_trouble_answer.setAlignment(Qt.AlignCenter)

        layout.addWidget(label_trouble_answer)

        layout.addWidget(QLabel(''))

        label_rate_question = QLabel(i18n['about.info.rate.question'])
        label_rate_question.setStyleSheet('font-size: 10px; font-weight: bold;')
        label_rate_question.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_rate_question)

        label_rate_answer = QLabel(i18n['about.info.rate.answer'])
        label_rate_answer.setStyleSheet('font-size: 10px;')
        label_rate_answer.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_rate_answer)

        layout.addWidget(QLabel(''))

        self.adjustSize()
        self.setFixedSize(self.size())

    def closeEvent(self, event):
        event.ignore()
        self.hide()
