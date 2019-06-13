#!env/bin/python
import sys

from PyQt5.QtWidgets import QApplication, QWidget

from core.controller import FlatpakController
from core.model import FlatpakManager
from view.qt.systray import TrayIcon

app = QApplication(sys.argv)
manager = FlatpakManager()
controller = FlatpakController(manager)
hidden_widget = QWidget()
trayIcon = TrayIcon(parent=hidden_widget, controller=controller, check_interval=30)
trayIcon.show()

sys.exit(app.exec_())
