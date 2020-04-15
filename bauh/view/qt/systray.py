import json
import logging
import os
import sys
import time
import traceback
from io import StringIO
from subprocess import Popen
from threading import Lock, Thread
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal, QCoreApplication, QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu

from bauh import __app_name__, ROOT_DIR
from bauh.api.abstract.model import PackageUpdate
from bauh.commons.system import run_cmd
from bauh.context import generate_i18n
from bauh.view.core.tray_client import TRAY_CHECK_FILE
from bauh.view.qt.about import AboutDialog
from bauh.view.qt.view_utils import load_resource_icon
from bauh.view.util import util, resource

CLI_PATH = '{}/bin/bauh-cli'.format(sys.exec_prefix)


def list_updates(logger: logging.Logger) -> List[PackageUpdate]:
    if os.path.exists(CLI_PATH):
        output = run_cmd('{} updates -f json'.format(CLI_PATH))

        if output:
            return [PackageUpdate(pkg_id=o['id'], name=o['name'], version=o['version'], pkg_type=o['type']) for o in json.loads(output)]
        else:
            logger.info("No updates found")

    else:
        logger.warning('bauh-cli seems not to be installed ({})'.format(CLI_PATH))

    return []


class UpdateCheck(QThread):

    signal = pyqtSignal(list)

    def __init__(self, check_interval: int, lock: Lock, check_file: bool, logger: logging.Logger, parent=None):
        super(UpdateCheck, self).__init__(parent)
        self.check_interval = check_interval
        self.lock = lock
        self.check_file = check_file
        self.logger = logger

    def _notify_updates(self):
        self.lock.acquire()
        try:
            updates = list_updates(self.logger)

            if updates is not None:
                self.signal.emit(updates)
        finally:
            self.lock.release()

        time.sleep(self.check_interval)

    def run(self):
        while True:
            if self.check_file:
                if os.path.exists(TRAY_CHECK_FILE):
                    self._notify_updates()
                    try:
                        os.remove(TRAY_CHECK_FILE)
                    except:
                        traceback.print_exc()
                else:
                    time.sleep(self.check_interval)
            else:
                self._notify_updates()


class TrayIcon(QSystemTrayIcon):

    def __init__(self, config: dict, screen_size: QSize, logger: logging.Logger, manage_process: Popen = None, settings_process: Popen = None):
        super(TrayIcon, self).__init__()
        self.i18n = generate_i18n(config, resource.get_path('locale/tray'))
        self.screen_size = screen_size
        self.manage_process = manage_process
        self.settings_process = settings_process
        self.logger = logger

        if config['ui']['tray']['default_icon']:
            self.icon_default = QIcon(config['ui']['tray']['default_icon'])
        else:
            self.icon_default = QIcon.fromTheme('bauh_tray_default')

        if self.icon_default.isNull():
            self.icon_default = load_resource_icon('img/logo.svg', 24)

        if config['ui']['tray']['updates_icon']:
            self.icon_updates = QIcon(config['ui']['tray']['updates_icon'])
        else:
            self.icon_updates = QIcon.fromTheme('bauh_tray_updates')

        if self.icon_updates.isNull():
            self.icon_updates = load_resource_icon('img/logo_update.svg', 24)

        self.setIcon(self.icon_default)

        self.menu = QMenu()

        self.action_manage = self.menu.addAction(self.i18n['tray.action.manage'])
        self.action_manage.triggered.connect(self.show_manage_window)

        self.action_settings = self.menu.addAction(self.i18n['tray.settings'].capitalize())
        self.action_settings.triggered.connect(self.show_settings_window)

        self.action_about = self.menu.addAction(self.i18n['tray.action.about'])
        self.action_about.triggered.connect(self.show_about)

        self.action_exit = self.menu.addAction(self.i18n['tray.action.exit'])
        self.action_exit.triggered.connect(lambda: QCoreApplication.exit())

        self.setContextMenu(self.menu)

        self.manage_window = None
        self.dialog_about = None
        self.settings_window = None

        self.check_lock = Lock()
        self.check_thread = UpdateCheck(check_interval=int(config['updates']['check_interval']), check_file=False, lock=self.check_lock, logger=logger)
        self.check_thread.signal.connect(self.notify_updates)
        self.check_thread.start()

        self.recheck_thread = UpdateCheck(check_interval=2, check_file=True, lock=self.check_lock, logger=logger)
        self.recheck_thread.signal.connect(self.notify_updates)
        self.recheck_thread.start()

        self.last_updates = set()
        self.update_notification = bool(config['system']['notifications'])
        self.lock_notify = Lock()

        self.activated.connect(self.handle_click)
        self.set_default_tooltip()

    def set_default_tooltip(self):
        self.setToolTip('{} ({})'.format(self.i18n['tray.action.manage'], __app_name__).lower())

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
                self.logger.info("{} updates available".format(len(updates)))
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
                        for ptype in sorted(ups_by_type):
                            msg.write('\n  * {} ( {} )'.format(ptype, ups_by_type[ptype]))

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
        if self.manage_process is None:
            self.manage_process = Popen([sys.executable, '{}/app.py'.format(ROOT_DIR)])
        elif self.manage_process.poll() is not None:  # it means it has finished
            self.manage_process = None
            self.show_manage_window()

    def show_settings_window(self):
        if self.settings_process is None:
            self.settings_process = Popen([sys.executable, '{}/app.py'.format(ROOT_DIR), '--settings'])
        elif self.settings_process.poll() is not None:  # it means it has finished
            self.settings_process = None
            self.show_settings_window()

    def show_about(self):
        if self.dialog_about is None:
            self.dialog_about = AboutDialog(self.i18n)

        if self.dialog_about.isHidden():
            self.dialog_about.show()
