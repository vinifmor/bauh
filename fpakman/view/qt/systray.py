import time
from threading import Lock
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal, QCoreApplication, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu

from fpakman.core import resource, system
from fpakman.core.controller import FlatpakManager, ApplicationManager
from fpakman.core.model import Application
from fpakman.util.cache import Cache
from fpakman.view.qt.about import AboutDialog
from fpakman.view.qt.window import ManageWindow


class UpdateCheck(QThread):

    signal = pyqtSignal(list)

    def __init__(self, manager: ApplicationManager, check_interval: int, parent=None):
        super(UpdateCheck, self).__init__(parent)
        self.check_interval = check_interval
        self.manager = manager

    def run(self):

        while True:

            apps = self.manager.read_installed()

            updates = [app for app in apps if app.update]

            if updates:
                self.signal.emit(updates)

            time.sleep(self.check_interval)


class TrayIcon(QSystemTrayIcon):

    def __init__(self, locale_keys: dict, manager: ApplicationManager, icon_cache: Cache, disk_cache: bool, check_interval: int = 60, update_notification: bool = True):
        super(TrayIcon, self).__init__()
        self.locale_keys = locale_keys
        self.manager = manager
        self.icon_cache = icon_cache
        self.disk_cache = disk_cache

        self.icon_default = QIcon(resource.get_path('img/logo.png'))
        self.icon_update = QIcon(resource.get_path('img/logo_update.png'))
        self.setIcon(self.icon_default)

        self.menu = QMenu()

        self.action_manage = self.menu.addAction(self.locale_keys['tray.action.manage'])
        self.action_manage.triggered.connect(self.show_manage_window)

        self.action_about = self.menu.addAction(self.locale_keys['tray.action.about'])
        self.action_about.triggered.connect(self.show_about)

        self.action_exit = self.menu.addAction(self.locale_keys['tray.action.exit'])
        self.action_exit.triggered.connect(lambda: QCoreApplication.exit())

        self.setContextMenu(self.menu)

        self.manage_window = None
        self.check_thread = UpdateCheck(check_interval=check_interval, manager=self.manager)
        self.check_thread.signal.connect(self.notify_updates)
        self.check_thread.start()

        self.dialog_about = None

        self.last_updates = set()
        self.update_notification = update_notification
        self.lock_notify = Lock()

    def notify_updates(self, updates: List[Application]):

        self.lock_notify.acquire()

        try:
            if len(updates) > 0:

                update_keys = {'{}:{}'.format(app.base_data.id, app.base_data.version) for app in updates}

                new_icon = self.icon_update

                if update_keys.difference(self.last_updates):
                    self.last_updates = update_keys
                    msg = '{}: {}'.format(self.locale_keys['notification.new_updates'], len(updates))
                    self.setToolTip(msg)

                    if self.update_notification:
                        system.notify_user(msg)

            else:
                new_icon = self.icon_default
                self.setToolTip(None)

            if self.icon().cacheKey() != new_icon.cacheKey():  # changes the icon if needed
                self.setIcon(new_icon)

        finally:
            self.lock_notify.release()

    def show_manage_window(self):

        if self.manage_window is None:
            self.manage_window = ManageWindow(locale_keys=self.locale_keys,
                                              manager=self.manager,
                                              icon_cache=self.icon_cache,
                                              tray_icon=self,
                                              disk_cache=self.disk_cache)

        if self.manage_window.isMinimized():
            self.manage_window.setWindowState(Qt.WindowNoState)
        else:
            self.manage_window.refresh()
            self.manage_window.show()

    def show_about(self):

        if self.dialog_about is None:
            self.dialog_about = AboutDialog(self.locale_keys)

        if self.dialog_about.isHidden():
            self.dialog_about.show()
