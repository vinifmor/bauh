from typing import List

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from bauh_api.abstract.component import ComponentsManager, Component


class UpdatesPanel(QWidget):

    def __init__(self, manager: ComponentsManager, updates: List[Component], i18n: dict):
        super(UpdatesPanel, self).__init__()
        self.manager = manager
        self.updates = updates
        self.i18n = i18n

        self.setLayout(QVBoxLayout())
        self.resize(400, 400)
        self.setWindowTitle('Update')  # TODO i18n

        conflicts = False
        for up in updates:
            if up.conflicts:
                conflicts = True
                break

        if not conflicts:
            self.layout().addWidget(QLabel("There are some {} updates available. Do you wish to update them now ?"))  # i18n
        else:
            self.layout().addWidget(
                self.layout().addWidget(QLabel("There are some {} updates available, but they cannot be executed due to internal conflicts")))  # i18n
