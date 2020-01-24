from io import StringIO

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QToolBar, QSizePolicy, QToolButton, QPushButton

from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.view import MessageType
from bauh.view.qt import dialog
from bauh.view.qt.components import to_widget, new_spacer
from bauh.view.util.translation import I18n


class SettingsWindow(QWidget):

    def __init__(self, manager: SoftwareManager, i18n: I18n, parent: QWidget = None):
        super(SettingsWindow, self).__init__(parent=parent)
        self.setWindowTitle('Settings')
        self.setLayout(QVBoxLayout())
        self.manager = manager
        self.i18n = i18n
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        self.settings_model = self.manager.get_settings()

        self.layout().addWidget(to_widget(self.settings_model, i18n))

        action_bar = QToolBar()
        action_bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        bt_close = QPushButton()
        bt_close.setText(self.i18n['close'].capitalize())
        bt_close.clicked.connect(lambda: self.close())
        action_bar.addWidget(bt_close)

        action_bar.addWidget(new_spacer())

        bt_save = QPushButton()
        bt_save.setText(self.i18n['save'].capitalize())
        bt_save.clicked.connect(self._save_settings)
        action_bar.addWidget(bt_save)

        self.layout().addWidget(action_bar)

    def _save_settings(self):
        success, warnings = self.manager.save_settings(self.settings_model)

        if success:
            self.close()
        else:
            msg = StringIO()
            msg.write("It was not possible to properly the settings\n")

            for w in warnings:
                msg.write(w + '\n')

            msg.seek(0)

            dialog.show_message(title="Warning", body=msg.read(), type_=MessageType.WARNING)
