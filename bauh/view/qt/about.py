from glob import glob

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QVBoxLayout, QDialog, QLabel, QWidget, QHBoxLayout, QSizePolicy, QApplication

from bauh import __version__, __app_name__, ROOT_DIR
from bauh.context import generate_i18n
from bauh.view.util import resource

PROJECT_URL = 'https://github.com/vinifmor/' + __app_name__
LICENSE_URL = 'https://raw.githubusercontent.com/vinifmor/{}/master/LICENSE'.format(__app_name__)


class AboutDialog(QDialog):

    def __init__(self, app_config: dict):
        super(AboutDialog, self).__init__()
        i18n = generate_i18n(app_config, resource.get_path('locale/about'))
        self.setWindowTitle('{} ({})'.format(i18n['about.title'].capitalize(), __app_name__))
        layout = QVBoxLayout()
        self.setLayout(layout)

        logo_container = QWidget()
        logo_container.setObjectName('logo_container')
        logo_container.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        logo_container.setLayout(QHBoxLayout())

        label_logo = QLabel()
        label_logo.setObjectName('logo')

        logo_container.layout().addWidget(label_logo)
        layout.addWidget(logo_container)

        label_name = QLabel(__app_name__)
        label_name.setObjectName('app_name')
        layout.addWidget(label_name)

        label_version = QLabel(i18n['about.version'].lower() + ' ' + __version__)
        label_version.setObjectName('app_version')
        layout.addWidget(label_version)

        layout.addWidget(QLabel(''))

        line_desc = QLabel(i18n['about.info.desc'])
        line_desc.setObjectName('app_description')
        layout.addWidget(line_desc)

        layout.addWidget(QLabel(''))

        available_gems = [f for f in glob('{}/gems/*'.format(ROOT_DIR)) if not f.endswith('.py') and not f.endswith('__pycache__')]
        available_gems.sort()

        gems_widget = QWidget()
        gems_widget.setLayout(QHBoxLayout())

        gems_widget.layout().addWidget(QLabel())
        gem_logo_size = int(0.032552083 * QApplication.primaryScreen().size().height())

        for gem_path in available_gems:
            icon = QLabel()
            icon.setObjectName('gem_logo')
            icon_path = gem_path + '/resources/img/{}.svg'.format(gem_path.split('/')[-1])
            icon.setPixmap(QIcon(icon_path).pixmap(gem_logo_size, gem_logo_size))
            gems_widget.layout().addWidget(icon)

        gems_widget.layout().addWidget(QLabel())

        layout.addWidget(gems_widget)
        layout.addWidget(QLabel(''))

        label_more_info = QLabel()
        label_more_info.setObjectName('app_more_information')
        label_more_info.setText(i18n['about.info.link'] + " <a href='{url}'>{url}</a>".format(url=PROJECT_URL))
        label_more_info.setOpenExternalLinks(True)
        layout.addWidget(label_more_info)

        label_license = QLabel()
        label_license.setObjectName('app_license')
        label_license.setText("<a href='{}'>{}</a>".format(LICENSE_URL, i18n['about.info.license']))
        label_license.setOpenExternalLinks(True)
        layout.addWidget(label_license)

        layout.addWidget(QLabel(''))

        label_trouble_question = QLabel(i18n['about.info.trouble.question'])
        label_trouble_question.setObjectName('app_trouble_question')

        layout.addWidget(label_trouble_question)

        label_trouble_answer = QLabel(i18n['about.info.trouble.answer'])
        label_trouble_answer.setObjectName('app_trouble_answer')

        layout.addWidget(label_trouble_answer)

        layout.addWidget(QLabel(''))

        label_rate_question = QLabel(i18n['about.info.rate.question'])
        label_rate_question.setObjectName('app_rate_question')
        layout.addWidget(label_rate_question)

        label_rate_answer = QLabel(i18n['about.info.rate.answer'])
        label_rate_answer.setObjectName('app_rate_answer')
        layout.addWidget(label_rate_answer)

        layout.addWidget(QLabel(''))

        self.adjustSize()
        self.setFixedSize(self.size())

    def closeEvent(self, event):
        event.ignore()
        self.hide()
