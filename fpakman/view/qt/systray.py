import os
import time

from PyQt5.QtCore import QThread, pyqtSignal, QCoreApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu
from fpakman.core.controller import FlatpakManager

from fpakman.core import resource
from fpakman.view.qt.about import AboutDialog
from fpakman.view.qt.window import ManageWindow


class UpdateCheck(QThread):

    signal = pyqtSignal(int)

    def __init__(self, manager: FlatpakManager, check_interval: int, parent=None):
        super(UpdateCheck, self).__init__(parent)
        self.check_interval = check_interval
        self.manager = manager

    def run(self):

        while True:

            apps = self.manager.read_installed()

            updates = len([app for app in apps if app['update']])

            self.signal.emit(updates)

            time.sleep(self.check_interval)


class TrayIcon(QSystemTrayIcon):

    def __init__(self, locale_keys: dict, manager: FlatpakManager, check_interval: int = 60):
        super(TrayIcon, self).__init__()
        self.locale_keys = locale_keys
        self.manager = manager

        self.icon_default = QIcon(resource.get_path('img/flathub_45.svg'))
        self.icon_update = QIcon(resource.get_path('img/update_logo.svg'))
        self.setIcon(self.icon_default)

        self.menu = QMenu()

        self.action_manage = self.menu.addAction(self.locale_keys['tray.action.manage'])
        self.action_manage.triggered.connect(self.show_manage_window)

        self.action_about = self.menu.addAction(self.locale_keys['tray.action.about'])
        self.action_about.triggered.connect(self.show_about)

        self.action_exit = self.menu.addAction(self.locale_keys['tray.action.exit'])
        self.action_exit.triggered.connect(lambda: QCoreApplication.exit())

        self.setContextMenu(self.menu)

        self.manage_window = ManageWindow(locale_keys=self.locale_keys, manager=self.manager, tray_icon=self)
        self.check_thread = UpdateCheck(check_interval=check_interval, manager=self.manager)
        self.check_thread.signal.connect(self.notify_updates)
        self.check_thread.start()

        self.dialog_about = AboutDialog(self.locale_keys)

    def notify_updates(self, updates: int):
        if updates > 0:
            if self.icon().cacheKey() != self.icon_update.cacheKey():
                self.setIcon(self.icon_update)

                msg = '{}: {}'.format(self.locale_keys['notification.new_updates'], updates)
                self.setToolTip(msg)

                if bool(os.getenv('FPAKMAN_UPDATE_NOTIFICATION', 1)):
                    os.system("notify-send -i {} '{}'".format(resource.get_path('img/flathub_45.svg'), msg))

                if self.manage_window:
                    self.manage_window.refresh()

        else:
            self.setIcon(self.icon_default)
            self.setToolTip(None)

    def show_manage_window(self):

        if not self.manage_window:
            self.manage_window = ManageWindow(locale_keys=self.locale_keys,
                                              manager=self.manager,
                                              tray_icon=self)

        self.manage_window.refresh()
        self.manage_window.show()

    def show_about(self):

        if self.dialog_about.isHidden():
            self.dialog_about.show()
