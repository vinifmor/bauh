import time
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal, QCoreApplication, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu

from fpakman.core import resource, system
from fpakman.core.controller import FlatpakManager
from fpakman.view.qt.about import AboutDialog
from fpakman.view.qt.window import ManageWindow


class UpdateCheck(QThread):

    signal = pyqtSignal(list)

    def __init__(self, manager: FlatpakManager, check_interval: int, parent=None):
        super(UpdateCheck, self).__init__(parent)
        self.check_interval = check_interval
        self.manager = manager

    def run(self):

        while True:

            apps = self.manager.read_installed()

            updates = [app for app in apps if app['update']]

            if updates:
                self.signal.emit(updates)

            time.sleep(self.check_interval)


class LoadDatabase(QThread):

    signal_finished = pyqtSignal()

    def __init__(self, manager: FlatpakManager, parent=None):
        super(LoadDatabase, self).__init__(parent)
        self.manager = manager

    def run(self):
        self.manager.load_full_database()
        self.signal_finished.emit()


class TrayIcon(QSystemTrayIcon):

    def __init__(self, locale_keys: dict, manager: FlatpakManager, check_interval: int = 60, update_notification: bool = True):
        super(TrayIcon, self).__init__()
        self.locale_keys = locale_keys
        self.manager = manager

        self.icon_default = QIcon(resource.get_path('img/logo.png'))
        self.icon_update = QIcon(resource.get_path('img/logo_update.png'))
        self.setIcon(self.icon_default)

        self.menu = QMenu()

        self.action_refreshing = self.menu.addAction(self.locale_keys['tray.action.refreshing'] + '...')
        self.action_refreshing.setEnabled(False)

        self.action_manage = self.menu.addAction(self.locale_keys['tray.action.manage'])
        self.action_manage.triggered.connect(self.show_manage_window)
        self.action_manage.setVisible(False)

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

        self.thread_database = LoadDatabase(manager)
        self.thread_database.signal_finished.connect(self._update_menu)
        self.last_updates = set()
        self.update_notification = update_notification

    def load_database(self):
        self.thread_database.start()

    def _update_menu(self):
        self.action_refreshing.setVisible(False)
        self.action_manage.setVisible(True)

    def notify_updates(self, updates: List[dict]):

        if len(updates) > 0:

            update_keys = {'{}:{}'.format(app['id'], app['latest_version']) for app in updates}

            new_icon = self.icon_update

            if update_keys.difference(self.last_updates):
                self.last_updates = update_keys
                msg = '{}: {}'.format(self.locale_keys['notification.new_updates'].format('Flatpak'), len(updates))
                self.setToolTip(msg)

                if self.update_notification:
                    system.notify_user(msg)

        else:
            new_icon = self.icon_default
            self.setToolTip(None)

        if self.icon().cacheKey() != new_icon.cacheKey():  # changes the icon if needed
            self.setIcon(new_icon)

    def show_manage_window(self):

        if self.manage_window is None:
            self.manage_window = ManageWindow(locale_keys=self.locale_keys,
                                              manager=self.manager,
                                              tray_icon=self)

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
