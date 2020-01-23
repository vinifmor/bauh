from PyQt5.QtWidgets import QWidget, QVBoxLayout, QToolBar, QSizePolicy, QToolButton

from bauh.api.abstract.controller import SoftwareManager
from bauh.view.qt.components import to_widget
from bauh.view.util.translation import I18n


class SettingsWindow(QWidget):

    def __init__(self, manager: SoftwareManager, i18n: I18n, parent: QWidget = None):
        super(SettingsWindow, self).__init__(parent=parent)
        self.setWindowTitle('Settings')
        self.setLayout(QVBoxLayout())
        self.manager = manager
        self.i18n = i18n
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        settings_model = self.manager.get_settings()

        self.layout().addWidget(to_widget(settings_model, i18n))

        action_bar = QToolBar()
        action_bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        bt_save = QToolButton()
        bt_save.setText('Save')
        action_bar.addWidget(bt_save)

        self.layout().addWidget(action_bar)
