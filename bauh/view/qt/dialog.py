from typing import List

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMessageBox, QLabel, QWidget, QHBoxLayout
from bauh_api.abstract.view import MessageType

from bauh.core import resource

MSG_TYPE_MAP = {
    MessageType.ERROR: QMessageBox.Critical,
    MessageType.INFO: QMessageBox.Information,
    MessageType.WARNING: QMessageBox.Warning
}


def show_message(title: str, body: str, type_: MessageType, icon: QIcon = QIcon(resource.get_path('img/logo.svg'))):
    popup = QMessageBox()
    popup.setWindowTitle(title)
    popup.setText(body)
    popup.setIcon(MSG_TYPE_MAP[type_])

    if icon:
        popup.setWindowIcon(icon)

    popup.exec_()


def ask_confirmation(title: str, body: str, locale_keys: dict, icon: QIcon = QIcon(resource.get_path('img/logo.svg')), widgets: List[QWidget] = None):
    dialog_confirmation = QMessageBox()
    dialog_confirmation.setIcon(QMessageBox.Question)
    dialog_confirmation.setWindowTitle(title)
    dialog_confirmation.setStyleSheet('QLabel { margin-right: 25px; }')

    wbody = QWidget()
    wbody.setLayout(QHBoxLayout())
    wbody.layout().addWidget(QLabel(body))

    if widgets:
        for w in widgets:
            wbody.layout().addWidget(w)

    dialog_confirmation.layout().addWidget(wbody, 0, 1)

    bt_yes = dialog_confirmation.addButton(locale_keys['popup.button.yes'], QMessageBox.YesRole)
    dialog_confirmation.addButton(locale_keys['popup.button.no'], QMessageBox.NoRole)

    if icon:
        dialog_confirmation.setWindowIcon(icon)

    dialog_confirmation.exec_()

    return dialog_confirmation.clickedButton() == bt_yes
