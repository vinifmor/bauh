#!env/bin/python
import sys

from PyQt5.QtWidgets import QApplication

from core.controller import FlatpakController
from core.model import FlatpakManager
from view.qt.window import MainWindow

app = QApplication(sys.argv)
app.setStyle('Fusion')
manager = FlatpakManager()
controller = FlatpakController(manager)
window_main = MainWindow(controller)
window_main.refresh()

# tray_icon = SystemTrayIcon(window_main)
window_main.show()
# tray_icon.show()
sys.exit(app.exec_())
