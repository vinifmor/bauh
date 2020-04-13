import os
import re
import time
import traceback
from pathlib import Path
from threading import Thread
from typing import List, Set, Type, Tuple, Dict

from bauh import __app_name__, __version__
from bauh.api.abstract.controller import SoftwareManager, SearchResult, ApplicationContext, UpgradeRequirements, \
    UpgradeRequirement
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import SoftwarePackage, PackageUpdate, PackageHistory, PackageSuggestion, \
    CustomSoftwareAction
from bauh.api.abstract.view import ViewComponent, TabGroupComponent
from bauh.api.constants import CACHE_PATH
from bauh.api.exception import NoInternetException
from bauh.commons import internet
from bauh.commons.html import bold, link
from bauh.view.core.settings import GenericSettingsManager

RE_IS_URL = re.compile(r'^https?://.+')


class GenericUpgradeRequirements(UpgradeRequirements):

    def __init__(self, to_install: List[UpgradeRequirement], to_remove: List[UpgradeRequirement],
                 to_upgrade: List[UpgradeRequirement], cannot_upgrade: List[SoftwarePackage],
                 sub_requirements: Dict[SoftwareManager, UpgradeRequirements]):
        super(GenericUpgradeRequirements, self).__init__(to_install=to_install, to_upgrade=to_upgrade,
                                                         to_remove=to_remove, cannot_upgrade=cannot_upgrade)
        self.sub_requirements = sub_requirements


class GenericSoftwareManager(SoftwareManager):

    def __init__(self, managers: List[SoftwareManager], context: ApplicationContext, config: dict,
                 settings_manager: GenericSettingsManager = None):
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
        self.settings_manager = settings_manager
        self.http_client = context.http_client

    def reset_cache(self):
        if self._available_cache is not None:
            self._available_cache = {}
            self.working_managers.clear()

    def _sort(self, apps: List[SoftwarePackage], word: str) -> List[SoftwarePackage]:

        exact_name_matches, contains_name_matches, others = [], [], []

        for app in apps:
            lower_name = app.name.lower()

            if word == lower_name:
                exact_name_matches.append(app)
            elif word in lower_name:
                contains_name_matches.append(app)
            else:
                others.append(app)

        res = []
        for app_list in (exact_name_matches, contains_name_matches, others):
            app_list.sort(key=lambda a: a.name.lower())
            res.extend(app_list)

        return res

    def _can_work(self, man: SoftwareManager):

        if self._available_cache is not None:
            available = False
            for t in man.get_managed_types():
                available = self._available_cache.get(t)

                if available is None:
                    available = man.is_enabled() and man.can_work()
                    self._available_cache[t] = available

                if available:
                    available = True
        else:
            available = man.is_enabled() and man.can_work()

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
            apps_found = man.search(words=word, disk_loader=disk_loader, is_url=is_url)
            mtf = time.time()
            self.logger.info(man.__class__.__name__ + " took {0:.2f} seconds".format(mtf - mti))

            res.installed.extend(apps_found.installed)
            res.new.extend(apps_found.new)

    def search(self, word: str, disk_loader: DiskCacheLoader = None, limit: int = -1, is_url: bool = False) -> SearchResult:
        ti = time.time()
        self._wait_to_be_ready()

        res = SearchResult([], [], 0)

        if internet.is_available():
            norm_word = word.strip().lower()

            url_words = RE_IS_URL.match(norm_word)
            disk_loader = self.disk_loader_factory.new()
            disk_loader.start()

            threads = []

            for man in self.managers:
                t = Thread(target=self._search, args=(norm_word, url_words, man, disk_loader, res))
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            if disk_loader:
                disk_loader.stop_working()
                disk_loader.join()

            res.installed = self._sort(res.installed, norm_word)
            res.new = self._sort(res.new, norm_word)
            res.total = len(res.installed) + len(res.new)
        else:
            raise NoInternetException()

        tf = time.time()
        self.logger.info('Took {0:.2f} seconds'.format(tf - ti))
        return res

    def _wait_to_be_ready(self):
        if self.thread_prepare:
            self.thread_prepare.join()
            self.thread_prepare = None

    def set_enabled(self, enabled: bool):
        pass

    def can_work(self) -> bool:
        return True

    def read_installed(self, disk_loader: DiskCacheLoader = None, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None) -> SearchResult:
        ti = time.time()
        self._wait_to_be_ready()

        res = SearchResult([], None, 0)

        disk_loader = None

        net_available = internet.is_available()
        if not pkg_types:  # any type
            for man in self.managers:
                if self._can_work(man):
                    if not disk_loader:
                        disk_loader = self.disk_loader_factory.new()
                        disk_loader.start()

                    mti = time.time()
                    man_res = man.read_installed(disk_loader=disk_loader, pkg_types=None, internet_available=net_available)
                    mtf = time.time()
                    self.logger.info(man.__class__.__name__ + " took {0:.2f} seconds".format(mtf - mti))

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
                    self.logger.info(man.__class__.__name__ + " took {0:.2f} seconds".format(mtf - mti))

                    res.installed.extend(man_res.installed)
                    res.total += man_res.total

        if disk_loader:
            disk_loader.stop_working()
            disk_loader.join()

        tf = time.time()
        self.logger.info('Took {0:.2f} seconds'.format(tf - ti))
        return res

    def downgrade(self, app: SoftwarePackage, root_password: str, handler: ProcessWatcher) -> bool:
        man = self._get_manager_for(app)

        if man and app.can_be_downgraded():
            mti = time.time()
            res = man.downgrade(app, root_password, handler)
            mtf = time.time()
            self.logger.info('Took {0:.2f} seconds'.format(mtf - mti))
            return res
        else:
            raise Exception("downgrade is not possible for {}".format(app.__class__.__name__))

    def clean_cache_for(self, app: SoftwarePackage):
        man = self._get_manager_for(app)

        if man:
            return man.clean_cache_for(app)

    def upgrade(self, requirements: GenericUpgradeRequirements, root_password: str, handler: ProcessWatcher) -> bool:
        for man, man_reqs in requirements.sub_requirements.items():
            res = man.upgrade(man_reqs, root_password, handler)

            if not res:
                return False

        return True

    def uninstall(self, app: SoftwarePackage, root_password: str, handler: ProcessWatcher) -> bool:
        man = self._get_manager_for(app)

        if man:
            return man.uninstall(app, root_password, handler)

    def install(self, app: SoftwarePackage, root_password: str, handler: ProcessWatcher) -> bool:
        man = self._get_manager_for(app)

        if man:
            ti = time.time()
            try:
                self.logger.info('Installing {}'.format(app))
                return man.install(app, root_password, handler)
            except:
                traceback.print_exc()
                return False
            finally:
                tf = time.time()
                self.logger.info('Installation of {}'.format(app) + 'took {0:.2f} minutes'.format((tf - ti)/60))

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
            self.logger.info(man.__class__.__name__ + " took {0:.2f} seconds".format(mtf - mti))
            return history

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        pass

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

    def requires_root(self, action: str, app: SoftwarePackage) -> bool:
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

    def prepare(self, task_manager: TaskManager, root_password: str, internet_available: bool):
        if self.managers:
            internet_on = internet.is_available()
            for man in self.managers:
                if man not in self._already_prepared and self._can_work(man):
                    if task_manager:
                        man.prepare(task_manager, root_password, internet_on)
                    self._already_prepared.append(man)

    def list_updates(self, internet_available: bool = None) -> List[PackageUpdate]:
        self._wait_to_be_ready()

        updates = []

        if self.managers:
            net_available = internet.is_available()

            for man in self.managers:
                if self._can_work(man):
                    man_updates = man.list_updates(internet_available=net_available)
                    if man_updates:
                        updates.extend(man_updates)

        return updates

    def _check_for_updates(self) -> str:
        self.logger.info("Checking for updates")

        try:
            releases = self.http_client.get_json('https://api.github.com/repos/vinifmor/bauh/releases')

            if releases:
                latest = None

                for r in releases:
                    if not r['draft']:
                        latest = r
                        break

                if latest and latest.get('tag_name'):
                    notifications_dir = '{}/updates'.format(CACHE_PATH)
                    release_file = '{}/{}'.format(notifications_dir, latest['tag_name'])
                    if os.path.exists(release_file):
                        self.logger.info("Release {} already notified".format(latest['tag_name']))
                    elif latest['tag_name'] > __version__:
                        try:
                            Path(notifications_dir).mkdir(parents=True, exist_ok=True)
                            with open(release_file, 'w+') as f:
                                f.write('')
                        except:
                            self.logger.error("An error occurred while trying to create the update notification file: {}".format(release_file))

                        return self.i18n['warning.update_available'].format(bold(__app_name__), bold(latest['tag_name']), link(latest.get('html_url', '?')))
                    else:
                        self.logger.info("No updates available")
                else:
                    self.logger.warning("No official release found")
            else:
                self.logger.warning("No releases returned from the GitHub API")
        except:
            self.logger.error("An error occurred while trying to retrieve the current releases")

    def list_warnings(self, internet_available: bool = None) -> List[str]:
        warnings = []

        int_available = internet.is_available()

        if int_available:
            updates_msg = self._check_for_updates()

            if updates_msg:
                warnings.append(updates_msg)

        if self.managers:
            for man in self.managers:
                if man.is_enabled():
                    man_warnings = man.list_warnings(internet_available=int_available)

                    if man_warnings:
                        if warnings is None:
                            warnings = []

                        warnings.extend(man_warnings)

        return warnings

    def _fill_suggestions(self, suggestions: list, man: SoftwareManager, limit: int, filter_installed: bool):
        if self._can_work(man):
            mti = time.time()
            man_sugs = man.list_suggestions(limit=limit, filter_installed=filter_installed)
            mtf = time.time()
            self.logger.info(man.__class__.__name__ + ' took {0:.2f} seconds'.format(mtf - mti))

            if man_sugs:
                if 0 < limit < len(man_sugs):
                    man_sugs = man_sugs[0:limit]

                suggestions.extend(man_sugs)

    def list_suggestions(self, limit: int, filter_installed: bool) -> List[PackageSuggestion]:
        if bool(self.config['suggestions']['enabled']):
            if self.managers and internet.is_available():
                suggestions, threads = [], []
                for man in self.managers:
                    t = Thread(target=self._fill_suggestions, args=(suggestions, man, int(self.config['suggestions']['by_type']), filter_installed))
                    t.start()
                    threads.append(t)

                for t in threads:
                    t.join()

                if suggestions:
                    suggestions.sort(key=lambda s: s.priority.value, reverse=True)

                return suggestions
        return []

    def execute_custom_action(self, action: CustomSoftwareAction, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher):
        man = action.manager if action.manager else self._get_manager_for(pkg)

        if man:
            return eval('man.{}({}root_password=root_password, watcher=watcher)'.format(action.manager_method, 'pkg=pkg, ' if pkg else ''))

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: SoftwarePackage):
        self._wait_to_be_ready()

        man = self._get_manager_for(pkg)

        if man:
            self.logger.info('Launching {}'.format(pkg))
            man.launch(pkg)

    def get_screenshots(self, pkg: SoftwarePackage):
        man = self._get_manager_for(pkg)

        if man:
            return man.get_screenshots(pkg)

    def get_working_managers(self):
        return [m for m in self.managers if self._can_work(m)]

    def get_settings(self, screen_width: int, screen_height: int) -> ViewComponent:
        if self.settings_manager is None:
            self.settings_manager = GenericSettingsManager(managers=self.managers,
                                                           working_managers=self.working_managers,
                                                           logger=self.logger,
                                                           i18n=self.i18n)
        else:
            self.settings_manager.managers = self.managers
            self.settings_manager.working_managers = self.working_managers

        return self.settings_manager.get_settings(screen_width=screen_width, screen_height=screen_height)

    def save_settings(self, component: TabGroupComponent) -> Tuple[bool, List[str]]:
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

    def get_upgrade_requirements(self, pkgs: List[SoftwarePackage], root_password: str, watcher: ProcessWatcher) -> UpgradeRequirements:
        by_manager = self._map_pkgs_by_manager(pkgs)
        res = GenericUpgradeRequirements([], [], [], [], {})

        if by_manager:
            for man, pkgs in by_manager.items():
                ti = time.time()
                man_reqs = man.get_upgrade_requirements(pkgs, root_password, watcher)
                tf = time.time()
                self.logger.info(man.__class__.__name__ + " took {0:.2f} seconds".format(tf - ti))

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

    def get_custom_actions(self) -> List[CustomSoftwareAction]:
        if self.managers:
            actions = []

            working_managers = []

            for man in self.managers:
                if self._can_work(man):
                    working_managers.append(man)

            if working_managers:
                working_managers.sort(key=lambda m: m.__class__.__name__)

                for man in working_managers:
                    man_actions = man.get_custom_actions()

                    if man_actions:
                        actions.extend(man_actions)

            return actions

    def _fill_sizes(self, man: SoftwareManager, pkgs: List[SoftwarePackage]):
        ti = time.time()
        man.fill_sizes(pkgs)
        tf = time.time()
        self.logger.info(man.__class__.__name__ + " took {0:.2f} seconds".format(tf - ti))

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
