import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QApplication, QWidget

from core import resource


# to update
#apps = flatpak.list_installed()
#print(apps)


class SystemTrayIcon(QSystemTrayIcon):

    def __init__(self, parent=None):
        QSystemTrayIcon.__init__(self, QIcon(resource.get_path('img/flathub_logo.svg')), parent)
        self.menu = QMenu(parent)
        exitAction = self.menu.addAction("Exit")
        self.setContextMenu(self.menu)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = QWidget()
    trayIcon = SystemTrayIcon(w)
    trayIcon.show()

    sys.exit(app.exec_())
