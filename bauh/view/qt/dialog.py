from typing import List, Optional

from PyQt5.QtCore import Qt, QSize, QMargins
from PyQt5.QtGui import QIcon, QCursor
from PyQt5.QtWidgets import QMessageBox, QLabel, QWidget, QHBoxLayout, QDialog, QVBoxLayout, QSizePolicy, QApplication, \
    QStyle, QPushButton, QScrollArea, QFrame

from bauh.api.abstract.view import MessageType
from bauh.view.qt.components import new_spacer
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


class ConfirmationDialog(QDialog):

    def __init__(self, title: str, body: Optional[str], i18n: I18n, icon: QIcon = QIcon(resource.get_path('img/logo.svg')),
                 widgets: Optional[List[QWidget]] = None, confirmation_button: bool = True, deny_button: bool = True,
                 window_cancel: bool = False, confirmation_label: Optional[str] = None, deny_label: Optional[str] = None):
        super(ConfirmationDialog, self).__init__()

        if not window_cancel:
            self.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)

        self.setLayout(QVBoxLayout())
        self.setWindowTitle(title)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        self.setMinimumWidth(250)
        self.confirmed = False

        if icon:
            self.setWindowIcon(icon)

        container_body = QWidget()
        container_body.setObjectName('confirm_container_body')
        container_body.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)

        if widgets:
            container_body.setLayout(QVBoxLayout())
            scroll = QScrollArea(self)
            scroll.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setWidget(container_body)
            self.layout().addWidget(scroll)
        else:
            container_body.setLayout(QHBoxLayout())
            self.layout().addWidget(container_body)

            lb_icon = QLabel()
            lb_icon.setObjectName('confirm_icon')
            lb_icon.setPixmap(QApplication.style().standardIcon(QStyle.SP_MessageBoxQuestion).pixmap(QSize(48, 48)))
            container_body.layout().addWidget(lb_icon)

        if body:
            lb_msg = QLabel(body)
            lb_msg.setObjectName('confirm_msg')
            container_body.layout().addWidget(lb_msg)

        if widgets:
            for w in widgets:
                container_body.layout().addWidget(w)
        else:
            container_body.layout().addWidget(new_spacer())

        container_bottom = QWidget()
        container_bottom.setObjectName('confirm_container_bottom')
        container_bottom.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        container_bottom.setLayout(QHBoxLayout())
        self.layout().addWidget(container_bottom)

        container_bottom.layout().addWidget(new_spacer())

        if confirmation_button:
            bt_confirm = QPushButton(confirmation_label.capitalize() if confirmation_label else i18n['popup.button.yes'])
            bt_confirm.setObjectName('ok')
            bt_confirm.setCursor(QCursor(Qt.PointingHandCursor))
            bt_confirm.setDefault(True)
            bt_confirm.setAutoDefault(True)
            bt_confirm.clicked.connect(self.confirm)
            container_bottom.layout().addWidget(bt_confirm)

        if deny_button:
            bt_cancel = QPushButton(deny_label.capitalize() if deny_label else i18n['popup.button.no'])
            bt_cancel.setObjectName('bt_cancel')
            bt_cancel.setCursor(QCursor(Qt.PointingHandCursor))
            bt_cancel.clicked.connect(self.close)
            container_bottom.layout().addWidget(bt_cancel)

            if not confirmation_button:
                bt_cancel.setDefault(True)
                bt_cancel.setAutoDefault(True)

    def confirm(self):
        self.confirmed = True
        self.close()

    def ask(self) -> bool:
        self.exec_()
        return self.confirmed


def ask_confirmation(title: str, body: str, i18n: I18n, icon: QIcon = QIcon(resource.get_path('img/logo.svg')),
                     widgets: List[QWidget] = None) -> bool:
    popup = ConfirmationDialog(title=title, body=body, i18n=i18n, icon=icon, widgets=widgets)
    popup.exec_()
    return popup.confirmed
