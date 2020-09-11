from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QCursor
from PyQt5.QtWidgets import QMessageBox, QLabel, QWidget, QHBoxLayout

from bauh.api.abstract.view import MessageType
from bauh.view.qt import css
from bauh.view.util import resource
from bauh.view.util.translation import I18n

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


def ask_confirmation(title: str, body: str, i18n: I18n, icon: QIcon = QIcon(resource.get_path('img/logo.svg')), widgets: List[QWidget] = None):
    diag = QMessageBox()
    diag.setIcon(QMessageBox.Question)
    diag.setWindowTitle(title)
    diag.setStyleSheet('QLabel { margin-right: 25px; }')
    diag.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)

    wbody = QWidget()
    wbody.setLayout(QHBoxLayout())
    wbody.layout().addWidget(QLabel(body))

    if widgets:
        for w in widgets:
            wbody.layout().addWidget(w)

    diag.layout().addWidget(wbody, 0, 1)

    bt_yes = diag.addButton(i18n['popup.button.yes'], QMessageBox.YesRole)
    bt_yes.setStyleSheet(css.OK_BUTTON)
    bt_yes.setCursor(QCursor(Qt.PointingHandCursor))
    diag.setDefaultButton(bt_yes)

    bt_no = diag.addButton(i18n['popup.button.no'], QMessageBox.NoRole)
    bt_no.setCursor(QCursor(Qt.PointingHandCursor))

    if icon:
        diag.setWindowIcon(icon)

    diag.exec_()

    return diag.clickedButton() == bt_yes
