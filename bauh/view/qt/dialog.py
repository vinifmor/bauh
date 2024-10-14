from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QCursor
from PyQt6.QtWidgets import QMessageBox, QLabel, QWidget, QHBoxLayout, QDialog, QVBoxLayout, QSizePolicy, QPushButton, \
    QScrollArea, QFrame

from bauh.api.abstract.view import MessageType
from bauh.view.qt.components import new_spacer
from bauh.view.util import resource
from bauh.view.util.translation import I18n

MSG_TYPE_MAP = {
    MessageType.ERROR: QMessageBox.Icon.Critical,
    MessageType.INFO: QMessageBox.Icon.Information,
    MessageType.WARNING: QMessageBox.Icon.Warning
}


def show_message(title: str, body: str, type_: MessageType, icon: QIcon = QIcon(resource.get_path('img/logo.svg'))):
    popup = QMessageBox()
    popup.setWindowTitle(title)
    popup.setText(body)
    popup.setIcon(MSG_TYPE_MAP[type_])

    if icon:
        popup.setWindowIcon(icon)

    popup.exec()


class ConfirmationDialog(QDialog):

    def __init__(self, title: str, body: Optional[str], i18n: I18n, icon: QIcon = QIcon(resource.get_path('img/logo.svg')),
                 widgets: Optional[List[QWidget]] = None, confirmation_button: bool = True, deny_button: bool = True,
                 window_cancel: bool = False, confirmation_label: Optional[str] = None, deny_label: Optional[str] = None,
                 confirmation_icon: bool = True, min_width: Optional[int] = None,
                 min_height: Optional[int] = None, max_width: Optional[int] = None,
                 confirmation_icon_type: MessageType = MessageType.INFO):
        super(ConfirmationDialog, self).__init__()

        if not window_cancel:
            self.setWindowFlags(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)

        self.setLayout(QVBoxLayout())
        self.setWindowTitle(title)
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(min_width if min_width and min_width > 0 else 250)

        if max_width is not None and max_width > 0:
            self.setMaximumWidth(max_width)

        if isinstance(min_height, int) and min_height > 0:
            self.setMinimumHeight(min_height)

        self.confirmed = False

        if icon:
            self.setWindowIcon(icon)

        container_body = QWidget()
        container_body.setObjectName('confirm_container_body')
        container_body.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)

        if isinstance(min_height, int) and min_height > 0:
            container_body.setMinimumWidth(min_height)

        if widgets:
            container_body.setLayout(QVBoxLayout())
            scroll = QScrollArea(self)
            scroll.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setWidget(container_body)
            self.layout().addWidget(scroll)
        else:
            container_body.setLayout(QHBoxLayout())
            self.layout().addWidget(container_body)

            if confirmation_icon:
                lb_icon = QLabel()
                lb_icon.setObjectName("confirm_dialog_icon")
                lb_icon.setProperty("type", confirmation_icon_type.name.lower())
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
        container_bottom.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        container_bottom.setLayout(QHBoxLayout())
        self.layout().addWidget(container_bottom)

        container_bottom.layout().addWidget(new_spacer())

        if confirmation_button:
            bt_confirm = QPushButton(confirmation_label.capitalize() if confirmation_label else i18n['popup.button.yes'])
            bt_confirm.setObjectName('ok')
            bt_confirm.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            bt_confirm.setDefault(True)
            bt_confirm.setAutoDefault(True)
            bt_confirm.clicked.connect(self.confirm)
            container_bottom.layout().addWidget(bt_confirm)

        if deny_button:
            bt_cancel = QPushButton(deny_label.capitalize() if deny_label else i18n['popup.button.no'])
            bt_cancel.setObjectName('bt_cancel')
            bt_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            bt_cancel.clicked.connect(self.close)
            container_bottom.layout().addWidget(bt_cancel)

            if not confirmation_button:
                bt_cancel.setDefault(True)
                bt_cancel.setAutoDefault(True)

    def confirm(self):
        self.confirmed = True
        self.close()

    def ask(self) -> bool:
        self.exec()
        return self.confirmed


def ask_confirmation(title: str, body: str, i18n: I18n, icon: QIcon = QIcon(resource.get_path('img/logo.svg')),
                     widgets: List[QWidget] = None) -> bool:
    popup = ConfirmationDialog(title=title, body=body, i18n=i18n, icon=icon, widgets=widgets)
    popup.exec()
    return popup.confirmed
