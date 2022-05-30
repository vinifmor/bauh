import os
import re
import shutil
import time
import traceback
from subprocess import Popen, STDOUT
from threading import Thread
from typing import List, Set, Type, Tuple, Dict, Optional, Generator, Callable, Pattern

from bauh.api.abstract.controller import SoftwareManager, SearchResult, ApplicationContext, UpgradeRequirements, \
    UpgradeRequirement, TransactionResult, SoftwareAction, SettingsView, SettingsController
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import SoftwarePackage, PackageUpdate, PackageHistory, PackageSuggestion, \
    CustomSoftwareAction
from bauh.api.abstract.view import ViewComponent, TabGroupComponent, MessageType, PanelComponent
from bauh.api.exception import NoInternetException
from bauh.commons.boot import CreateConfigFile
from bauh.commons.html import bold
from bauh.commons.util import sanitize_command_input
from bauh.view.core.config import CoreConfigManager
from bauh.view.core.settings import GenericSettingsManager
from bauh.view.core.update import check_for_update
from bauh.view.util import resource
from bauh.view.util.resource import get_path
from bauh.view.util.util import clean_app_files, restart_app

RE_IS_URL = re.compile(r'^https?://.+')


class GenericUpgradeRequirements(UpgradeRequirements):

    def __init__(self, to_install: List[UpgradeRequirement], to_remove: List[UpgradeRequirement],
                 to_upgrade: List[UpgradeRequirement], cannot_upgrade: List[SoftwarePackage],
                 sub_requirements: Dict[SoftwareManager, UpgradeRequirements]):
        super(GenericUpgradeRequirements, self).__init__(to_install=to_install, to_upgrade=to_upgrade,
                                                         to_remove=to_remove, cannot_upgrade=cannot_upgrade)
        self.sub_requirements = sub_requirements


class GenericSoftwareManager(SoftwareManager, SettingsController):

    def __init__(self, managers: List[SoftwareManager], context: ApplicationContext, config: dict,
                 force_suggestions: bool = False):

        super(GenericSoftwareManager, self).__init__(context=context)
        self.managers = managers
        self.map = {t: m for m in self.managers for t in m.get_managed_types()}
        self._available_cache = {} if config['system']['single_dependency_checking'] else None
        self.thread_prepare = None
        self.i18n = context.i18n
        self.disk_loader_factory = context.disk_loader_factory
        self.logger = context.logger
        self._already_prepared = []
        self.working_managers = []
        self.config = config
        self.settings_manager: Optional[GenericSettingsManager] = None
        self.http_client = context.http_client
        self.configman = CoreConfigManager()
        self._action_reset: Optional[CustomSoftwareAction] = None
        self._dynamic_extra_actions: Optional[Dict[CustomSoftwareAction, Callable[[dict], bool]]] = None
        self.force_suggestions = force_suggestions

    @property
    def dynamic_extra_actions(self) -> Dict[CustomSoftwareAction, Callable[[dict], bool]]:
        if self._dynamic_extra_actions is None:
            self._dynamic_extra_actions = {
                CustomSoftwareAction(i18n_label_key='action.backups',
                                     i18n_status_key='action.backups.status',
                                     i18n_description_key='action.backups.desc',
                                     manager_method='launch_timeshift',
                                     manager=self,
                                     icon_path='timeshift',
                                     requires_root=False,
                                     refresh=False): self.is_backups_action_available
            }

        return self._dynamic_extra_actions

    @property
    def action_reset(self) -> CustomSoftwareAction:
        if self._action_reset is None:
            self._action_reset = CustomSoftwareAction(i18n_label_key='action.reset',
                                                      i18n_status_key='action.reset.status',
                                                      i18n_description_key='action.reset.desc',
                                                      manager_method='reset',
                                                      icon_path=resource.get_path('img/logo.svg'),
                                                      requires_root=False,
                                                      manager=self,
                                                      refresh=False)

        return self._action_reset

    def _is_timeshift_launcher_available(self) -> bool:
        return bool(shutil.which('timeshift-launcher'))

    def is_backups_action_available(self, app_config: dict) -> bool:
        return bool(app_config['backup']['enabled']) and self._is_timeshift_launcher_available()

    def reset_cache(self):
        if self._available_cache is not None:
            self._available_cache = {}
            self.working_managers.clear()

    def launch_timeshift(self, root_password: Optional[str], watcher: ProcessWatcher):
        if self._is_timeshift_launcher_available():
            try:
                Popen(['timeshift-launcher'], stderr=STDOUT)
                return True
            except:
                traceback.print_exc()
                watcher.show_message(title=self.i18n["error"].capitalize(),
                                     body=self.i18n['action.backups.tool_error'].format(bold('Timeshift')),
                                     type_=MessageType.ERROR)
                return False
        else:
            watcher.show_message(title=self.i18n["error"].capitalize(),
                                 body=self.i18n['action.backups.tool_error'].format(bold('Timeshift')),
                                 type_=MessageType.ERROR)
            return False

    def _can_work(self, man: SoftwareManager):
        if self._available_cache is not None:
            available = False
            for t in man.get_managed_types():
                available = self._available_cache.get(t)

                if available is None:
                    available = man.is_enabled() and man.can_work()[0]
                    self._available_cache[t] = available

                if available:
                    available = True
        else:
            available = man.is_enabled() and man.can_work()[0]

        if available:
            if man not in self.working_managers:
                self.working_managers.append(man)
        else:
            if man in self.working_managers:
                self.working_managers.remove(man)

        return available

    def _search(self, word: str, is_url: bool, man: SoftwareManager, disk_loader, res: SearchResult):
        if self._can_work(man):
            mti = time.time()
            apps_found = man.search(words=word, disk_loader=disk_loader, is_url=is_url, limit=-1)
            mtf = time.time()
            self.logger.info(f'{man.__class__.__name__} took {mtf - mti:.8f} seconds')

            res.installed.extend(apps_found.installed)
            res.new.extend(apps_found.new)

    def search(self, words: str, disk_loader: DiskCacheLoader = None, limit: int = -1, is_url: bool = False) -> SearchResult:
        ti = time.time()
        self._wait_to_be_ready()

        res = SearchResult.empty()

        if self.context.is_internet_available():
            norm_query = sanitize_command_input(words).lower()
            self.logger.info(f"Search query: {norm_query}")

            if norm_query:
                is_url = bool(RE_IS_URL.match(norm_query))
                disk_loader = self.disk_loader_factory.new()
                disk_loader.start()

                threads = []

                for man in self.managers:
                    t = Thread(target=self._search, args=(norm_query, is_url, man, disk_loader, res))
                    t.start()
                    threads.append(t)

                for t in threads:
                    t.join()

                if disk_loader:
                    disk_loader.stop_working()
                    disk_loader.join()

            # res.installed = self._sort(res.installed, norm_word)
            # res.new = self._sort(res.new, norm_word)
        else:
            raise NoInternetException()

        res.update_total()
        tf = time.time()
        self.logger.info(f'Took {tf - ti:.8f} seconds')
        return res

    def _wait_to_be_ready(self):
        if self.thread_prepare:
            self.thread_prepare.join()
            self.thread_prepare = None

    def set_enabled(self, enabled: bool):
        pass

    def can_work(self) -> Tuple[bool, Optional[str]]:
        return True, None

    def _get_package_lower_name(self, pkg: SoftwarePackage):
        return pkg.name.lower()

    def read_installed(self, disk_loader: DiskCacheLoader = None, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None) -> SearchResult:
        ti = time.time()
        self._wait_to_be_ready()

        res = SearchResult([], None, 0)

        disk_loader = None

        net_available = self.context.is_internet_available()
        if not pkg_types:  # any type
            for man in self.managers:
                if self._can_work(man):
                    if not disk_loader:
                        disk_loader = self.disk_loader_factory.new()
                        disk_loader.start()

                    mti = time.time()
                    man_res = man.read_installed(disk_loader=disk_loader, pkg_types=None, internet_available=net_available)
                    mtf = time.time()
                    self.logger.info(f'{man.__class__.__name__} took {mtf - mti:.2f} seconds')

                    res.installed.extend(man_res.installed)
                    res.total += man_res.total
        else:
            man_already_used = []

            for t in pkg_types:
                man = self.map.get(t)
                if man and (man not in man_already_used) and self._can_work(man):

                    if not disk_loader:
                        disk_loader = self.disk_loader_factory.new()
                        disk_loader.start()

                    mti = time.time()
                    man_res = man.read_installed(disk_loader=disk_loader, pkg_types=None, internet_available=net_available)
                    mtf = time.time()
                    self.logger.info(f'{man.__class__.__name__} took {mtf - mti:.2f} seconds')

                    res.installed.extend(man_res.installed)
                    res.total += man_res.total

        if disk_loader:
            disk_loader.stop_working()
            disk_loader.join()

        if res.installed:
            for p in res.installed:
                if p.is_update_ignored():
                    if p.categories is None:
                        p.categories = ['updates_ignored']
                    elif 'updates_ignored' not in p.categories:
                        self._add_category(p, 'updates_ignored')

            res.installed.sort(key=self._get_package_lower_name)

        tf = time.time()
        self.logger.info(f'Took {tf - ti:.2f} seconds')
        return res

    def _add_category(self, pkg: SoftwarePackage,  category: str):
        if isinstance(pkg.categories, tuple):
            pkg.categories = tuple((*pkg.categories, category))
        elif isinstance(pkg.categories, list):
            pkg.categories.append(category)
        elif isinstance(pkg.categories, set):
            pkg.categories.add(category)

    def downgrade(self, app: SoftwarePackage, root_password: Optional[str], handler: ProcessWatcher) -> bool:
        man = self._get_manager_for(app)

        if man and app.can_be_downgraded():
            mti = time.time()
            res = man.downgrade(app, root_password, handler)
            mtf = time.time()
            self.logger.info(f'Took {mtf - mti:.2f} seconds')
            return res
        else:
            raise Exception(f"Downgrading is not possible for {app.__class__.__name__}")

    def clean_cache_for(self, app: SoftwarePackage):
        man = self._get_manager_for(app)

        if man:
            return man.clean_cache_for(app)

    def upgrade(self, requirements: GenericUpgradeRequirements, root_password: Optional[str], handler: ProcessWatcher) -> bool:
        for man, man_reqs in requirements.sub_requirements.items():
            res = man.upgrade(man_reqs, root_password, handler)

            if not res:
                return False

        return True

    def _fill_post_transaction_status(self, pkg: SoftwarePackage, installed: bool):
        pkg.installed = installed
        pkg.update = False

        if pkg.latest_version:
            pkg.version = pkg.latest_version

    def _update_post_transaction_status(self, res: TransactionResult):
        if res.success:
            if res.installed:
                for p in res.installed:
                    self._fill_post_transaction_status(p, True)
            if res.removed:
                for p in res.removed:
                    self._fill_post_transaction_status(p, False)

    def uninstall(self, pkg: SoftwarePackage, root_password: Optional[str], handler: ProcessWatcher, disk_loader: DiskCacheLoader = None) -> TransactionResult:
        man = self._get_manager_for(pkg)

        if man:
            ti = time.time()
            disk_loader = self.disk_loader_factory.new()
            disk_loader.start()
            self.logger.info(f"Uninstalling {pkg.name}")
            try:
                res = man.uninstall(pkg, root_password, handler, disk_loader)
                disk_loader.stop_working()
                disk_loader.join()
                self._update_post_transaction_status(res)
                return res
            except:
                traceback.print_exc()
                return TransactionResult(success=False, installed=[], removed=[])
            finally:
                tf = time.time()
                self.logger.info(f'Uninstallation of {pkg} took {(tf - ti) / 60:.2f} minutes')

    def install(self, app: SoftwarePackage, root_password: Optional[str], disk_loader: DiskCacheLoader, handler: ProcessWatcher) -> TransactionResult:
        man = self._get_manager_for(app)

        if man:
            ti = time.time()
            disk_loader = self.disk_loader_factory.new()
            disk_loader.start()
            try:
                self.logger.info(f'Installing {app}')
                res = man.install(app, root_password, disk_loader, handler)
                disk_loader.stop_working()
                disk_loader.join()
                self._update_post_transaction_status(res)
                return res
            except:
                traceback.print_exc()
                return TransactionResult(success=False, installed=[], removed=[])
            finally:
                tf = time.time()
                self.logger.info(f'Installation of {app} took {(tf - ti) / 60:.2f} minutes')

    def get_info(self, app: SoftwarePackage):
        man = self._get_manager_for(app)

        if man:
            return man.get_info(app)

    def get_history(self, app: SoftwarePackage) -> PackageHistory:
        man = self._get_manager_for(app)

        if man:
            mti = time.time()
            history = man.get_history(app)
            mtf = time.time()
            self.logger.info(f'{man.__class__.__name__} took {mtf - mti:.2f} seconds')
            return history

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        available_types = set()

        for man in self.get_working_managers():
            available_types.update(man.get_managed_types())

        return available_types

    def is_enabled(self):
        return True

    def _get_manager_for(self, app: SoftwarePackage) -> SoftwareManager:
        man = self.map[app.__class__]
        return man if man and self._can_work(man) else None

    def cache_to_disk(self, pkg: SoftwarePackage, icon_bytes: bytes, only_icon: bool):
        if pkg.supports_disk_cache():
            man = self._get_manager_for(pkg)

            if man:
                return man.cache_to_disk(pkg, icon_bytes=icon_bytes, only_icon=only_icon)

    def requires_root(self, action: SoftwareAction, app: SoftwarePackage) -> bool:
        if app is None:
            if self.managers:
                for man in self.managers:
                    if self._can_work(man):
                        if man.requires_root(action, app):
                            return True
            return False
        else:
            man = self._get_manager_for(app)

            if man:
                return man.requires_root(action, app)

    def prepare(self, task_manager: TaskManager, root_password: Optional[str], internet_available: bool):
        ti = time.time()
        self.logger.info("Initializing")
        taskman = task_manager if task_manager else TaskManager()  # empty task manager to prevent null pointers

        create_config = CreateConfigFile(taskman=taskman, configman=self.configman, i18n=self.i18n,
                                         task_icon_path=get_path('img/logo.svg'), logger=self.logger)
        create_config.start()

        if self.managers:
            internet_on = self.context.is_internet_available()
            prepare_tasks = []
            for man in self.managers:
                if man not in self._already_prepared and self._can_work(man):
                    t = Thread(target=man.prepare, args=(taskman, root_password, internet_on), daemon=True)
                    t.start()
                    prepare_tasks.append(t)
                    self._already_prepared.append(man)

            for t in prepare_tasks:
                t.join()

        create_config.join()
        tf = time.time()
        self.logger.info(f'Finished ({tf - ti:.2f} seconds)')

    def cache_available_managers(self):
        if self.managers:
            for man in self.managers:
                self._can_work(man)

    def list_updates(self, internet_available: bool = None) -> List[PackageUpdate]:
        self._wait_to_be_ready()

        updates = []

        if self.managers:
            net_available = self.context.is_internet_available()

            for man in self.managers:
                if self._can_work(man):
                    man_updates = man.list_updates(internet_available=net_available)
                    if man_updates:
                        updates.extend(man_updates)

        return updates

    def list_warnings(self, internet_available: bool = None) -> List[str]:
        warnings = []

        int_available = self.context.is_internet_available()

        if int_available:
            updates_msg = check_for_update(self.logger, self.http_client, self.i18n)

            if updates_msg:
                warnings.append(updates_msg)

        if self.managers:
            for man in self.managers:
                if self._can_work(man):
                    man_warnings = man.list_warnings(internet_available=int_available)

                    if man_warnings:
                        warnings.extend(man_warnings)

        return warnings

    def _fill_suggestions(self, suggestions: list, man: SoftwareManager, limit: int, filter_installed: bool):
        if self._can_work(man):
            mti = time.time()
            man_sugs = man.list_suggestions(limit=limit, filter_installed=filter_installed)
            mtf = time.time()
            self.logger.info(f'{man.__class__.__name__} took {mtf - mti:.5f} seconds')

            if man_sugs:
                if 0 < limit < len(man_sugs):
                    man_sugs = man_sugs[0:limit]

                suggestions.extend(man_sugs)

    def list_suggestions(self, limit: int, filter_installed: bool) -> List[PackageSuggestion]:
        if self.force_suggestions or bool(self.config['suggestions']['enabled']):
            if self.managers and self.context.is_internet_available():
                suggestions, threads = [], []
                for man in self.managers:
                    t = Thread(target=self._fill_suggestions,
                               args=(suggestions, man, int(self.config['suggestions']['by_type']), filter_installed))
                    t.start()
                    threads.append(t)

                for t in threads:
                    t.join()

                if suggestions:
                    suggestions.sort(key=lambda s: s.priority.value, reverse=True)

                return suggestions
        return []

    def execute_custom_action(self, action: CustomSoftwareAction, pkg: SoftwarePackage, root_password: Optional[str], watcher: ProcessWatcher):
        if action.requires_internet and not self.context.is_internet_available():
            raise NoInternetException()

        man = action.manager if action.manager else self._get_manager_for(pkg)

        if man:
            return eval(f"man.{action.manager_method}({'pkg=pkg, ' if pkg else ''}root_password=root_password, watcher=watcher)")

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: SoftwarePackage):
        self._wait_to_be_ready()

        man = self._get_manager_for(pkg)

        if man:
            self.logger.info(f'Launching {pkg}')
            man.launch(pkg)

    def get_screenshots(self, pkg: SoftwarePackage) -> Generator[str, None, None]:
        man = self._get_manager_for(pkg)

        if man:
            yield from man.get_screenshots(pkg)

    def get_working_managers(self):
        return [m for m in self.managers if self._can_work(m)]

    def get_settings(self) -> Optional[Generator[SettingsView, None, None]]:
        if self.settings_manager is None:
            self.settings_manager = GenericSettingsManager(managers=self.managers,
                                                           working_managers=self.working_managers,
                                                           configman=self.configman,
                                                           context=self.context)
        else:
            self.settings_manager.managers = self.managers
            self.settings_manager.working_managers = self.working_managers

        yield SettingsView(self, self.settings_manager.get_settings())

    def save_settings(self, component: TabGroupComponent) -> Tuple[bool, Optional[List[str]]]:
        return self.settings_manager.save_settings(component)

    def _map_pkgs_by_manager(self, pkgs: List[SoftwarePackage], pkg_filters: list = None) -> Dict[SoftwareManager, List[SoftwarePackage]]:
        by_manager = {}
        for pkg in pkgs:
            if pkg_filters and not all((1 for f in pkg_filters if f(pkg))):
                continue

            man = self._get_manager_for(pkg)

            if man:
                man_pkgs = by_manager.get(man)

                if man_pkgs is None:
                    man_pkgs = []
                    by_manager[man] = man_pkgs

                man_pkgs.append(pkg)

        return by_manager

    def get_upgrade_requirements(self, pkgs: List[SoftwarePackage], root_password: Optional[str], watcher: ProcessWatcher) -> UpgradeRequirements:
        by_manager = self._map_pkgs_by_manager(pkgs)
        res = GenericUpgradeRequirements([], [], [], [], {})

        if by_manager:
            for man, pkgs in by_manager.items():
                ti = time.time()
                man_reqs = man.get_upgrade_requirements(pkgs, root_password, watcher)
                tf = time.time()
                self.logger.info(f'{man.__class__.__name__} took {tf - ti:.2f} seconds')

                if not man_reqs:
                    return  # it means the process should be stopped

                if man_reqs:
                    res.sub_requirements[man] = man_reqs
                    if man_reqs.to_install:
                        res.to_install.extend(man_reqs.to_install)

                    if man_reqs.to_remove:
                        res.to_remove.extend(man_reqs.to_remove)

                    if man_reqs.to_upgrade:
                        res.to_upgrade.extend(man_reqs.to_upgrade)

                    if man_reqs.cannot_upgrade:
                        res.cannot_upgrade.extend(man_reqs.cannot_upgrade)

        return res

    def reset(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        body = f"<p>{self.i18n['action.reset.body_1'].format(bold(self.context.app_name))}</p>" \
               f"<p>{self.i18n['action.reset.body_2']}</p>"

        if watcher.request_confirmation(title=self.i18n['action.reset'],
                                        body=body,
                                        confirmation_label=self.i18n['proceed'].capitalize(),
                                        deny_label=self.i18n['cancel'].capitalize()):

            try:
                clean_app_files(managers=self.managers, logs=False)
                restart_app()
            except:
                return False

        return True

    def gen_custom_actions(self) -> Generator[CustomSoftwareAction, None, None]:
        if self.managers:
            working_managers = []

            for man in self.managers:
                if self._can_work(man):
                    working_managers.append(man)

            if working_managers:
                working_managers.sort(key=lambda m: m.__class__.__name__)

                for man in working_managers:
                    for action in man.gen_custom_actions():
                        action.manager = man
                        yield action

        app_config = self.configman.get_config()

        for action, available in self.dynamic_extra_actions.items():
            if available(app_config):
                yield action

        yield self.action_reset

    def _fill_sizes(self, man: SoftwareManager, pkgs: List[SoftwarePackage]):
        ti = time.time()
        man.fill_sizes(pkgs)
        tf = time.time()
        self.logger.info(f'{man.__class__.__name__} took {tf - ti:.2f} seconds')

    def fill_sizes(self, pkgs: List[SoftwarePackage]):
        by_manager = self._map_pkgs_by_manager(pkgs, pkg_filters=[lambda p: p.size is None])

        if by_manager:
            threads = []
            for man, man_pkgs in by_manager.items():
                if man_pkgs:
                    t = Thread(target=self._fill_sizes, args=(man, man_pkgs), daemon=True)
                    t.start()
                    threads.append(t)

            for t in threads:
                t.join()

    def ignore_update(self, pkg: SoftwarePackage):
        manager = self._get_manager_for(pkg)

        if manager:
            manager.ignore_update(pkg)

            if pkg.is_update_ignored():
                if pkg.categories is None:
                    pkg.categories = ['updates_ignored']
                elif 'updates_ignored' not in pkg.categories:
                    self._add_category(pkg, 'updates_ignored')

    def revert_ignored_update(self, pkg: SoftwarePackage):
        manager = self._get_manager_for(pkg)

        if manager:
            manager.revert_ignored_update(pkg)

            if not pkg.is_update_ignored() and pkg.categories and 'updates_ignored' in pkg.categories:
                if isinstance(pkg.categories, tuple):
                    pkg.categories = tuple(c for c in pkg.categories if c != 'updates_ignored')
                else:
                    pkg.categories.remove('updates_ignored')
