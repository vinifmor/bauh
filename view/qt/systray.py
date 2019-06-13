import time

from PyQt5.QtCore import QThread, pyqtSignal, QCoreApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu

from core import resource


# to update
from core.controller import FlatpakController
from view.qt.window import ManageWindow


class UpdateCheck(QThread):

    signal = pyqtSignal(int)

    def __init__(self, check_interval: int, controller: FlatpakController, parent=None):
        super(UpdateCheck, self).__init__(parent)
        self.controller = controller
        self.check_interval = check_interval

    def run(self):

        while True:

            apps = self.controller.refresh()

            updates = len([app for app in apps if app['update']])

            self.signal.emit(updates)

            time.sleep(self.check_interval)


class TrayIcon(QSystemTrayIcon):

    def __init__(self, controller: FlatpakController, check_interval: int = 60, parent=None):
        self.controller = controller

        self.icon_default = QIcon(resource.get_path('img/flathub_45.svg'))
        self.icon_update = QIcon(resource.get_path('img/update_logo.svg'))
        QSystemTrayIcon.__init__(self, self.icon_default, parent)

        self.menu = QMenu(parent)
        self.action_manage = self.menu.addAction("Manage applications")
        self.action_manage.triggered.connect(self.show_manage_window)
        self.action_exit = self.menu.addAction("Exit")
        self.action_exit.triggered.connect(lambda: QCoreApplication.exit())
        self.setContextMenu(self.menu)

        self.manage_window = ManageWindow(controller=controller, tray_icon=self)
        self.check_thread = UpdateCheck(check_interval=check_interval, controller=self.controller)
        self.check_thread.signal.connect(self.notify_updates)
        self.check_thread.start()

    def notify_updates(self, updates: int):
        if updates > 0:
            if self.icon() != self.icon_update:
                self.setIcon(self.icon_update)
                self.setToolTip('Updates found: {}'.format(updates))

                if self.manage_window:
                    self.manage_window.refresh()
        else:
            self.setIcon(self.icon_default)
            self.setToolTip(None)

    def show_manage_window(self):

        if not self.manage_window:
            self.manage_window = ManageWindow(controller=self.controller)

        self.manage_window.refresh()
        self.manage_window.show()
