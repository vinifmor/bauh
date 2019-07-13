import time
from datetime import datetime, timedelta
from typing import List

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from fpakman.core.controller import ApplicationManager
from fpakman.core.exception import NoInternetException
from fpakman.core.model import ApplicationStatus
from fpakman.util.cache import Cache
from fpakman.view.qt import dialog
from fpakman.view.qt.view_model import ApplicationView


class UpdateSelectedApps(QThread):

    signal_finished = pyqtSignal(bool)
    signal_output = pyqtSignal(str)

    def __init__(self, manager: ApplicationManager, apps_to_update: List[ApplicationView] = None):
        super(UpdateSelectedApps, self).__init__()
        self.apps_to_update = apps_to_update
        self.manager = manager

    def run(self):

        error = False

        for app in self.apps_to_update:

            subproc = self.manager.update_and_stream(app.model)

            self.signal_output.emit(' '.join(subproc.args) + '\n')

            for output in subproc.stdout:
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

            for output in subproc.stderr:
                line = output.decode().strip()
                if line:
                    error = True
                    self.signal_output.emit(line)

            self.signal_output.emit('\n')

            if error:
                break

        self.signal_finished.emit(not error)


class RefreshApps(QThread):

    signal = pyqtSignal(list)

    def __init__(self, manager: ApplicationManager):
        super(RefreshApps, self).__init__()
        self.manager = manager

    def run(self):
        self.signal.emit(self.manager.read_installed())


class UninstallApp(QThread):
    signal_finished = pyqtSignal()
    signal_output = pyqtSignal(str)

    def __init__(self, manager: ApplicationManager, icon_cache: Cache, app: ApplicationView = None):
        super(UninstallApp, self).__init__()
        self.app = app
        self.manager = manager
        self.icon_cache = icon_cache

    def run(self):
        if self.app:
            subproc = self.manager.uninstall_and_stream(self.app.model)
            self.signal_output.emit(' '.join(subproc.args) + '\n')

            for output in subproc.stdout:
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

            error = False

            for output in subproc.stderr:
                line = output.decode().strip()
                if line:
                    error = True
                    self.signal_output.emit(line)

            if not error:
                self.icon_cache.delete(self.app.model.base_data.icon_url)
                self.manager.clean_cache_for(self.app.model)

            self.signal_finished.emit()


class DowngradeApp(QThread):
    signal_finished = pyqtSignal(bool)
    signal_output = pyqtSignal(str)

    def __init__(self, manager: ApplicationManager, locale_keys: dict, app: ApplicationView = None):
        super(DowngradeApp, self).__init__()
        self.manager = manager
        self.app = app
        self.locale_keys = locale_keys
        self.root_password = None

    def run(self):
        if self.app:

            success = True
            try:
                stream = self.manager.downgrade_app(self.app.model, self.root_password)

                if stream is None:
                    dialog.show_error(title=self.locale_keys['popup.downgrade.impossible.title'],
                                      body=self.locale_keys['popup.downgrade.impossible.body'])
                else:
                    for output in stream:
                        line = output.decode().strip()
                        if line:
                            self.signal_output.emit(line)
            except (requests.exceptions.ConnectionError, NoInternetException):
                success = False
                self.signal_output.emit(self.locale_keys['internet.required'])
            finally:
                self.app = None
                self.root_password = None
                self.signal_finished.emit(success)


class GetAppInfo(QThread):
    signal_finished = pyqtSignal(dict)

    def __init__(self, manager: ApplicationManager, app: ApplicationView = None):
        super(GetAppInfo, self).__init__()
        self.app = app
        self.manager = manager

    def run(self):
        if self.app:
            self.signal_finished.emit(self.manager.get_info(self.app.model))
            self.app = None


class GetAppHistory(QThread):
    signal_finished = pyqtSignal(dict)

    def __init__(self, manager: ApplicationManager, locale_keys: dict, app: ApplicationView = None):
        super(GetAppHistory, self).__init__()
        self.app = app
        self.manager = manager
        self.locale_keys = locale_keys

    def run(self):
        if self.app:
            try:
                res = {'model': self.app.model, 'history': self.manager.get_history(self.app.model)}
                self.signal_finished.emit(res)
            except (requests.exceptions.ConnectionError, NoInternetException):
                self.signal_finished.emit({'error': self.locale_keys['internet.required']})
            finally:
                self.app = None


class SearchApps(QThread):
    signal_finished = pyqtSignal(list)

    def __init__(self, manager: ApplicationManager):
        super(SearchApps, self).__init__()
        self.word = None
        self.manager = manager

    def run(self):
        apps_found = []

        if self.word:
            apps_found = self.manager.search(self.word)

        self.signal_finished.emit(apps_found)
        self.word = None


class InstallApp(QThread):

    signal_finished = pyqtSignal(bool)
    signal_output = pyqtSignal(str)

    def __init__(self, manager: ApplicationManager, disk_cache: bool, icon_cache: Cache, app: ApplicationView = None):
        super(InstallApp, self).__init__()
        self.app = app
        self.manager = manager
        self.icon_cache = icon_cache
        self.disk_cache = disk_cache

    def run(self):

        if self.app:
            subproc = self.manager.install_and_stream(self.app.model)
            self.signal_output.emit(' '.join(subproc.args) + '\n')

            for output in subproc.stdout:
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

            error = False

            for output in subproc.stderr:
                line = output.decode().strip()
                if line:
                    error = True
                    self.signal_output.emit(line)

            if not error and self.disk_cache:
                self.app.model.installed = True

                if self.app.model.supports_disk_cache():
                    icon_data = self.icon_cache.get(self.app.model.base_data.icon_url)
                    self.manager.cache_to_disk(app=self.app.model,
                                               icon_bytes=icon_data.get('bytes') if icon_data else None,
                                               only_icon=False)

            self.app = None
            self.signal_finished.emit(not error)


class AnimateProgress(QThread):

    signal_change = pyqtSignal(int)

    def __init__(self):
        super(AnimateProgress, self).__init__()
        self.progress_value = 0
        self.increment = 5
        self.stop = False

    def run(self):

        current_increment = self.increment

        while not self.stop:
            self.signal_change.emit(self.progress_value)

            if self.progress_value == 100:
                current_increment = -current_increment
            if self.progress_value == 0:
                current_increment = self.increment

            self.progress_value += current_increment

            time.sleep(0.05)

        self.progress_value = 0


class VerifyModels(QThread):

    signal_updates = pyqtSignal()

    def __init__(self, apps: List[ApplicationView] = None):
        super(VerifyModels, self).__init__()
        self.apps = apps

    def run(self):

        if self.apps:

            stop_at = datetime.utcnow() + timedelta(seconds=30)
            last_ready = 0

            while True:
                current_ready = 0

                for app in self.apps:
                    current_ready += 1 if app.model.status == ApplicationStatus.READY else 0

                if current_ready > last_ready:
                    last_ready = current_ready
                    self.signal_updates.emit()

                if current_ready == len(self.apps):
                    self.signal_updates.emit()
                    break

                if stop_at <= datetime.utcnow():
                    break

        self.apps = None
