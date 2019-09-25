from typing import List

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QLabel, QWidget
from bauh.api.abstract.view import ViewComponent, SingleSelectComponent, MultipleSelectComponent
from bauh.view.qt import css

from bauh.view.qt.components import MultipleSelectQt, new_single_select


class ConfirmationDialog(QMessageBox):

    def __init__(self, title: str, body: str, locale_keys: dict, components: List[ViewComponent] = None, confirmation_label: str = None, deny_label: str = None):
        super(ConfirmationDialog, self).__init__()
        self.setWindowTitle(title)
        self.setStyleSheet('QLabel { margin-right: 25px; }')
        self.bt_yes = self.addButton(locale_keys['popup.button.yes'] if not confirmation_label else confirmation_label.capitalize(), QMessageBox.YesRole)
        self.bt_yes.setStyleSheet(css.OK_BUTTON)

        self.addButton(locale_keys['popup.button.no'] if not deny_label else deny_label.capitalize(), QMessageBox.NoRole)

        if body:
            if not components:
                self.setIcon(QMessageBox.Question)

            self.layout().addWidget(QLabel(body), 0, 1)

        if components:
            comps_container = QWidget(parent=self)
            comps_container.setLayout(QVBoxLayout())

            for idx, comp in enumerate(components):
                if isinstance(comp, SingleSelectComponent):
                    inst = new_single_select(comp)
                elif isinstance(comp, MultipleSelectComponent):
                    inst = MultipleSelectQt(comp, None)
                else:
                    raise Exception("Cannot render instances of " + comp.__class__.__name__)

                comps_container.layout().addWidget(inst)

            self.layout().addWidget(comps_container, 1, 1)

        self.exec_()

    def is_confirmed(self):
        return self.clickedButton() == self.bt_yes
