import subprocess
import sys
from typing import List

from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QLabel, QGridLayout, QPushButton

from bauh import ROOT_DIR
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.view import MultipleSelectComponent, InputOption
from bauh.commons import resource, system
from bauh.core.config import Configuration, save
from bauh.util import util
from bauh.view.qt import qt_utils
from bauh.view.qt.components import MultipleSelectQt, CheckboxQt, new_spacer


class GemSelectorPanel(QWidget):

    def __init__(self, managers: List[SoftwareManager], i18n: dict, managers_set: List[str], show_panel_after_restart: bool = False):
        super(GemSelectorPanel, self).__init__()
        self.managers = managers
        self.setLayout(QGridLayout())
        self.setWindowIcon(QIcon(resource.get_path('img/logo.svg', ROOT_DIR)))
        self.setWindowTitle(i18n['welcome'].capitalize() if not managers_set else i18n['gem_selector.title'])
        self.resize(400, 400)
        self.exit_on_close = not managers_set
        self.show_panel_after_restart = show_panel_after_restart

        self.label_question = QLabel(i18n['gem_selector.question'])
        self.label_question.setStyleSheet('QLabel { font-weight: bold}')
        self.layout().addWidget(self.label_question, 0, 1, Qt.AlignHCenter)

        self.bt_proceed = QPushButton(i18n['proceed' if not managers_set else 'change'].capitalize())
        self.bt_proceed.setStyleSheet("""QPushButton { background: green; color: white; font-weight: bold} 
                                         QPushButton:disabled { background-color: gray; }  
                                      """)
        self.bt_proceed.clicked.connect(self.save)

        self.bt_exit = QPushButton(i18n['exit'].capitalize())
        self.bt_exit.setStyleSheet('QPushButton { background: red; color: white; font-weight: bold}')
        self.bt_exit.clicked.connect(self.exit)

        gem_options = []

        for m in managers:
            modname = m.__module__.split('.')[-2]
            gem_options.append(InputOption(label=i18n.get('gem.{}.label'.format(modname), modname.capitalize()),
                                           value=modname,
                                           icon_path='{r}/gems/{n}/resources/img/{n}.png'.format(r=ROOT_DIR, n=modname)))

        if managers_set:
            default_ops = {o for o in gem_options if o.value in managers_set}
        else:
            default_ops = set(gem_options)

        self.bt_proceed.setEnabled(bool(default_ops))

        self.gem_select_model = MultipleSelectComponent(label='', options=gem_options, default_options=default_ops, max_per_line=3)

        self.gem_select = MultipleSelectQt(self.gem_select_model, self.check_state)
        self.layout().addWidget(self.gem_select, 1, 1)

        self.layout().addWidget(new_spacer(), 2, 1)

        self.layout().addWidget(self.bt_proceed, 3, 1, Qt.AlignRight)
        self.layout().addWidget(self.bt_exit, 3, 1, Qt.AlignLeft)

        self.adjustSize()
        self.setFixedSize(self.size())
        qt_utils.centralize(self)

    def check_state(self, model: CheckboxQt, checked: bool):
        if self.isVisible():
            self.bt_proceed.setEnabled(bool(self.gem_select_model.values))

    def save(self):
        config = Configuration(gems=[o.value for o in self.gem_select_model.values])
        save(config)

        util.restart_app(self.show_panel_after_restart)

    def exit(self):
        if self.exit_on_close:
            QCoreApplication.exit()
        else:
            self.close()

