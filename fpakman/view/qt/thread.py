import time
from datetime import datetime, timedelta
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal

from fpakman.core.controller import ApplicationManager
from fpakman.core.model import ApplicationStatus
from fpakman.util.cache import Cache
from fpakman.view.qt import dialog
from fpakman.view.qt.view_model import ApplicationView


class UpdateSelectedApps(QThread):

    signal_finished = pyqtSignal()
    signal_output = pyqtSignal(str)

    def __init__(self, manager: ApplicationManager, apps_to_update: List[ApplicationView] = None):
        super(UpdateSelectedApps, self).__init__()
        self.apps_to_update = apps_to_update
        self.manager = manager

    def run(self):

        for app in self.apps_to_update:
            for output in self.manager.update_and_stream(app.model):
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

        self.signal_finished.emit()


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
            for output in self.manager.uninstall_and_stream(self.app.model):
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

            self.icon_cache.delete(self.app.model.base_data.icon_url)
            self.manager.clean_cache_for(self.app.model)
            self.signal_finished.emit()


class DowngradeApp(QThread):
    signal_finished = pyqtSignal()
    signal_output = pyqtSignal(str)

    def __init__(self, manager: ApplicationManager, locale_keys: dict, app: ApplicationView = None):
        super(DowngradeApp, self).__init__()
        self.manager = manager
        self.app = app
        self.locale_keys = locale_keys
        self.root_password = None

    def run(self):
        if self.app:

            stream = self.manager.downgrade_app(self.app.model, self.root_password)

            if stream is None:
                dialog.show_error(title=self.locale_keys['popup.downgrade.impossible.title'],
                                  body=self.locale_keys['popup.downgrade.impossible.body'])
            else:
                for output in self.manager.downgrade_app(self.app.model, self.root_password):
                    line = output.decode().strip()
                    if line:
                        self.signal_output.emit(line)

            self.app = None
            self.root_password = None
            self.signal_finished.emit()


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

    def __init__(self, manager: ApplicationManager, app: ApplicationView = None):
        super(GetAppHistory, self).__init__()
        self.app = app
        self.manager = manager

    def run(self):
        if self.app:
            self.signal_finished.emit({'model': self.app.model, 'history': self.manager.get_history(self.app.model)})
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

    signal_finished = pyqtSignal()
    signal_output = pyqtSignal(str)

    def __init__(self, manager: ApplicationManager, app: ApplicationView = None):
        super(InstallApp, self).__init__()
        self.app = app
        self.manager = manager

    def run(self):

        if self.app:
            for output in self.manager.install_and_stream(self.app.model):
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

        self.app = None
        self.signal_finished.emit()


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
