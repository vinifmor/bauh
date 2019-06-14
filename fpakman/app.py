import argparse
import os
import sys

from PyQt5.QtWidgets import QApplication, QWidget

from fpakman.core.controller import FlatpakController
from fpakman.core.model import FlatpakManager
from fpakman.view.qt.systray import TrayIcon
from fpakman.core import __version__
from fpakman.core import util

parser = argparse.ArgumentParser(prog='fpakman', description="GUI for Flatpak applications management")
parser.add_argument('-v', '--version', action='version', version='%(prog)s {}'.format(__version__))
args = parser.parse_args()

locale_keys = util.get_locale_keys()

app = QApplication(sys.argv)
manager = FlatpakManager()
manager.load_database_async()
controller = FlatpakController(manager)
hidden_widget = QWidget()

trayIcon = TrayIcon(locale_keys=locale_keys,
                    parent=hidden_widget,
                    controller=controller,
                    check_interval=int(os.getenv('FPAKMAN_CHECK_INTERVAL', 60)))
trayIcon.show()

sys.exit(app.exec_())
