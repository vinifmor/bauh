import time
from threading import Lock, Thread
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal, QCoreApplication, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu

from bauh import __app_name__
from bauh.core import resource, system
from bauh.core.controller import ApplicationManager
from bauh.core.model import ApplicationUpdate
from bauh.view.qt.about import AboutDialog
from bauh.view.qt.window import ManageWindow


class UpdateCheck(QThread):

    signal = pyqtSignal(list)

    def __init__(self, manager: ApplicationManager, check_interval: int, parent=None):
        super(UpdateCheck, self).__init__(parent)
        self.check_interval = check_interval
        self.manager = manager

    def run(self):

        while True:
            updates = self.manager.list_updates()
            self.signal.emit(updates)
            time.sleep(self.check_interval)


class TrayIcon(QSystemTrayIcon):

    def __init__(self, locale_keys: dict, manager: ApplicationManager, manage_window: ManageWindow, check_interval: int = 60, update_notification: bool = True):
        super(TrayIcon, self).__init__()
        self.locale_keys = locale_keys
        self.manager = manager

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
        self.dialog_about = None
        self.check_thread = UpdateCheck(check_interval=check_interval, manager=self.manager)
        self.check_thread.signal.connect(self.notify_updates)
        self.check_thread.start()

        self.last_updates = set()
        self.update_notification = update_notification
        self.lock_notify = Lock()

        self.activated.connect(self.handle_click)
        self.set_default_tooltip()

        self.manage_window = manage_window

    def set_default_tooltip(self):
        self.setToolTip('{} ({})'.format(self.locale_keys['manage_window.title'], __app_name__).lower())

    def handle_click(self, reason):
        if reason == self.Trigger:
            self.show_manage_window()

    def verify_updates(self, notify_user: bool = True):
        Thread(target=self._verify_updates, args=(notify_user,)).start()

    def _verify_updates(self, notify_user: bool):
        self.notify_updates(self.manager.list_updates(), notify_user=notify_user)

    def notify_updates(self, updates: List[ApplicationUpdate], notify_user: bool = True):

        self.lock_notify.acquire()

        try:
            if len(updates) > 0:
                update_keys = {'{}:{}:{}'.format(up.type, up.id, up.version) for up in updates}

                new_icon = self.icon_update

                if update_keys.difference(self.last_updates):
                    self.last_updates = update_keys
                    msg = '{}: {}'.format(self.locale_keys['notification.new_updates'], len(updates))
                    self.setToolTip(msg)

                    if self.update_notification and notify_user:
                        system.notify_user(msg)

            else:
                self.last_updates.clear()
                new_icon = self.icon_default
                self.set_default_tooltip()

            if self.icon().cacheKey() != new_icon.cacheKey():  # changes the icon if needed
                self.setIcon(new_icon)

        finally:
            self.lock_notify.release()

    def show_manage_window(self):
        if self.manage_window.isMinimized():
            self.manage_window.setWindowState(Qt.WindowNoState)
        elif not self.manage_window.isVisible():
            self.manage_window.refresh_apps()
            self.manage_window.show()

    def show_about(self):

        if self.dialog_about is None:
            self.dialog_about = AboutDialog(self.locale_keys)

        if self.dialog_about.isHidden():
            self.dialog_about.show()
