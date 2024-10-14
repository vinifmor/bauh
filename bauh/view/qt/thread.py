import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import StringIO
from logging import Logger
from pathlib import Path
from queue import Queue
from typing import List, Type, Set, Tuple, Optional, Pattern

import requests
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget

from bauh.api import user
from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.controller import SoftwareManager, UpgradeRequirement, UpgradeRequirements, SoftwareAction
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import PackageStatus, SoftwarePackage, CustomSoftwareAction
from bauh.api.abstract.view import MessageType, MultipleSelectComponent, InputOption, TextComponent, \
    FormComponent, ViewComponent
from bauh.api.exception import NoInternetException
from bauh.api.paths import LOGS_DIR
from bauh.commons.html import bold
from bauh.commons.internet import InternetChecker
from bauh.commons.regex import RE_URL
from bauh.commons.system import ProcessHandler, SimpleProcess
from bauh.commons.view_utils import get_human_size_str
from bauh.view.core import timeshift
from bauh.view.core.config import CoreConfigManager, BACKUP_REMOVE_METHODS, BACKUP_DEFAULT_REMOVE_METHOD
from bauh.view.qt import commons
from bauh.view.qt.commons import sort_packages, PackageFilters
from bauh.view.qt.qt_utils import get_current_screen_geometry
from bauh.view.qt.view_index import query_packages
from bauh.view.qt.view_model import PackageView, PackageViewStatus
from bauh.view.util.translation import I18n

RE_VERSION_IN_NAME = re.compile(r'\s+version\s+[\w.]+\s*$')


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

    def __init__(self, i18n: I18n, root_password: Optional[Tuple[bool, str]] = None):
        super(AsyncAction, self).__init__()
        self.i18n = i18n
        self.wait_confirmation = False
        self.confirmation_res = None
        self.root_password = root_password
        self.stop = False

    def request_confirmation(self, title: str, body: str, components: List[ViewComponent] = None,
                             confirmation_label: str = None, deny_label: str = None, deny_button: bool = True,
                             window_cancel: bool = False,
                             confirmation_button: bool = True,
                             min_width: Optional[int] = None,
                             min_height: Optional[int] = None,
                             max_width: Optional[int] = None) -> bool:
        self.wait_confirmation = True
        self.signal_confirmation.emit({'title': title, 'body': body, 'components': components,
                                       'confirmation_label': confirmation_label, 'deny_label': deny_label,
                                       'deny_button': deny_button, 'window_cancel': window_cancel,
                                       'confirmation_button': confirmation_button, 'min_width': min_width,
                                       'min_height': min_height, 'max_width': max_width})
        self.wait_user()
        return self.confirmation_res

    def request_root_password(self) -> Tuple[bool, Optional[str]]:
        self.wait_confirmation = True
        self.signal_root_password.emit()
        self.wait_user()
        res = self.root_password
        self.root_password = None
        return res

    def confirm(self, res: bool):
        self.confirmation_res = res
        self.wait_confirmation = False

    def set_root_password(self, valid: bool, password: str):
        self.root_password = (valid, password)
        self.wait_confirmation = False

    def wait_user(self):
        while self.wait_confirmation:
            self.msleep(10)

    def print(self, msg: str):
        if msg:
            self.signal_output.emit(msg)

    def show_message(self, title: str, body: str, type_: MessageType = MessageType.INFO):
        self.signal_message.emit({'title': title, 'body': body, 'type': type_})

    def notify_finished(self, res: object = None):
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

    def request_reboot(self, msg: str) -> bool:
        if self.request_confirmation(title=self.i18n['action.request_reboot.title'],
                                     body=msg,
                                     confirmation_label=self.i18n['yes'].capitalize(),
                                     deny_label=self.i18n['bt.not_now']):
            ProcessHandler(self).handle_simple(SimpleProcess(['reboot']))
            return True

        return False

    def _generate_backup(self, app_config: dict, root_password: Optional[str]) -> bool:
        if app_config['backup']['mode'] not in ('only_one', 'incremental'):
            self.show_message(title=self.i18n['error'].capitalize(),
                              body='{}: {}'.format(self.i18n['action.backup.invalid_mode'], bold(app_config['backup']['mode'])),
                              type_=MessageType.ERROR)
            self.change_substatus('')
            return False

        handler = ProcessHandler(self)
        if app_config['backup']['mode'] == 'only_one':
            remove_method = app_config['backup']['remove_method']

            if remove_method not in BACKUP_REMOVE_METHODS:
                remove_method = BACKUP_DEFAULT_REMOVE_METHOD

            delete_failed = False

            if remove_method == 'self':
                previous_snapshots = tuple(timeshift.read_created_snapshots(root_password))

                if previous_snapshots:
                    substatus = f"[{self.i18n['core.config.tab.backup'].lower()}] {self.i18n['action.backup.substatus.delete']}"
                    self.change_substatus(substatus)

                    for snapshot in reversed(previous_snapshots):
                        deleted, _ = handler.handle_simple(timeshift.delete(snapshot, root_password))

                        if not deleted:
                            delete_failed = True
            else:
                deleted, _ = handler.handle_simple(timeshift.delete_all_snapshots(root_password))
                delete_failed = not deleted

            if delete_failed and not self.request_confirmation(title=self.i18n['core.config.tab.backup'],
                                                               body=f"{self.i18n['action.backup.error.delete']}. "
                                                                    f"{self.i18n['action.backup.error.proceed']}",
                                                               confirmation_label=self.i18n['yes'].capitalize(),
                                                               deny_label=self.i18n['no'].capitalize()):
                self.change_substatus('')
                return False

        self.change_substatus('[{}] {}'.format(self.i18n['core.config.tab.backup'].lower(), self.i18n['action.backup.substatus.create']))
        created, _ = handler.handle_simple(timeshift.create_snapshot(root_password, app_config['backup']['type']))

        if not created and not self.request_confirmation(title=self.i18n['core.config.tab.backup'],
                                                         body='{}. {}'.format(self.i18n['action.backup.error.create'],
                                                                              self.i18n['action.backup.error.proceed']),
                                                         confirmation_label=self.i18n['yes'].capitalize(),
                                                         deny_label=self.i18n['no'].capitalize()):
            self.change_substatus('')
            return False

        self.change_substatus('')
        return True

    def _check_backup_requirements(self, app_config: dict, pkg: Optional[PackageView], action_key: Optional[str]) -> bool:
        if pkg and not pkg.model.supports_backup():
            return False

        if action_key and app_config['backup'][action_key] is False:
            return False

        return bool(app_config['backup']['enabled']) and timeshift.is_available()

    def _should_backup(self, action_key: str, app_config: dict) -> bool:
        # backup -> true: do not ask, only execute | false: do not ask or execute | None: ask
        backup = app_config['backup'][action_key] if action_key else None

        if backup is None:
            return self.request_confirmation(title=self.i18n['core.config.tab.backup'],
                                             body=self.i18n['action.backup.msg'],
                                             confirmation_label=self.i18n['yes'].capitalize(),
                                             deny_label=self.i18n['no'].capitalize())
        else:
            return backup

    def request_backup(self, action_key: Optional[str], pkg: Optional[PackageView], app_config: dict, root_password: Optional[str], backup_only: bool = False) -> Tuple[bool, Optional[str]]:
        if not backup_only:
            if not self._check_backup_requirements(app_config=app_config, pkg=pkg, action_key=action_key):
                return True, root_password

            if not self._should_backup(action_key=action_key, app_config=app_config):
                return True, root_password

        pwd = root_password
        if not user.is_root() and pwd is None:
            valid_password, pwd = self.request_root_password()

            if not valid_password:
                return False, None

        return self._generate_backup(app_config=app_config, root_password=pwd), pwd


class UpgradeSelected(AsyncAction):

    UPGRADE_LOGS_DIR = f'{LOGS_DIR}/upgrade'
    SUMMARY_FILE = UPGRADE_LOGS_DIR + '/{}_summary.txt'

    def __init__(self, manager: SoftwareManager, internet_checker: InternetChecker, i18n: I18n,
                 parent_widget: QWidget, pkgs: List[PackageView] = None):
        super(UpgradeSelected, self).__init__(i18n=i18n)
        self.pkgs = pkgs
        self.manager = manager
        self.internet_checker = internet_checker
        self._parent_widget = parent_widget

    def _req_as_option(self, req: UpgradeRequirement, tooltip: bool = True, custom_tooltip: str = None, required_size: bool = True, display_sizes: bool = True,
                       positive_size_symbol: bool = False) -> InputOption:
        if req.pkg.installed:
            icon_path = req.pkg.get_disk_icon_path()

            if not icon_path:
                icon_path = req.pkg.get_type_icon_path()
            elif not os.path.isfile(icon_path) or QIcon.fromTheme(icon_path).isNull():
                icon_path = req.pkg.get_type_icon_path()

        else:
            icon_path = req.pkg.get_type_icon_path()

        size_str = None
        if display_sizes:
            storage_size = '?' if req.extra_size is None else get_human_size_str(req.extra_size, positive_size_symbol)
            size_str = f"{self.i18n['action.update.storage_size']}: {storage_size}"
            if required_size and req.extra_size != req.required_size:
                download_size = '?' if req.required_size is None else get_human_size_str(req.required_size)
                size_str += f" ({self.i18n['action.update.download_size']}: {download_size})"

        label = f"{req.pkg.name} {f' ({req.pkg.latest_version})' if req.pkg.latest_version else ''}"

        if size_str:
            label += f' | {size_str}'

        return InputOption(label=label,
                           value=None,
                           tooltip=custom_tooltip if custom_tooltip else (req.pkg.get_name_tooltip() if tooltip else None),
                           read_only=True,
                           icon_path=icon_path)

    def _sum_pkgs_size(self, reqs: List[UpgradeRequirement]) -> Tuple[float, float]:
        required, extra = 0, 0
        for r in reqs:
            if r.required_size is not None:
                required += r.required_size

            if r.extra_size is not None:
                extra += r.extra_size

        return required, extra

    def _gen_cannot_upgrade_form(self, reqs: List[UpgradeRequirement]) -> FormComponent:
        reqs.sort(key=UpgradeRequirement.sort_by_priority)
        opts = [self._req_as_option(req=r, tooltip=False, custom_tooltip=r.reason, display_sizes=False) for r in reqs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]

        return FormComponent(label='{} ({}: {})'.format(self.i18n['action.update.cannot_update_label'],
                                                        self.i18n['amount'].capitalize(), len(opts)),
                             components=comps)

    def _gen_to_install_form(self, reqs: List[UpgradeRequirement]) -> Tuple[FormComponent, Tuple[int, int]]:
        opts = [self._req_as_option(r, custom_tooltip=r.reason, positive_size_symbol=True) for r in reqs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]
        required_size, extra_size = self._sum_pkgs_size(reqs)

        lb = '{} ({}: {} | {}: {} | {}: {})'.format(self.i18n['action.update.required_label'].capitalize(),
                                                    self.i18n['amount'].capitalize(),
                                                    len(opts),
                                                    self.i18n['action.update.storage_size'],
                                                    '?' if extra_size is None else get_human_size_str(extra_size, True),
                                                    self.i18n['action.update.download_size'],
                                                    '?' if required_size is None else get_human_size_str(required_size))
        return FormComponent(label=lb, components=comps), (required_size, extra_size)

    def _gen_to_remove_form(self, reqs: List[UpgradeRequirement]) -> FormComponent:
        opts = [self._req_as_option(r, False, r.reason, required_size=False) for r in reqs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]
        required_size, extra_size = self._sum_pkgs_size(reqs)

        lb = '{} ({}: {} | {}: {})'.format(self.i18n['action.update.label_to_remove'].capitalize(),
                                           self.i18n['amount'].capitalize(),
                                           len(opts),
                                           self.i18n['action.update.storage_size'],
                                           '?' if extra_size is None else get_human_size_str(-extra_size))
        return FormComponent(label=lb, components=comps)

    def _gen_to_update_form(self, reqs: List[UpgradeRequirement]) -> Tuple[FormComponent, Tuple[int, int]]:
        opts = [self._req_as_option(r, tooltip=False, positive_size_symbol=True) for r in reqs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]
        required_size, extra_size = self._sum_pkgs_size(reqs)

        lb = '{} ({}: {} | {}: {} | {}: {})'.format(self.i18n['action.update.label_to_upgrade'].capitalize(),
                                                    self.i18n['amount'].capitalize(),
                                                    len(opts),
                                                    self.i18n['action.update.storage_size'],
                                                    '?' if extra_size is None else get_human_size_str(extra_size, True),
                                                    self.i18n['action.update.download_size'],
                                                    '?' if required_size is None else get_human_size_str(required_size))

        return FormComponent(label=lb, components=comps), (required_size, extra_size)

    def _request_password(self) -> Tuple[bool, Optional[str]]:
        if not user.is_root():
            success, pwd = self.request_root_password()

            if not success:
                return False, None

            return True, pwd

        return True, None

    def _ask_for_trim(self) -> bool:
        return self.request_confirmation(title=self.i18n['confirmation'].capitalize(), body=self.i18n['action.trim_disk.ask'])

    def _trim_disk(self, root_password: Optional[str]):
        self.change_status('{}...'.format(self.i18n['action.disk_trim'].capitalize()))
        self.change_substatus('')

        success, output = ProcessHandler(self).handle_simple(SimpleProcess(['fstrim', '/', '-v'], root_password=root_password))

        if not success:
            self.show_message(title=self.i18n['success'].capitalize(),
                              body=self.i18n['action.disk_trim.error'],
                              type_=MessageType.ERROR)

    def _write_summary_log(self, upgrade_id: str, requirements: UpgradeRequirements):
        try:
            Path(self.UPGRADE_LOGS_DIR).mkdir(parents=True, exist_ok=True)

            summary_text = StringIO()
            summary_text.write('Upgrade summary ( id: {} )'.format(upgrade_id))

            if requirements.cannot_upgrade:
                summary_text.write('\nCannot upgrade:')

                for dep in requirements.cannot_upgrade:
                    type_label = self.i18n.get('gem.{}.type.{}.label'.format(dep.pkg.gem_name, dep.pkg.get_type().lower()), dep.pkg.get_type().capitalize())
                    summary_text.write('\n * Type:{}\tName: {}\tVersion: {}\tReason: {}'.format(type_label, dep.pkg.name, dep.pkg.version if dep.pkg.version else '?', dep.reason if dep.reason else '?'))

                summary_text.write('\n')

            if requirements.to_remove:
                summary_text.write('\nMust be removed:')

                for dep in requirements.to_remove:
                    type_label = self.i18n.get('gem.{}.type.{}.label'.format(dep.pkg.gem_name, dep.pkg.get_type().lower()), dep.pkg.get_type().capitalize())
                    summary_text.write('\n * Type:{}\tName: {}\tVersion: {}\tReason: {}'.format(type_label, dep.pkg.name, dep.pkg.version if dep.pkg.version else '?', dep.reason if dep.reason else '?'))

                summary_text.write('\n')

            if requirements.to_install:
                summary_text.write('\nMust be installed:')

                for dep in requirements.to_install:
                    type_label = self.i18n.get(
                        'gem.{}.type.{}.label'.format(dep.pkg.gem_name, dep.pkg.get_type().lower()),
                        dep.pkg.get_type().capitalize())
                    summary_text.write('\n * Type:{}\tName: {}\tVersion: {}\tReason: {}'.format(type_label,
                                                                                                dep.pkg.name,
                                                                                                dep.pkg.version if dep.pkg.version else '?',
                                                                                                dep.reason if dep.reason else '?'))

                summary_text.write('\n')

            if requirements.to_upgrade:
                summary_text.write('\nWill be upgraded:')

                for dep in requirements.to_upgrade:
                    type_label = self.i18n.get('gem.{}.type.{}.label'.format(dep.pkg.gem_name, dep.pkg.get_type().lower()), dep.pkg.get_type().capitalize())
                    summary_text.write(
                        '\n * Type:{}\tName: {}\tVersion:{} \tNew version: {}'.format(type_label,
                                                                                      dep.pkg.name,
                                                                                      dep.pkg.version if dep.pkg.version else '?',
                                                                                      dep.pkg.latest_version if dep.pkg.latest_version else '?'))

                summary_text.write('\n')

            summary_text.seek(0)

            with open(self.SUMMARY_FILE.format(upgrade_id), 'w+') as f:
                f.write(summary_text.read())

        except Exception:
            traceback.print_exc()

    def _handle_internet_off(self):
        self.pkgs = None
        self.print(self.i18n['internet.required'])
        self.notify_finished({'success': False, 'updated': 0, 'types': set(), 'id': None})

    def run(self):
        if not self.internet_checker.is_available():
            return self._handle_internet_off()

        root_user = user.is_root()
        to_update, upgrade_requires_root, bkp_supported = [], False, False

        for pkg in self.pkgs:
            if pkg.model.update and not pkg.model.is_update_ignored() and pkg.update_checked:
                to_update.append(pkg)

                if not bkp_supported and pkg.model.supports_backup():
                    bkp_supported = True

                if not root_user and not upgrade_requires_root and self.manager.requires_root(SoftwareAction.UPGRADE, pkg.model):
                    upgrade_requires_root = True

        if upgrade_requires_root:
            valid_password, root_password = self._request_password()
        else:
            valid_password, root_password = True, None

        if not valid_password:
            self.notify_finished({'success': False, 'updated': 0, 'types': set(), 'id': None})
            self.pkgs = None
            return

        if len(to_update) > 1:
            self.disable_progress_controll()
        else:
            self.enable_progress_controll()

        success = False

        updated, updated_types = 0, set()

        models = [view.model for view in to_update]

        self.change_substatus(self.i18n['action.update.requirements.status'])
        requirements = self.manager.get_upgrade_requirements(models, root_password, self)

        if not requirements:
            self.pkgs = None
            self.notify_finished({'success': success, 'updated': updated, 'types': updated_types, 'id': None})
            return

        comps, required_size, extra_size = [], 0, 0

        if requirements.cannot_upgrade:
            comps.append(self._gen_cannot_upgrade_form(requirements.cannot_upgrade))

        if requirements.to_install:
            req_form, reqs_size = self._gen_to_install_form(requirements.to_install)
            required_size += reqs_size[0]
            extra_size += reqs_size[1]
            comps.append(req_form)

        if requirements.to_remove:
            comps.append(self._gen_to_remove_form(requirements.to_remove))

        can_upgrade = False
        if requirements.to_upgrade:
            can_upgrade = True
            updates_form, updates_size = self._gen_to_update_form(requirements.to_upgrade)
            required_size += updates_size[0]
            extra_size += updates_size[1]
            comps.append(updates_form)

        disc_size_text = f"{self.i18n['action.update.total_storage_size']}: {get_human_size_str(extra_size, True)}"
        download_size_text = f"{self.i18n['action.update.download_size']}: {get_human_size_str(required_size)}"

        comps.insert(0, TextComponent(f'{disc_size_text} ({download_size_text})', size=14))
        comps.insert(1, TextComponent(''))

        screen_width = get_current_screen_geometry(self._parent_widget).width()
        if not self.request_confirmation(title=self.i18n['action.update.summary'].capitalize(), body='', components=comps,
                                         confirmation_label=self.i18n['proceed'].capitalize(), deny_label=self.i18n['cancel'].capitalize(),
                                         confirmation_button=can_upgrade, min_width=int(0.45 * screen_width)):
            self.notify_finished({'success': success, 'updated': updated, 'types': updated_types, 'id': None})
            self.pkgs = None
            return

        if not self.internet_checker.is_available():
            return self._handle_internet_off()

        self.change_substatus('')

        app_config = CoreConfigManager().get_config()

        # backup dialog ( if enabled, supported and accepted )
        should_backup = bkp_supported
        should_backup = should_backup and self._check_backup_requirements(app_config=app_config, pkg=None, action_key='upgrade')
        should_backup = should_backup and self._should_backup(action_key='upgrade', app_config=app_config)

        # trim dialog ( if enabled and accepted )
        if app_config['disk']['trim']['after_upgrade'] is not False:
            should_trim = app_config['disk']['trim']['after_upgrade'] or self._ask_for_trim()
        else:
            should_trim = False

        if should_trim and not root_user and root_password is None:  # trim requires root and the password might have not being asked yet
            valid_password, root_password = self._request_password()

            if not valid_password:
                self.notify_finished({'success': False, 'updated': 0, 'types': set(), 'id': None})
                self.pkgs = None
                return

        # performing backup
        if should_backup:
            proceed, root_password = self.request_backup(action_key='upgrade',
                                                         app_config=app_config,
                                                         root_password=root_password,
                                                         pkg=None,
                                                         backup_only=True)
            if not proceed:
                self.notify_finished({'success': False, 'updated': 0, 'types': set(), 'id': None})
                self.pkgs = None
                return

        self.change_substatus('')

        timestamp = datetime.now()
        upgrade_id = 'upgrade_{}{}{}_{}'.format(timestamp.year, timestamp.month, timestamp.day, int(time.time()))

        self._write_summary_log(upgrade_id, requirements)

        success = bool(self.manager.upgrade(requirements, root_password, self))
        self.change_substatus('')

        if success:
            if requirements.to_upgrade:
                updated = len(requirements.to_upgrade)
                updated_types.update((req.pkg.__class__ for req in requirements.to_upgrade))

            if should_trim:
                self._trim_disk(root_password)

            if bool(app_config['updates']['ask_for_reboot']):
                msg = '<p>{}</p>{}</p><br/><p>{}</p>'.format(self.i18n['action.update.success.reboot.line1'],
                                                             self.i18n['action.update.success.reboot.line2'],
                                                             self.i18n['action.update.success.reboot.line3'])
                self.request_reboot(msg)

        self.notify_finished({'success': success, 'updated': updated, 'types': updated_types, 'id': upgrade_id})
        self.pkgs = None


class RefreshApps(AsyncAction):

    def __init__(self, i18n: I18n, manager: SoftwareManager, pkg_types: Set[Type[SoftwarePackage]] = None):
        super(RefreshApps, self).__init__(i18n=i18n)
        self.manager = manager
        self.pkg_types = pkg_types

    def run(self):
        try:
            res = self.manager.read_installed(pkg_types=self.pkg_types, disk_loader=None, only_apps=False,
                                              internet_available=True, limit=-1)
            refreshed_types = set()

            if res:
                for idx, ins in enumerate(res.installed):
                    if self.pkg_types:
                        refreshed_types.add(ins.__class__)

            elif self.pkg_types:
                refreshed_types = self.pkg_types

            self.notify_finished({'installed': res.installed, 'total': res.total, 'types': refreshed_types})
        except Exception:
            traceback.print_exc()
            self.notify_finished({'installed': [], 'total': 0, 'types': set()})
        finally:
            self.pkg_types = None


class UninstallPackage(AsyncAction):

    def __init__(self, manager: SoftwareManager, icon_cache: MemoryCache, i18n: I18n, pkg: PackageView = None):
        super(UninstallPackage, self).__init__(i18n=i18n)
        self.pkg = pkg
        self.manager = manager
        self.icon_cache = icon_cache
        self.root_pwd = None

    def run(self):
        if self.pkg:
            proceed, _ = self.request_backup(action_key='uninstall',
                                             pkg=self.pkg,
                                             root_password=self.root_pwd,
                                             app_config=CoreConfigManager().get_config())
            if not proceed:
                self.notify_finished({'success': False, 'removed': None, 'pkg': self.pkg})
                self.pkg = None
                self.root_pwd = None
                return

            try:
                res = self.manager.uninstall(self.pkg.model, self.root_pwd, self, None)

                if res.success and res.removed:
                    for p in res.removed:
                        if p.icon_url:
                            self.icon_cache.delete(p.icon_url)

                        self.manager.clean_cache_for(p)

                self.notify_finished({'success': res.success, 'removed': res.removed, 'pkg': self.pkg})
            except Exception:
                traceback.print_exc()
                self.notify_finished({'success': False, 'removed': None, 'pkg': self.pkg})
            finally:
                self.pkg = None
                self.root_pwd = None


class DowngradePackage(AsyncAction):

    def __init__(self, manager: SoftwareManager, i18n: I18n, pkg: PackageView = None):
        super(DowngradePackage, self).__init__(i18n=i18n)
        self.manager = manager
        self.pkg = pkg
        self.root_pwd = None

    def run(self):
        if self.pkg:
            success = False

            proceed, _ = self.request_backup(action_key='downgrade',
                                             pkg=self.pkg,
                                             root_password=self.root_pwd,
                                             app_config=CoreConfigManager().get_config())

            if not proceed:
                self.notify_finished({'app': self.pkg, 'success': success})
                self.pkg = None
                self.root_pwd = None
                return

            try:
                success = self.manager.downgrade(self.pkg.model, self.root_pwd, self)
            except (requests.exceptions.ConnectionError, NoInternetException) as e:
                success = False
                self.print(self.i18n['internet.required'])
            finally:
                self.notify_finished({'app': self.pkg, 'success': success})
                self.pkg = None
                self.root_pwd = None


class ShowPackageInfo(AsyncAction):

    def __init__(self, i18n: I18n, manager: SoftwareManager, pkg: PackageView = None):
        super(ShowPackageInfo, self).__init__(i18n=i18n)
        self.pkg = pkg
        self.manager = manager

    def run(self):
        if self.pkg:
            info = {'__app__': self.pkg}

            pkg_info = self.manager.get_info(self.pkg.model)

            if pkg_info:
                info.update(pkg_info)

            self.notify_finished(info)
            self.pkg = None


class ShowPackageHistory(AsyncAction):

    def __init__(self, manager: SoftwareManager, i18n: I18n, pkg: PackageView = None):
        super(ShowPackageHistory, self).__init__(i18n=i18n)
        self.pkg = pkg
        self.manager = manager

    def run(self):
        if self.pkg:
            try:
                self.notify_finished({'history': self.manager.get_history(self.pkg.model)})
            except (requests.exceptions.ConnectionError, NoInternetException) as e:
                self.notify_finished({'error': self.i18n['internet.required']})
            finally:
                self.pkg = None


class SearchPackages(AsyncAction):

    def __init__(self, i18n: I18n, manager: SoftwareManager):
        super(SearchPackages, self).__init__(i18n=i18n)
        self.word = None
        self.manager = manager

    def run(self):
        search_res = {'pkgs_found': [], 'error': None}

        if self.word:
            try:
                res = self.manager.search(words=self.word, disk_loader=None, limit=-1, is_url=False)
                search_res['pkgs_found'] = sort_packages((*(res.installed or ()), *(res.new or ())), self.word)
            except NoInternetException:
                search_res['error'] = 'internet.required'
            finally:
                self.notify_finished(search_res)
                self.word = None


class InstallPackage(AsyncAction):

    def __init__(self, manager: SoftwareManager, icon_cache: MemoryCache, i18n: I18n, pkg: PackageView = None):
        super(InstallPackage, self).__init__(i18n=i18n)
        self.pkg = pkg
        self.manager = manager
        self.icon_cache = icon_cache
        self.root_pwd = None

    def run(self):
        if self.pkg:
            res = {'success': False, 'installed': None, 'removed': None, 'pkg': self.pkg}

            proceed, _ = self.request_backup(action_key='install',
                                             pkg=self.pkg,
                                             root_password=self.root_pwd,
                                             app_config=CoreConfigManager().get_config())

            if not proceed:
                self.signal_finished.emit(res)
                self.pkg = None
                self.root_pwd = None
                return

            try:
                transaction_res = self.manager.install(self.pkg.model, self.root_pwd, None, self)
                res['success'] = transaction_res.success
                res['installed'] = transaction_res.installed
                res['removed'] = transaction_res.removed

                if transaction_res.success:
                    self.pkg.model.installed = True

                    if self.pkg.model.supports_disk_cache():
                        icon_data = self.icon_cache.get(self.pkg.model.icon_url)
                        self.manager.cache_to_disk(pkg=self.pkg.model,
                                                   icon_bytes=icon_data.get('bytes') if icon_data else None,
                                                   only_icon=False)
            except (requests.exceptions.ConnectionError, NoInternetException):
                res['success'] = False
                self.print(self.i18n['internet.required'])
            finally:
                self.signal_finished.emit(res)
                self.pkg = None


class AnimateProgress(QThread):

    signal_change = pyqtSignal(int)

    def __init__(self):
        super(AnimateProgress, self).__init__()
        self.progress_value = 0
        self.increment = 5
        self.stop = False
        self.limit = 100
        self.wait_time = 50
        self.last_progress = 0
        self.manual = False
        self.paused = False

    def _reset(self):
        self.progress_value = 0
        self.increment = 5
        self.stop = False
        self.limit = 100
        self.wait_time = 50
        self.last_progress = 0
        self.manual = False
        self.paused = False

    def set_progress(self, val: int):
        if 0 <= val <= 100:
            self.limit = val
            self.manual = True
            self.increment = 0.5
            self.paused = False

            if self.progress_value >= val:
                self.progress_value = val

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

            super(AnimateProgress, self).msleep(self.wait_time)

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

            self.msleep(100)

        self.pkgs = None
        self.work = True
        self.signal_finished.emit()

    def stop_working(self):
        self.work = False


class NotifyInstalledLoaded(QThread):
    signal_loaded = pyqtSignal()

    def __init__(self):
        super(NotifyInstalledLoaded, self).__init__()
        self.loaded = False

    def notify_loaded(self):
        self.loaded = True

    def run(self):
        self.msleep(100)
        self.signal_loaded.emit()


class FindSuggestions(AsyncAction):

    def __init__(self, i18n: I18n, man: SoftwareManager):
        super(FindSuggestions, self).__init__(i18n=i18n)
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
        warnings = self.man.list_warnings(internet_available=True)
        if warnings:
            self.signal_warnings.emit(warnings)


class LaunchPackage(AsyncAction):

    def __init__(self, i18n: I18n, manager: SoftwareManager, pkg: PackageView = None):
        super(LaunchPackage, self).__init__(i18n=i18n)
        self.pkg = pkg
        self.manager = manager

    def run(self):
        if self.pkg:
            try:
                super(LaunchPackage, self).msleep(250)
                self.manager.launch(self.pkg.model)
                self.notify_finished(True)
            except Exception:
                traceback.print_exc()
            finally:
                self.notify_finished(False)


class ApplyFilters(AsyncAction):

    signal_table = pyqtSignal(list)

    def __init__(self, i18n: I18n, logger: Logger, filters: Optional[PackageFilters] = None,
                 pkgs: Optional[List[PackageView]] = None, index: Optional[dict] = None):
        super(ApplyFilters, self).__init__(i18n=i18n)
        self.logger = logger
        self.index = index
        self.filters = filters
        self.pkgs = pkgs
        self.wait_table_update = False

    def stop_waiting(self):
        self.wait_table_update = False

    def run(self):
        if self.index and self.filters and self.pkgs:
            if self.filters.anything:
                # it means no filter should be applied, and when can rely on the firstly displayed packages
                sorted_pkgs = self.pkgs

                if self.filters.display_limit > 0:
                    sorted_pkgs = sorted_pkgs[0:self.filters.display_limit]
                
            else:
                ti = time.time()
                sort_term = self.filters.name or self.filters.search  # improves displayed matches when no name typed
                matched_pkgs = query_packages(index=self.index, filters=self.filters)
                sorted_pkgs = commons.sort_packages(pkgs=matched_pkgs, word=sort_term)
                tf = time.time()
                self.logger.info(f"Took {tf - ti:.9f} seconds to filter and sort packages")

            self.wait_table_update = True
            self.signal_table.emit(sorted_pkgs)

            while self.wait_table_update:
                super(ApplyFilters, self).msleep(1)

        self.notify_finished()


class CustomAction(AsyncAction):

    def __init__(self, manager: SoftwareManager, i18n: I18n, custom_action: CustomSoftwareAction = None, pkg: PackageView = None, root_password: Optional[str] = None):
        super(CustomAction, self).__init__(i18n=i18n)
        self.manager = manager
        self.pkg = pkg
        self.custom_action = custom_action
        self.root_pwd = root_password

    def run(self):
        res = {'success': False, 'pkg': self.pkg, 'action': self.custom_action, 'error': None, 'error_type': MessageType.ERROR}

        if self.custom_action.backup:
            proceed, _ = self.request_backup(app_config=CoreConfigManager().get_config(),
                                             action_key=None,
                                             root_password=self.root_pwd,
                                             pkg=self.pkg)
            if not proceed:
                self.notify_finished(res)
                self.pkg = None
                self.custom_action = None
                self.root_pwd = None
                return

        try:
            res['success'] = self.manager.execute_custom_action(action=self.custom_action,
                                                                pkg=self.pkg.model if self.pkg else None,
                                                                root_password=self.root_pwd,
                                                                watcher=self)
        except (requests.exceptions.ConnectionError, NoInternetException):
            res['success'] = False
            res['error'] = 'internet.required'
            res['error_type'] = MessageType.WARNING
            self.signal_output.emit(self.i18n['internet.required'])

        self.notify_finished(res)
        self.pkg = None
        self.custom_action = None
        self.root_pwd = None


class ShowScreenshots(AsyncAction):

    def __init__(self, i18n: I18n, manager: SoftwareManager, pkg: PackageView = None):
        super(ShowScreenshots, self).__init__(i18n=i18n)
        self.pkg = pkg
        self.manager = manager

    def run(self):
        if self.pkg:
            self.notify_finished({'pkg': self.pkg, 'screenshots': tuple(self.manager.get_screenshots(self.pkg.model))})

        self.pkg = None


class IgnorePackageUpdates(AsyncAction):

    def __init__(self, i18n: I18n, manager: SoftwareManager, pkg: PackageView = None):
        super(IgnorePackageUpdates, self).__init__(i18n=i18n)
        self.pkg = pkg
        self.manager = manager

    def run(self):
        if self.pkg:
            try:
                if self.pkg.model.is_update_ignored():
                    self.manager.revert_ignored_update(self.pkg.model)
                    res = {'action': 'ignore_updates_reverse', 'success': not self.pkg.model.is_update_ignored(), 'pkg': self.pkg}
                else:
                    self.manager.ignore_update(self.pkg.model)
                    res = {'action': 'ignore_updates', 'success': self.pkg.model.is_update_ignored(), 'pkg': self.pkg}

                self.notify_finished(res)

            finally:
                self.pkg = None


class SaveTheme(QThread):

    def __init__(self, theme_key: Optional[str], parent: Optional[QWidget] = None):
        super(SaveTheme, self).__init__(parent=parent)
        self.theme_key = theme_key

    def run(self):
        if self.theme_key:
            configman = CoreConfigManager()
            core_config = configman.get_config()
            core_config['ui']['theme'] = self.theme_key

            try:
                configman.save_config(core_config)
            except Exception:
                traceback.print_exc()


class StartAsyncAction(QThread):

    signal_start = pyqtSignal()

    def __init__(self, delay_in_milis: int = -1, parent: Optional[QObject] = None):
        super(StartAsyncAction, self).__init__(parent=parent)
        self.delay = delay_in_milis

    def run(self):
        if self.delay > 0:
            self.msleep(self.delay)

        self.signal_start.emit()


class URLFileDownloader(QThread):

    signal_downloaded = pyqtSignal(str, bytes, object)

    def __init__(self, logger: Logger, max_workers: int = 50, request_timeout: int = 30, inactivity_timeout: int = 3,
                 max_downloads: int = -1, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._logger = logger
        self._queue = Queue()
        self._max_workers = max_workers
        self._request_timeout = request_timeout
        self._inactivity_timeout = inactivity_timeout
        self._max_downloads = max_downloads
        self._stop = False

    def _get(self, url_: str, id_: Optional[object]):
        if self._stop:
            self._logger.info(f"File '{url_}' download cancelled")
            return

        try:
            res = requests.get(url=url_, timeout=self._request_timeout)
            content = res.content if res.status_code == 200 else None
            self.signal_downloaded.emit(url_, content, id_)
        except Exception as e:
            self._logger.error(f"[ERROR] could not download file from '{url_}': "
                               f"{e.__class__.__name__}({str(e.args)})\n")

    def run(self) -> None:
        download_count = 0
        futures = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            while not self._stop and (self._max_downloads <= 0 or download_count < self._max_downloads):
                try:
                    url_, id_ = self._queue.get(timeout=self._inactivity_timeout)
                    futures.append(executor.submit(self._get, url_, id_))
                    download_count += 1
                except Exception:
                    self._stop = True

            cancelled_count = 0
            for f in futures:
                if not f.done():
                    f.cancel()
                    cancelled_count += 1

            if cancelled_count > 0:
                self._logger.info(f"{cancelled_count} file downloads cancelled")

        self._logger.info(f"Finished to download files (count={download_count})")

    def stop(self) -> None:
        self._stop = True

    def get(self, url: str, id_: Optional[object]):
        final_url = url.strip() if url else None

        if final_url:
            if RE_URL.match(final_url):
                self._queue.put((final_url, id_))
            else:
                self.signal_downloaded.emit(final_url, None, id_)
