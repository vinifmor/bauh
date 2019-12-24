import re
import time
from datetime import datetime, timedelta
from typing import List, Type, Set

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import PackageStatus, SoftwarePackage, PackageAction
from bauh.api.abstract.view import InputViewComponent, MessageType
from bauh.api.exception import NoInternetException
from bauh.view.qt import commons
from bauh.view.qt.view_model import PackageView
from bauh.view.util.translation import I18n

RE_VERSION_IN_NAME = re.compile(r'\s+version\s+[\w\.]+\s*$')


class AsyncAction(QThread, ProcessWatcher):

    signal_output = pyqtSignal(str)  # print messages to the terminal widget
    signal_confirmation = pyqtSignal(dict)  # asks the users to confirm something
    signal_finished = pyqtSignal(object)  # informs the main window that the action has finished
    signal_message = pyqtSignal(dict)  # asks the GUI to show an error popup
    signal_status = pyqtSignal(str)  # changes the GUI status message
    signal_substatus = pyqtSignal(str)  # changes the GUI substatus message
    signal_progress = pyqtSignal(int)

    def __init__(self):
        super(AsyncAction, self).__init__()
        self.wait_confirmation = False
        self.confirmation_res = None
        self.stop = False

    def request_confirmation(self, title: str, body: str, components: List[InputViewComponent] = None, confirmation_label: str = None, deny_label: str = None) -> bool:
        self.wait_confirmation = True
        self.signal_confirmation.emit({'title': title, 'body': body, 'components': components, 'confirmation_label': confirmation_label, 'deny_label': deny_label})
        self.wait_user()
        return self.confirmation_res

    def confirm(self, res: bool):
        self.confirmation_res = res
        self.wait_confirmation = False

    def wait_user(self):
        while self.wait_confirmation:
            time.sleep(0.01)

    def print(self, msg: str):
        if msg:
            self.signal_output.emit(msg)

    def show_message(self, title: str, body: str, type_: MessageType = MessageType.INFO):
        self.signal_message.emit({'title': title, 'body': body, 'type': type_})

    def notify_finished(self, res: object):
        self.signal_finished.emit(res)

    def change_status(self, status: str):
        if status:
            self.signal_status.emit(status)

    def change_substatus(self, substatus: str):
        self.signal_substatus.emit(substatus)

    def change_progress(self, val: int):
        if val is not None:
            self.signal_progress.emit(val)

    def should_stop(self):
        return self.stop


class UpdateSelectedApps(AsyncAction):

    def __init__(self, manager: SoftwareManager, i18n: I18n, apps_to_update: List[PackageView] = None):
        super(UpdateSelectedApps, self).__init__()
        self.apps_to_update = apps_to_update
        self.manager = manager
        self.root_password = None
        self.i18n = i18n

    def run(self):

        success = False

        if self.apps_to_update:
            updated, updated_types = 0, set()
            for app in self.apps_to_update:

                name = app.model.name if not RE_VERSION_IN_NAME.findall(app.model.name) else app.model.name.split('version')[0].strip()

                self.change_status('{} {} {}...'.format(self.i18n['manage_window.status.upgrading'], name, app.model.version))
                success = bool(self.manager.update(app.model, self.root_password, self))
                self.change_substatus('')

                if not success:
                    break
                else:
                    updated += 1
                    updated_types.add(app.model.__class__)
                    self.signal_output.emit('\n')

            self.notify_finished({'success': success, 'updated': updated, 'types': updated_types})

        self.apps_to_update = None


class RefreshApps(AsyncAction):

    def __init__(self, manager: SoftwareManager, app: PackageView = None, pkg_types: Set[Type[SoftwarePackage]] = None):
        super(RefreshApps, self).__init__()
        self.manager = manager
        self.app = app  # app that should be on list top
        self.pkg_types = pkg_types

    def run(self):
        res = self.manager.read_installed(pkg_types=self.pkg_types)
        refreshed_types = set()

        if res:
            idx_found, app_found = None, None
            for idx, ins in enumerate(res.installed):
                if self.pkg_types:
                    refreshed_types.add(ins.__class__)

                if self.app and ins.get_type() == self.app.model.get_type() and ins.id == self.app.model.id:
                    idx_found = idx
                    app_found = ins
                    break

            if app_found:
                del res.installed[idx_found]
                res.installed.insert(0, app_found)

        elif self.pkg_types:
            refreshed_types = self.pkg_types

        self.notify_finished({'installed': res.installed, 'total': res.total, 'types': refreshed_types})
        self.app = None
        self.pkg_types = None


class UninstallApp(AsyncAction):

    def __init__(self, manager: SoftwareManager, icon_cache: MemoryCache, app: PackageView = None):
        super(UninstallApp, self).__init__()
        self.app = app
        self.manager = manager
        self.icon_cache = icon_cache
        self.root_password = None

    def run(self):
        if self.app:
            success = self.manager.uninstall(self.app.model, self.root_password, self)

            if success:
                self.icon_cache.delete(self.app.model.icon_url)
                self.manager.clean_cache_for(self.app.model)

            self.notify_finished(self.app if success else None)
            self.app = None
            self.root_password = None


class DowngradeApp(AsyncAction):

    def __init__(self, manager: SoftwareManager, i18n: I18n, app: PackageView = None):
        super(DowngradeApp, self).__init__()
        self.manager = manager
        self.app = app
        self.i18n = i18n
        self.root_password = None

    def run(self):
        if self.app:
            success = False
            try:
                success = self.manager.downgrade(self.app.model, self.root_password, self)
            except (requests.exceptions.ConnectionError, NoInternetException) as e:
                success = False
                self.print(self.i18n['internet.required'])
            finally:
                self.notify_finished({'app': self.app, 'success': success})
                self.app = None
                self.root_password = None


class GetAppInfo(AsyncAction):

    def __init__(self, manager: SoftwareManager, app: PackageView = None):
        super(GetAppInfo, self).__init__()
        self.app = app
        self.manager = manager

    def run(self):
        if self.app:
            info = {'__app__': self.app}
            info.update(self.manager.get_info(self.app.model))
            self.notify_finished(info)
            self.app = None


class GetAppHistory(AsyncAction):

    def __init__(self, manager: SoftwareManager, i18n: I18n, app: PackageView = None):
        super(GetAppHistory, self).__init__()
        self.app = app
        self.manager = manager
        self.i18n = i18n

    def run(self):
        if self.app:
            try:
                self.notify_finished({'history': self.manager.get_history(self.app.model)})
            except (requests.exceptions.ConnectionError, NoInternetException) as e:
                self.notify_finished({'error': self.i18n['internet.required']})
            finally:
                self.app = None


class SearchPackages(AsyncAction):

    def __init__(self, manager: SoftwareManager):
        super(SearchPackages, self).__init__()
        self.word = None
        self.manager = manager

    def run(self):
        search_res = {'pkgs_found': [], 'error': None}

        if self.word:
            try:
                res = self.manager.search(self.word)
                search_res['pkgs_found'].extend(res.installed)
                search_res['pkgs_found'].extend(res.new)
            except NoInternetException:
                search_res['error'] = 'internet.required'
            finally:
                self.notify_finished(search_res)
                self.word = None


class InstallPackage(AsyncAction):

    def __init__(self, manager: SoftwareManager, disk_cache: bool, icon_cache: MemoryCache, i18n: I18n, pkg: PackageView = None):
        super(InstallPackage, self).__init__()
        self.pkg = pkg
        self.manager = manager
        self.icon_cache = icon_cache
        self.disk_cache = disk_cache
        self.i18n = i18n
        self.root_password = None

    def run(self):
        if self.pkg:
            success = False

            try:
                success = self.manager.install(self.pkg.model, self.root_password, self)

                if success and self.disk_cache:
                    self.pkg.model.installed = True

                    if self.pkg.model.supports_disk_cache():
                        icon_data = self.icon_cache.get(self.pkg.model.icon_url)
                        self.manager.cache_to_disk(pkg=self.pkg.model,
                                                   icon_bytes=icon_data.get('bytes') if icon_data else None,
                                                   only_icon=False)
            except (requests.exceptions.ConnectionError, NoInternetException):
                success = False
                self.print(self.i18n['internet.required'])
            finally:
                self.signal_finished.emit({'success': success, 'pkg': self.pkg})
                self.pkg = None


class AnimateProgress(QThread):

    signal_change = pyqtSignal(int)

    def __init__(self):
        super(AnimateProgress, self).__init__()
        self.progress_value = 0
        self.increment = 5
        self.stop = False
        self.limit = 100
        self.sleep = 0.05
        self.last_progress = 0
        self.manual = False
        self.paused = False

    def _reset(self):
        self.progress_value = 0
        self.increment = 5
        self.stop = False
        self.limit = 100
        self.sleep = 0.05
        self.last_progress = 0
        self.manual = False
        self.paused = False

    def set_progress(self, val: int):
        if 0 <= val <= 100:
            self.limit = val
            self.manual = True
            self.increment = 0.5
            self.paused = False

    def pause(self):
        self.paused = True

    def animate(self):
        self.paused = False

    def run(self):

        current_increment = self.increment

        while not self.stop:
            if not self.paused:
                if self.progress_value != self.last_progress:
                    self.signal_change.emit(self.progress_value)
                    self.last_progress = self.progress_value

                if not self.manual:
                    if self.progress_value >= self.limit:
                        current_increment = -self.increment
                    elif self.progress_value <= 0:
                        current_increment = self.increment
                else:
                    if self.progress_value >= self.limit:
                        current_increment = 0
                    else:
                        current_increment = self.increment

                self.progress_value += current_increment

            time.sleep(self.sleep)

        self.signal_change.emit(100)
        self._reset()


class VerifyModels(QThread):

    signal_updates = pyqtSignal()

    def __init__(self, apps: List[PackageView] = None):
        super(VerifyModels, self).__init__()
        self.apps = apps
        self.work = True

    def run(self):

        if self.apps:

            stop_at = datetime.utcnow() + timedelta(seconds=30)
            last_ready = 0

            while True:

                if not self.work:
                    break

                current_ready = 0

                for app in self.apps:
                    current_ready += 1 if app.model.status == PackageStatus.READY else 0

                if current_ready > last_ready:
                    last_ready = current_ready
                    self.signal_updates.emit()

                if current_ready == len(self.apps):
                    self.signal_updates.emit()
                    break

                if stop_at <= datetime.utcnow():
                    break

                time.sleep(0.1)

        self.work = True
        self.apps = None


class FindSuggestions(AsyncAction):

    def __init__(self, man: SoftwareManager):
        super(FindSuggestions, self).__init__()
        self.man = man
        self.filter_installed = False

    def run(self):
        sugs = self.man.list_suggestions(limit=-1, filter_installed=self.filter_installed)
        self.notify_finished({'pkgs_found': [s.package for s in sugs] if sugs is not None else [], 'error': None})


class ListWarnings(QThread):

    signal_warnings = pyqtSignal(list)

    def __init__(self, man: SoftwareManager, i18n: I18n):
        super(QThread, self).__init__()
        self.i18n = i18n
        self.man = man

    def run(self):
        warnings = self.man.list_warnings()
        if warnings:
            self.signal_warnings.emit(warnings)


class LaunchApp(AsyncAction):

    def __init__(self, manager: SoftwareManager, app: PackageView = None):
        super(LaunchApp, self).__init__()
        self.app = app
        self.manager = manager

    def run(self):

        if self.app:
            try:
                time.sleep(0.25)
                self.manager.launch(self.app.model)
                self.notify_finished(True)
            except:
                self.notify_finished(False)


class ApplyFilters(AsyncAction):

    signal_table = pyqtSignal(object)

    def __init__(self, filters: dict = None, pkgs: List[PackageView] = None):
        super(ApplyFilters, self).__init__()
        self.pkgs = pkgs
        self.filters = filters
        self.wait_table_update = False

    def stop_waiting(self):
        self.wait_table_update = False

    def run(self):
        if self.pkgs:
            pkgs_info = commons.new_pkgs_info()

            for pkgv in self.pkgs:
                commons.update_info(pkgv, pkgs_info)
                commons.apply_filters(pkgv, self.filters, pkgs_info)

            self.wait_table_update = True
            self.signal_table.emit(pkgs_info)

            while self.wait_table_update:
                time.sleep(0.005)

        self.notify_finished(True)


class CustomAction(AsyncAction):

    def __init__(self, manager: SoftwareManager, i18n: I18n, custom_action: PackageAction = None, pkg: PackageView = None, root_password: str = None):
        super(CustomAction, self).__init__()
        self.manager = manager
        self.pkg = pkg
        self.custom_action = custom_action
        self.root_password = root_password
        self.i18n = i18n

    def run(self):
        success = True
        if self.pkg:
            try:
                success = self.manager.execute_custom_action(action=self.custom_action,
                                                             pkg=self.pkg.model,
                                                             root_password=self.root_password,
                                                             watcher=self)
            except (requests.exceptions.ConnectionError, NoInternetException):
                success = False
                self.signal_output.emit(self.i18n['internet.required'])

        self.notify_finished({'success': success, 'pkg': self.pkg})
        self.pkg = None
        self.custom_action = None
        self.root_password = None


class GetScreenshots(AsyncAction):

    def __init__(self, manager: SoftwareManager, pkg: PackageView = None):
        super(GetScreenshots, self).__init__()
        self.pkg = pkg
        self.manager = manager

    def run(self):
        if self.pkg:
            self.notify_finished({'pkg': self.pkg, 'screenshots': self.manager.get_screenshots(self.pkg.model)})

        self.pkg = None
