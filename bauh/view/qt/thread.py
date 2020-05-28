import os
import re
import time
import traceback
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import List, Type, Set, Tuple

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from bauh import LOGS_PATH
from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.controller import SoftwareManager, UpgradeRequirement, UpgradeRequirements
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import PackageStatus, SoftwarePackage, CustomSoftwareAction
from bauh.api.abstract.view import MessageType, MultipleSelectComponent, InputOption, TextComponent, \
    FormComponent, ViewComponent
from bauh.api.exception import NoInternetException
from bauh.commons import user
from bauh.commons.html import bold
from bauh.commons.system import get_human_size_str, ProcessHandler, SimpleProcess
from bauh.view.core import timeshift
from bauh.view.core.config import read_config
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

    def request_confirmation(self, title: str, body: str, components: List[ViewComponent] = None,
                             confirmation_label: str = None, deny_label: str = None, deny_button: bool = True, window_cancel: bool = False) -> bool:
        self.wait_confirmation = True
        self.signal_confirmation.emit({'title': title, 'body': body, 'components': components, 'confirmation_label': confirmation_label, 'deny_label': deny_label, 'deny_button': deny_button, 'window_cancel': window_cancel})
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

    def request_reboot(self, msg: str) -> bool:
        if self.request_confirmation(title=self.i18n['action.request_reboot.title'],
                                     body=msg,
                                     confirmation_label=self.i18n['yes'].capitalize(),
                                     deny_label=self.i18n['bt.not_now']):
            ProcessHandler(self).handle_simple(SimpleProcess(['reboot']))
            return True

        return False

    def _generate_backup(self, app_config: dict, i18n: I18n, root_password: str) -> bool:
        if timeshift.is_available():
            if app_config['backup']['mode'] not in ('only_one', 'incremental'):
                self.show_message(title=self.i18n['error'].capitalize(),
                                  body='{}: {}'.format(self.i18n['action.backup.invalid_mode'], bold(app_config['backup']['mode'])),
                                  type_=MessageType.ERROR)
                return False

            if not user.is_root() and not root_password:
                root_pwd, valid = self.request_root_password()
            else:
                root_pwd, valid = root_password, True

            if not valid:
                return False

            handler = ProcessHandler(self)
            if app_config['backup']['mode'] == 'only_one':
                self.change_substatus('[{}] {}'.format(i18n['core.config.tab.backup'].lower(), i18n['action.backup.substatus.delete']))
                deleted, _ = handler.handle_simple(timeshift.delete_all_snapshots(root_pwd))

                if not deleted and not self.request_confirmation(title=i18n['core.config.tab.backup'],
                                                                 body='{}. {}'.format(i18n['action.backup.error.delete'], i18n['action.backup.error.proceed']),
                                                                 confirmation_label=i18n['yes'].capitalize(),
                                                                 deny_label=i18n['no'].capitalize()):
                    return False

            self.change_substatus('[{}] {}'.format(i18n['core.config.tab.backup'].lower(), i18n['action.backup.substatus.create']))
            created, _ = handler.handle_simple(timeshift.create_snapshot(root_pwd, app_config['backup']['type']))

            if not created and not self.request_confirmation(title=i18n['core.config.tab.backup'],
                                                             body='{}. {}'.format(i18n['action.backup.error.create'],
                                                                                  i18n['action.backup.error.proceed']),
                                                             confirmation_label=i18n['yes'].capitalize(),
                                                             deny_label=i18n['no'].capitalize()):
                return False

        return True

    def request_backup(self, app_config: dict, key: str, i18n: I18n, root_password: str = None) -> bool:
        if bool(app_config['backup']['enabled']) and timeshift.is_available():
            val = app_config['backup'][key] if key else None

            if val is None:  # ask mode
                if self.request_confirmation(title=i18n['core.config.tab.backup'],
                                             body=i18n['action.backup.msg'],
                                             confirmation_label=i18n['yes'].capitalize(),
                                             deny_label=i18n['no'].capitalize()):
                    res = self._generate_backup(app_config, i18n, root_password)
                    self.change_substatus('')
                    return res

            elif val is True:  # direct mode
                res = self._generate_backup(app_config, i18n, root_password)
                self.change_substatus('')
                return res

        return True


class UpgradeSelected(AsyncAction):

    LOGS_DIR = '{}/upgrade'.format(LOGS_PATH)
    SUMMARY_FILE = LOGS_DIR + '/{}_summary.txt'

    def __init__(self, manager: SoftwareManager, i18n: I18n, pkgs: List[PackageView] = None):
        super(UpgradeSelected, self).__init__()
        self.pkgs = pkgs
        self.manager = manager
        self.i18n = i18n

    def _req_as_option(self, req: UpgradeRequirement, tooltip: bool = True, custom_tooltip: str = None) -> InputOption:
        if req.pkg.installed:
            icon_path = req.pkg.get_disk_icon_path()

            if not icon_path or not os.path.isfile(icon_path):
                icon_path = req.pkg.get_type_icon_path()

        else:
            icon_path = req.pkg.get_type_icon_path()

        size_str = '{}: {}'.format(self.i18n['size'].capitalize(),
                                   '?' if req.extra_size is None else get_human_size_str(req.extra_size))
        if req.extra_size != req.required_size:
            size_str += ' ( {}: {} )'.format(self.i18n['action.update.pkg.required_size'].capitalize(),
                                             '?' if req.required_size is None else get_human_size_str(req.required_size))

        label = '{}{} - {}'.format(req.pkg.name,
                                   ' ( {} )'.format(req.pkg.latest_version) if req.pkg.latest_version else '',
                                   size_str)

        return InputOption(label=label,
                           value=None,
                           tooltip=custom_tooltip if custom_tooltip else (req.pkg.get_name_tooltip() if tooltip else None),
                           read_only=True,
                           icon_path=icon_path)

    def _sum_pkgs_size(self, reqs: List[UpgradeRequirement]) -> Tuple[int, int]:
        required, extra = 0, 0
        for r in reqs:
            if r.required_size is not None:
                required += r.required_size

            if r.extra_size is not None:
                extra += r.extra_size

        return required, extra

    def _gen_cannot_update_form(self, reqs: List[UpgradeRequirement]) -> FormComponent:
        opts = [self._req_as_option(r, False, r.reason) for r in reqs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]

        return FormComponent(label=self.i18n['action.update.cannot_update_label'], components=comps)

    def _gen_to_install_form(self, reqs: List[UpgradeRequirement]) -> Tuple[FormComponent, Tuple[int, int]]:
        opts = [self._req_as_option(r) for r in reqs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]
        required_size, extra_size = self._sum_pkgs_size(reqs)

        lb = '{} ( {}: {}. {}: {}. {}: {} )'.format(self.i18n['action.update.required_label'].capitalize(),
                                                    self.i18n['amount'].capitalize(),
                                                    len(opts),
                                                    self.i18n['size'].capitalize(),
                                                    '?' if extra_size is None else get_human_size_str(extra_size),
                                                    self.i18n['action.update.pkg.required_size'].capitalize(),
                                                    '?' if required_size is None else get_human_size_str(required_size))
        return FormComponent(label=lb, components=comps), (required_size, extra_size)

    def _gen_to_remove_form(self, reqs: List[UpgradeRequirement]) -> FormComponent:
        opts = [self._req_as_option(r, False, r.reason) for r in reqs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]
        required_size, extra_size = self._sum_pkgs_size(reqs)

        lb = '{} ( {}: {}. {}: {} )'.format(self.i18n['action.update.label_to_remove'].capitalize(),
                                            self.i18n['amount'].capitalize(),
                                            len(opts),
                                            self.i18n['size'].capitalize(),
                                            '?' if extra_size is None else get_human_size_str(-extra_size))
        return FormComponent(label=lb, components=comps)

    def _gen_to_update_form(self, reqs: List[UpgradeRequirement]) -> Tuple[FormComponent, Tuple[int, int]]:
        opts = [self._req_as_option(r, tooltip=False) for r in reqs]
        comps = [MultipleSelectComponent(label='', options=opts, default_options=set(opts))]
        required_size, extra_size = self._sum_pkgs_size(reqs)

        lb = '{} ( {}: {}. {}: {}. {}: {} )'.format(self.i18n['action.update.label_to_upgrade'].capitalize(),
                                                    self.i18n['amount'].capitalize(),
                                                    len(opts),
                                                    self.i18n['size'].capitalize(),
                                                    '?' if extra_size is None else get_human_size_str(extra_size),
                                                    self.i18n['action.update.pkg.required_size'].capitalize(),
                                                    '?' if required_size is None else get_human_size_str(required_size))

        return FormComponent(label=lb, components=comps), (required_size, extra_size)

    def _request_password(self) -> Tuple[bool, str]:
        if not user.is_root():
            pwd, success = self.request_root_password()

            if not success:
                return False, None

            return True, pwd

        return True, None

    def _ask_for_trim(self) -> bool:
        return self.request_confirmation(title=self.i18n['confirmation'].capitalize(), body=self.i18n['action.trim_disk.ask'])

    def _trim_disk(self, root_password: str):
        self.change_status('{}...'.format(self.i18n['action.disk_trim'].capitalize()))
        self.change_substatus('')

        success, output = ProcessHandler(self).handle_simple(SimpleProcess(['fstrim', '/', '-v'], root_password=root_password))

        if not success:
            self.show_message(title=self.i18n['success'].capitalize(),
                              body=self.i18n['action.disk_trim.error'],
                              type_=MessageType.ERROR)

    def _write_summary_log(self, upgrade_id: str, requirements: UpgradeRequirements):
        try:
            Path(self.LOGS_DIR).mkdir(parents=True, exist_ok=True)

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

        except:
            traceback.print_exc()

    def run(self):
        valid_password, root_password = self._request_password()

        if not valid_password:
            self.notify_finished({'success': False, 'updated': 0, 'types': set(), 'id': None})
            self.pkgs = None
            return

        to_update = [pkg for pkg in self.pkgs if pkg.model.update and not pkg.model.is_update_ignored() and pkg.update_checked]

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
            comps.append(self._gen_cannot_update_form(requirements.cannot_upgrade))

        if requirements.to_install:
            req_form, reqs_size = self._gen_to_install_form(requirements.to_install)
            required_size += reqs_size[0]
            extra_size += reqs_size[1]
            comps.append(req_form)

        if requirements.to_remove:
            comps.append(self._gen_to_remove_form(requirements.to_remove))

        updates_form, updates_size = self._gen_to_update_form(requirements.to_upgrade)
        required_size += updates_size[0]
        extra_size += updates_size[1]
        comps.append(updates_form)

        extra_size_text = '{}: {}'.format(self.i18n['action.update.total_size'].capitalize(), get_human_size_str(extra_size))
        req_size_text = '{}: {}'.format(self.i18n['action.update.required_size'].capitalize(),
                                        get_human_size_str(required_size))
        comps.insert(0, TextComponent('{}  |  {}'.format(extra_size_text, req_size_text), size=14))
        comps.insert(1, TextComponent(''))

        if not self.request_confirmation(title=self.i18n['action.update.summary'].capitalize(), body='', components=comps,
                                         confirmation_label=self.i18n['proceed'].capitalize(), deny_label=self.i18n['cancel'].capitalize()):
            self.notify_finished({'success': success, 'updated': updated, 'types': updated_types, 'id': None})
            self.pkgs = None
            return

        self.change_substatus('')

        app_config = read_config()

        # trim dialog
        if app_config['disk']['trim']['after_upgrade'] is not False:
            should_trim = app_config['disk']['trim']['after_upgrade'] or self._ask_for_trim()
        else:
            should_trim = False

        # backup process ( if enabled, supported and accepted )
        if bool(app_config['backup']['enabled']) and app_config['backup']['upgrade'] in (True, None) and timeshift.is_available():
            any_requires_bkp = False

            for dep in requirements.to_upgrade:
                if dep.pkg.supports_backup():
                    any_requires_bkp = True
                    break

            if any_requires_bkp:
                if not self.request_backup(app_config, 'upgrade', self.i18n, root_password):
                    self.notify_finished({'success': success, 'updated': updated, 'types': updated_types, 'id': None})
                    self.pkgs = None
                    return

        self.change_substatus('')

        timestamp = datetime.now()
        upgrade_id = 'upgrade_{}{}{}_{}'.format(timestamp.year, timestamp.month, timestamp.day, int(time.time()))

        self._write_summary_log(upgrade_id, requirements)

        success = bool(self.manager.upgrade(requirements, root_password, self))
        self.change_substatus('')

        if success:
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

    def __init__(self, manager: SoftwareManager, icon_cache: MemoryCache, i18n: I18n, app: PackageView = None):
        super(UninstallApp, self).__init__()
        self.app = app
        self.manager = manager
        self.icon_cache = icon_cache
        self.root_pwd = None
        self.i18n = i18n

    def run(self):
        if self.app:
            if self.app.model.supports_backup():
                if not self.request_backup(read_config(), 'uninstall', self.i18n, self.root_pwd):
                    self.notify_finished(False)
                    self.app = None
                    self.root_pwd = None
                    return

            success = self.manager.uninstall(self.app.model, self.root_pwd, self)

            if success:
                self.icon_cache.delete(self.app.model.icon_url)
                self.manager.clean_cache_for(self.app.model)

            self.notify_finished(self.app if success else None)
            self.app = None
            self.root_pwd = None


class DowngradeApp(AsyncAction):

    def __init__(self, manager: SoftwareManager, i18n: I18n, app: PackageView = None):
        super(DowngradeApp, self).__init__()
        self.manager = manager
        self.app = app
        self.i18n = i18n
        self.root_pwd = None

    def run(self):
        if self.app:
            success = False

            if self.app.model.supports_backup():
                if not self.request_backup(read_config(), 'downgrade', self.i18n, self.root_pwd):
                    self.notify_finished({'app': self.app, 'success': success})
                    self.app = None
                    self.root_pwd = None
                    return

            try:
                success = self.manager.downgrade(self.app.model, self.root_pwd, self)
            except (requests.exceptions.ConnectionError, NoInternetException) as e:
                success = False
                self.print(self.i18n['internet.required'])
            finally:
                self.notify_finished({'app': self.app, 'success': success})
                self.app = None
                self.root_pwd = None


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

    def __init__(self, manager: SoftwareManager, icon_cache: MemoryCache, i18n: I18n, pkg: PackageView = None):
        super(InstallPackage, self).__init__()
        self.pkg = pkg
        self.manager = manager
        self.icon_cache = icon_cache
        self.i18n = i18n
        self.root_pwd = None

    def run(self):
        if self.pkg:
            success = False

            if self.pkg.model.supports_backup():
                if not self.request_backup(read_config(), 'install', self.i18n, self.root_pwd):
                    self.signal_finished.emit({'success': False, 'pkg': self.pkg})
                    return

            try:
                success = self.manager.install(self.pkg.model, self.root_pwd, self)

                if success:
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
        self.root_pwd = root_password
        self.i18n = i18n

    def run(self):
        if self.custom_action.backup:
            app_config = read_config()
            if not self.request_backup(app_config, None, self.i18n, self.root_pwd):
                self.notify_finished({'success': False, 'pkg': self.pkg, 'action': self.custom_action})
                self.pkg = None
                self.custom_action = None
                self.root_pwd = None
                return

        try:
            success = self.manager.execute_custom_action(action=self.custom_action,
                                                         pkg=self.pkg.model if self.pkg else None,
                                                         root_password=self.root_pwd,
                                                         watcher=self)
        except (requests.exceptions.ConnectionError, NoInternetException):
            success = False
            self.signal_output.emit(self.i18n['internet.required'])

        self.notify_finished({'success': success, 'pkg': self.pkg, 'action': self.custom_action})
        self.pkg = None
        self.custom_action = None
        self.root_pwd = None


class GetScreenshots(AsyncAction):

    def __init__(self, manager: SoftwareManager, pkg: PackageView = None):
        super(GetScreenshots, self).__init__()
        self.pkg = pkg
        self.manager = manager

    def run(self):
        if self.pkg:
            self.notify_finished({'pkg': self.pkg, 'screenshots': self.manager.get_screenshots(self.pkg.model)})

        self.pkg = None


class IgnorePackageUpdates(AsyncAction):

    def __init__(self, manager: SoftwareManager, pkg: PackageView = None):
        super(IgnorePackageUpdates, self).__init__()
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
