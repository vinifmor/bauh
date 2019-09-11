import subprocess
import sys
from typing import List

from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QLabel, QGridLayout, QPushButton

from bauh import ROOT_DIR
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.view import MultipleSelectComponent, InputOption
from bauh.commons import resource
from bauh.core.config import Configuration, save
from bauh.view.qt.components import MultipleSelectQt, CheckboxQt, new_spacer


class GemSelectorPanel(QWidget):

    def __init__(self, managers: List[SoftwareManager], i18n: dict, boot: bool):
        super(GemSelectorPanel, self).__init__()
        self.managers = managers
        self.setLayout(QGridLayout())
        self.setWindowIcon(QIcon(resource.get_path('img/logo.svg', ROOT_DIR)))
        self.setWindowTitle('Welcome' if boot else 'Supported types')
        self.resize(400, 400)

        self.label_question = QLabel('What types of applications do you want to find here ?')
        self.label_question.setStyleSheet('QLabel { font-weight: bold}')
        self.layout().addWidget(self.label_question, 0, 1, Qt.AlignHCenter)

        self.bt_proceed = QPushButton('Proceed')
        self.bt_proceed.setStyleSheet('QPushButton { background: green; color: white; font-weight: bold}')
        self.bt_proceed.setEnabled(True)
        self.bt_proceed.clicked.connect(self.save)

        self.bt_exit = QPushButton('Exit')
        self.bt_exit.setStyleSheet('QPushButton { background: red; color: white; font-weight: bold}')
        self.bt_exit.clicked.connect(lambda:  QCoreApplication.exit())

        gem_options = []

        for m in managers:
            modname = m.__module__.split('.')[-2]
            gem_options.append(InputOption(label=i18n.get('gem.{}.label'.format(modname), modname.capitalize()),
                                           value=modname,
                                           icon_path='{r}/gems/{n}/resources/img/{n}.png'.format(r=ROOT_DIR, n=modname)))

        self.gem_select_model = MultipleSelectComponent(label='', options=gem_options, default_options=set(gem_options), max_per_line=3)

        self.gem_select = MultipleSelectQt(self.gem_select_model, self.check_state)
        self.layout().addWidget(self.gem_select, 1, 1)

        self.layout().addWidget(new_spacer(), 2, 1)

        self.layout().addWidget(self.bt_proceed, 3, 1, Qt.AlignRight)
        self.layout().addWidget(self.bt_exit, 3, 1, Qt.AlignLeft)

        self.adjustSize()
        self.setFixedSize(self.size())

    def check_state(self, model: CheckboxQt, checked: bool):
        self.bt_proceed.setEnabled(bool(self.gem_select_model.values))

    def save(self):
        config = Configuration(gems=[o.value for o in self.gem_select_model.values])
        save(config)
        subprocess.Popen([sys.executable, *sys.argv])
        self.close()

