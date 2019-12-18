from typing import List

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QLabel, QWidget, QScrollArea, QFrame, QSizePolicy

from bauh.api.abstract.view import ViewComponent, SingleSelectComponent, MultipleSelectComponent, TextInputComponent, \
    FormComponent
from bauh.view.qt import css
from bauh.view.qt.components import MultipleSelectQt, new_single_select, TextInputQt, FormQt, new_spacer
from bauh.view.util.translation import I18n


class ConfirmationDialog(QMessageBox):

    def __init__(self, title: str, body: str, i18n: I18n, screen_size: QSize,  components: List[ViewComponent] = None,
                 confirmation_label: str = None, deny_label: str = None):
        super(ConfirmationDialog, self).__init__()
        self.setWindowTitle(title)
        self.setStyleSheet('QLabel { margin-right: 25px; }')
        self.bt_yes = self.addButton(i18n['popup.button.yes'] if not confirmation_label else confirmation_label.capitalize(), QMessageBox.YesRole)
        self.bt_yes.setStyleSheet(css.OK_BUTTON)

        self.addButton(i18n['popup.button.no'] if not deny_label else deny_label.capitalize(), QMessageBox.NoRole)

        label = None
        if body:
            if not components:
                self.setIcon(QMessageBox.Question)
            label = QLabel(body)
            self.layout().addWidget(label, 0, 1)

        width = 0
        if components:
            scroll = QScrollArea(self)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidgetResizable(True)

            comps_container = QWidget()
            comps_container.setLayout(QVBoxLayout())
            scroll.setWidget(comps_container)

            height = 0

            for idx, comp in enumerate(components):
                if isinstance(comp, SingleSelectComponent):
                    inst = new_single_select(comp)
                elif isinstance(comp, MultipleSelectComponent):
                    inst = MultipleSelectQt(comp, None)
                elif isinstance(comp, TextInputComponent):
                    inst = TextInputQt(comp)
                elif isinstance(comp, FormComponent):
                    inst = FormQt(comp, i18n)
                else:
                    raise Exception("Cannot render instances of " + comp.__class__.__name__)

                height += inst.sizeHint().height()

                if inst.sizeHint().width() > width:
                    width = inst.sizeHint().width()

                comps_container.layout().addWidget(inst)

            height = height if height < int(screen_size.height() / 2.5) else int(screen_size.height() / 2.5)

            scroll.setFixedHeight(height)

            self.layout().addWidget(scroll, 1 if body else 0, 1)

            if label and comps_container.sizeHint().width() > label.sizeHint().width():
                label.setText(label.text() + (' ' * int(comps_container.sizeHint().width() - label.sizeHint().width())))
        if not body and width > 0:
            self.layout().addWidget(QLabel(' ' * int(width / 2)), 1, 1)

        self.exec_()

    def is_confirmed(self):
        return self.clickedButton() == self.bt_yes
