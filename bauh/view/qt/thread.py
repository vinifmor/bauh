import os
import re
import time
from datetime import datetime, timedelta
from functools import reduce
from operator import add
from typing import List, Type, Set, Tuple

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import PackageStatus, SoftwarePackage, CustomSoftwareAction
from bauh.api.abstract.view import MessageType, MultipleSelectComponent, InputOption, TextComponent, \
    FormComponent, ViewComponent
from bauh.api.exception import NoInternetException
from bauh.commons import user
from bauh.commons.html import bold
from bauh.commons.system import get_human_size_str
from bauh.view.core import config
from bauh.view.qt import commons
from bauh.view.qt.view_model import PackageView, PackageViewStatus
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
    signal_root_password = pyqtSignal()
    signal_progress_control = pyqtSignal(bool)

    def __init__(self):
        super(AsyncAction, self).__init__()
        self.wait_confirmation = False
        self.confirmation_res = None
        self.root_password = None
        self.stop = False

    def request_confirmation(self, title: str, body: str, components: List[ViewComponent] = None, confirmation_label: str = None, deny_label: str = None, deny_button: bool = True) -> bool:
        self.wait_confirmation = True
        self.signal_confirmation.emit({'title': title, 'body': body, 'components': components, 'confirmation_label': confirmation_label, 'deny_label': deny_label, 'deny_button': deny_button})
        self.wait_user()
        return self.confirmation_res

    def request_root_password(self) -> Tuple[str, bool]:
        self.wait_confirmation = True
        self.signal_root_password.emit()
        self.wait_user()
        res = self.root_password
        self.root_password = None
        return res

    def confirm(self, res: bool):
        self.confirmation_res = res
        self.wait_confirmation = False

    def set_root_password(self, password: str, valid: bool):
        self.root_password = (password, valid)
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

    def enable_progress_controll(self):
        self.signal_progress_control.emit(True)

    def disable_progress_controll(self):
        self.signal_progress_control.emit(False)


class UpdateSelectedPackages(AsyncAction):

    def __init__(self, manager: SoftwareManager, i18n: I18n, pkgs: List[PackageView] = None):
        super(UpdateSelectedPackages, self).__init__()
        self.pkgs = pkgs
        self.manager = manager
        self.i18n = i18n

    def _pkg_as_option(self, pkg: SoftwarePackage, tooltip: bool = True) -> InputOption:
        if pkg.installed:
            icon_path = pkg.get_disk_icon_path()

            if not icon_path or not os.path.isfile(icon_path):
                icon_path = pkg.get_type_icon_path()

        else:
            icon_path = pkg.get_type_icon_path()

        label = '{}{} - {}: {}'.format(pkg.name,
                                       ' ( {} )'.format(pkg.latest_version) if pkg.latest_version else '',
                                       self.i18n['size'].capitalize(),
                                       '?' if pkg.size is None else get_human_size_str(pkg.size))

        return InputOption(label=label,
                           value=None,
                           tooltip=pkg.get_name_tooltip() if tooltip else None,
                           read_only=True,
                           icon_path=icon_path)

    def _sort_packages(self, pkgs: List[SoftwarePackage], app_config: dict) -> List[SoftwarePackage]:
        if bool(app_config['updates']['sort_packages']):
            self.change_substatus(self.i18n['action.update.status.sorting'])
            return self.manager.sort_update_order([view.model for view in self.pkgs])

        return pkgs

    def filter_to_update(self) -> Tuple[List[PackageView], bool]:  # packages to update and if they require root privileges
        to_update, requires_root = [], False
        root_user = user.is_root()

        for app_v in self.pkgs:
            if app_v.update_checked:
                to_update.append(app_v)

            if not root_user and not requires_root and self.manager.requires_root('update', app_v.model):
                requires_root = True

        return to_update, requires_root

    def _sum_pkgs_size(self, pkgs: List[SoftwarePackage]) -> int:
        try:
            return reduce(add, ((p.size if p.size is not None else 0) for p in pkgs))
        except:
            return 0

    def _gen_requirements_form(self, reqs: List[SoftwarePackage]) -> Tuple[FormComponent, int]:
        opts = [self._pkg_as_option(p) for p in reqs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]
        size = self._sum_pkgs_size(reqs)

        lb = '{} ( {}: {} )'.format(self.i18n['action.update.required_label'].capitalize(),
                                    self.i18n['size'].capitalize(),
                                    '?' if size is None else get_human_size_str(size))
        return FormComponent(label=lb, components=comps), size

    def _gen_sorted_form(self, pkgs: List[SoftwarePackage]) -> Tuple[FormComponent, int]:
        opts = [self._pkg_as_option(p, tooltip=False) for p in pkgs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]
        size = self._sum_pkgs_size(pkgs)

        lb = '{} ( {}: {} )'.format(self.i18n['action.update.order'].capitalize(),
                                    self.i18n['size'].capitalize(),
                                    '?' if size is None else get_human_size_str(size))

        return FormComponent(label=lb, components=comps), size

    def run(self):
        to_update, requires_root = self.filter_to_update()
        
        root_password = None

        if not user.is_root() and requires_root:
            root_password, ok = self.request_root_password()

            if not ok:
                self.notify_finished({'success': False, 'updated': 0, 'types': set()})
                self.pkgs = None
                return

        if len(to_update) > 1:
            self.disable_progress_controll()
        else:
            self.enable_progress_controll()

        success = False

        updated, updated_types = 0, set()

        app_config = config.read_config()

        models = [view.model for view in to_update]

        required_pkgs = None
        if bool(app_config['updates']['pre_dependency_checking']):
            self.change_substatus(self.i18n['action.update.requirements.status'])
            required_pkgs = self.manager.get_update_requirements(models, self)

        sorted_pkgs = self._sort_packages(models, app_config)

        comps, total_size = [], 0

        self.change_substatus(self.i18n['action.update.status.checking_sizes'])
        self.manager.fill_sizes([*(required_pkgs if required_pkgs else []), *sorted_pkgs])

        if required_pkgs:
            req_form, reqs_size = self._gen_requirements_form(required_pkgs)
            total_size += reqs_size
            comps.append(req_form)

        sorted_form, sorted_size = self._gen_sorted_form(sorted_pkgs)
        total_size += sorted_size
        comps.append(sorted_form)

        if total_size > 0:
            comps.insert(0, TextComponent(bold('{}: {}'.format(self.i18n['action.update.total_size'].capitalize(),
                                                               get_human_size_str(total_size)))))

        if not self.request_confirmation(title=self.i18n['action.update.summary'].capitalize(), body='', components=comps):
            self.notify_finished({'success': success, 'updated': updated, 'types': updated_types})
            self.pkgs = None
            return

        if required_pkgs:
            for pkg in required_pkgs:
                if not self.manager.install(pkg, root_password, self):
                    self.notify_finished({'success': False, 'updated': 0, 'types': set()})
                    self.pkgs = None
                    label = '{}{}'.format(pkg.name, ' ( {} )'.format(pkg.version) if pkg.version else '')
                    self.show_message(title=self.i18n['action.update.install_req.fail.title'],
                                      body=self.i18n['action.update.install_req.fail.body'].format(label),
                                      type_=MessageType.ERROR)
                    return False

        for pkg in sorted_pkgs:
            self.change_substatus('')
            name = pkg.name if not RE_VERSION_IN_NAME.findall(pkg.name) else pkg.name.split('version')[0].strip()

            self.change_status('{} {} {}...'.format(self.i18n['manage_window.status.upgrading'], name, pkg.version))
            success = bool(self.manager.update(pkg, root_password, self))
            self.change_substatus('')

            if not success:
                break
            else:
                updated += 1
                updated_types.add(pkg.__class__)
                self.signal_output.emit('\n')

        self.notify_finished({'success': success, 'updated': updated, 'types': updated_types})
        self.pkgs = None


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


class NotifyPackagesReady(QThread):

    signal_finished = pyqtSignal()
    signal_changed = pyqtSignal(int)

    def __init__(self, pkgs: List[PackageView] = None):
        super(NotifyPackagesReady, self).__init__()
        self.pkgs = pkgs
        self.work = True

    def run(self):
        timeout = datetime.now() + timedelta(seconds=15)

        to_verify = {p.table_index: p for p in self.pkgs}
        while self.work and datetime.now() < timeout:
            to_remove = []
            for idx, pkg in to_verify.items():
                if not self.work:
                    break
                elif pkg.model.status == PackageStatus.READY:
                    to_remove.append(idx)
                    if pkg.status == PackageViewStatus.LOADING:
                        self.signal_changed.emit(pkg.table_index)

            if not self.work:
                break

            if datetime.now() >= timeout:
                break

            for idx in to_remove:
                del to_verify[idx]

            if not to_verify:
                break

            time.sleep(0.1)

        self.pkgs = None
        self.work = True
        self.signal_finished.emit()


class NotifyInstalledLoaded(QThread):
    signal_loaded = pyqtSignal()

    def __init__(self):
        super(NotifyInstalledLoaded, self).__init__()
        self.loaded = False

    def notify_loaded(self):
        self.loaded = True

    def run(self):
        time.sleep(0.1)
        self.signal_loaded.emit()


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

    def __init__(self, manager: SoftwareManager, i18n: I18n, custom_action: CustomSoftwareAction = None, pkg: PackageView = None, root_password: str = None):
        super(CustomAction, self).__init__()
        self.manager = manager
        self.pkg = pkg
        self.custom_action = custom_action
        self.root_password = root_password
        self.i18n = i18n

    def run(self):
        try:
            success = self.manager.execute_custom_action(action=self.custom_action,
                                                         pkg=self.pkg.model if self.pkg else None,
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
