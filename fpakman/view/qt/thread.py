import time

from PyQt5.QtCore import QThread, pyqtSignal

from fpakman.core import flatpak
from fpakman.core.controller import FlatpakManager
from fpakman.view.qt import dialog


class UpdateSelectedApps(QThread):

    signal_finished = pyqtSignal()
    signal_output = pyqtSignal(str)

    def __init__(self):
        super(UpdateSelectedApps, self).__init__()
        self.refs_to_update = []

    def run(self):

        for app_ref in self.refs_to_update:
            for output in flatpak.update_and_stream(app_ref):
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

        self.signal_finished.emit()


class RefreshApps(QThread):

    signal = pyqtSignal(list)

    def __init__(self, manager: FlatpakManager):
        super(RefreshApps, self).__init__()
        self.manager = manager

    def run(self):
        self.signal.emit(self.manager.read_installed())


class UninstallApp(QThread):
    signal_finished = pyqtSignal()
    signal_output = pyqtSignal(str)

    def __init__(self):
        super(UninstallApp, self).__init__()
        self.app_ref = None

    def run(self):
        if self.app_ref:
            for output in flatpak.uninstall_and_stream(self.app_ref):
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

            self.signal_finished.emit()


class DowngradeApp(QThread):
    signal_finished = pyqtSignal()
    signal_output = pyqtSignal(str)

    def __init__(self, manager: FlatpakManager, locale_keys: dict):
        super(DowngradeApp, self).__init__()
        self.manager = manager
        self.app = None
        self.root_password = None
        self.locale_keys = locale_keys

    def run(self):
        if self.app:

            stream = self.manager.downgrade_app(self.app['model'], self.root_password)

            if stream is None:
                dialog.show_error(title=self.locale_keys['popup.downgrade.impossible.title'],
                                  body=self.locale_keys['popup.downgrade.impossible.body'])
            else:
                for output in self.manager.downgrade_app(self.app['model'], self.root_password):
                    line = output.decode().strip()
                    if line:
                        self.signal_output.emit(line)

            self.app = None
            self.root_password = None
            self.signal_finished.emit()


class GetAppInfo(QThread):
    signal_finished = pyqtSignal(dict)

    def __init__(self):
        super(GetAppInfo, self).__init__()
        self.app = None

    def run(self):
        if self.app:
            app_info = flatpak.get_app_info_fields(self.app['model']['id'], self.app['model']['branch'])
            app_info['name'] = self.app['model']['name']
            app_info['type'] = 'runtime' if self.app['model']['runtime'] else 'app'
            app_info['description'] = self.app['model']['description']
            self.signal_finished.emit(app_info)
            self.app = None


class GetAppHistory(QThread):
    signal_finished = pyqtSignal(dict)

    def __init__(self):
        super(GetAppHistory, self).__init__()
        self.app = None

    def run(self):
        if self.app:
            commits = flatpak.get_app_commits_data(self.app['model']['ref'], self.app['model']['origin'])
            self.signal_finished.emit({'model': self.app['model'], 'commits': commits})
            self.app = None


class SearchApps(QThread):
    signal_finished = pyqtSignal(list)

    def __init__(self, manager: FlatpakManager):
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

    def __init__(self):
        super(InstallApp, self).__init__()
        self.app = None

    def run(self):

        if self.app:
            for output in flatpak.install_and_stream(self.app['model']['id'], self.app['model']['origin']):
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
