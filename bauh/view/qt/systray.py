import os
import time
from io import StringIO
from threading import Lock, Thread
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal, QCoreApplication, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu

from bauh import __app_name__
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.model import PackageUpdate
from bauh.view.util import util, resource
from bauh.view.qt.about import AboutDialog
from bauh.view.qt.window import ManageWindow
from bauh.view.util.translation import I18n


class UpdateCheck(QThread):

    signal = pyqtSignal(list)

    def __init__(self, manager: SoftwareManager, check_interval: int, parent=None):
        super(UpdateCheck, self).__init__(parent)
        self.check_interval = check_interval
        self.manager = manager

    def run(self):

        while True:
            updates = self.manager.list_updates()
            self.signal.emit(updates)
            time.sleep(self.check_interval)


class TrayIcon(QSystemTrayIcon):

    def __init__(self, i18n: I18n, manager: SoftwareManager, manage_window: ManageWindow, config: dict):
        super(TrayIcon, self).__init__()
        self.i18n = i18n
        self.manager = manager

        if config['ui']['tray']['default_icon']:
            self.icon_default = QIcon(config['ui']['tray']['default_icon'])
        else:
            self.icon_default = QIcon.fromTheme('bauh_tray_default')

        if self.icon_default.isNull():
            self.icon_default = QIcon(resource.get_path('img/logo.png'))

        if config['ui']['tray']['updates_icon']:
            self.icon_updates = QIcon(config['ui']['tray']['updates_icon'])
        else:
            self.icon_updates = QIcon.fromTheme('bauh_tray_updates')

        if self.icon_updates.isNull():
            self.icon_updates = QIcon(resource.get_path('img/logo_update.png'))

        self.setIcon(self.icon_default)

        self.menu = QMenu()

        self.action_manage = self.menu.addAction(self.i18n['tray.action.manage'])
        self.action_manage.triggered.connect(self.show_manage_window)

        self.action_about = self.menu.addAction(self.i18n['tray.action.about'])
        self.action_about.triggered.connect(self.show_about)

        self.action_exit = self.menu.addAction(self.i18n['tray.action.exit'])
        self.action_exit.triggered.connect(lambda: QCoreApplication.exit())

        self.setContextMenu(self.menu)

        self.manage_window = None
        self.dialog_about = None
        self.check_thread = UpdateCheck(check_interval=int(config['updates']['check_interval']), manager=self.manager)
        self.check_thread.signal.connect(self.notify_updates)
        self.check_thread.start()

        self.last_updates = set()
        self.update_notification = bool(config['system']['notifications'])
        self.lock_notify = Lock()

        self.activated.connect(self.handle_click)
        self.set_default_tooltip()

        self.manage_window = manage_window

    def set_default_tooltip(self):
        self.setToolTip('{} ({})'.format(self.i18n['manage_window.title'], __app_name__).lower())

    def handle_click(self, reason):
        if reason == self.Trigger:
            self.show_manage_window()

    def verify_updates(self, notify_user: bool = True):
        Thread(target=self._verify_updates, args=(notify_user,)).start()

    def _verify_updates(self, notify_user: bool):
        self.notify_updates(self.manager.list_updates(), notify_user=notify_user)

    def notify_updates(self, updates: List[PackageUpdate], notify_user: bool = True):

        self.lock_notify.acquire()

        try:
            if len(updates) > 0:
                update_keys = {'{}:{}:{}'.format(up.type, up.id, up.version) for up in updates}

                new_icon = self.icon_updates

                if update_keys.difference(self.last_updates):
                    self.last_updates = update_keys
                    n_updates = len(updates)
                    ups_by_type = {}

                    for key in update_keys:
                        ptype = key.split(':')[0]
                        count = ups_by_type.get(ptype)
                        count = 1 if count is None else count + 1
                        ups_by_type[ptype] = count

                    msg = StringIO()
                    msg.write(self.i18n['notification.update{}'.format('' if n_updates == 1 else 's')].format(n_updates))

                    if len(ups_by_type) > 1:
                        for ptype, count in ups_by_type.items():
                            msg.write('\n  * {} ( {} )'.format(ptype.capitalize(), count))

                    msg.seek(0)
                    msg = msg.read()
                    self.setToolTip(msg)

                    if self.update_notification and notify_user:
                        util.notify_user(msg=msg)

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
            self.dialog_about = AboutDialog(self.i18n)

        if self.dialog_about.isHidden():
            self.dialog_about.show()
