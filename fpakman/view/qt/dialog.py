from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMessageBox

from fpakman.core import resource


def show_error(title: str, body: str, icon: QIcon = QIcon(resource.get_path('img/logo.svg'))):
    error_msg = QMessageBox()
    error_msg.setIcon(QMessageBox.Critical)
    error_msg.setWindowTitle(title)
    error_msg.setText(body)

    if icon:
        error_msg.setWindowIcon(icon)

    error_msg.exec_()


def show_warning(title: str, body: str, icon: QIcon = QIcon(resource.get_path('img/logo.svg'))):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setWindowTitle(title)
    msg.setText(body)

    if icon:
        msg.setWindowIcon(icon)

    msg.exec_()


def ask_confirmation(title: str, body: str, locale_keys: dict, icon: QIcon = QIcon(resource.get_path('img/logo.svg'))):
    dialog_confirmation = QMessageBox()
    dialog_confirmation.setIcon(QMessageBox.Question)
    dialog_confirmation.setWindowTitle(title)
    dialog_confirmation.setText(body)
    dialog_confirmation.setStyleSheet('QLabel { margin-right: 25px; }')

    bt_yes = dialog_confirmation.addButton(locale_keys['popup.button.yes'], QMessageBox.YesRole)
    dialog_confirmation.addButton(locale_keys['popup.button.no'], QMessageBox.NoRole)

    if icon:
        dialog_confirmation.setWindowIcon(icon)

    dialog_confirmation.exec_()

    return dialog_confirmation.clickedButton() == bt_yes
