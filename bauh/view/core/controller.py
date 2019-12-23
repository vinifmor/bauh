import re
import time
import traceback
from threading import Thread
from typing import List, Set, Type

from bauh.api.abstract.controller import SoftwareManager, SearchResult, ApplicationContext
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageUpdate, PackageHistory, PackageSuggestion, PackageAction
from bauh.api.exception import NoInternetException
from bauh.commons import internet

RE_IS_URL = re.compile(r'^https?://.+')


class GenericSoftwareManager(SoftwareManager):

    def __init__(self, managers: List[SoftwareManager], context: ApplicationContext, config: dict):
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

        if internet.is_available(self.context.http_client, self.context.logger):
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

    def _is_internet_available(self, res: dict):
        res['available'] = internet.is_available(self.context.http_client, self.context.logger)

    def _get_internet_check(self, res: dict) -> Thread:
        t = Thread(target=self._is_internet_available, args=(res,))
        t.start()
        return t

    def read_installed(self, disk_loader: DiskCacheLoader = None, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, net_check: bool = None) -> SearchResult:
        ti = time.time()
        self._wait_to_be_ready()

        net_check = {}
        thread_internet_check = self._get_internet_check(net_check)

        res = SearchResult([], None, 0)

        disk_loader = None

        if not pkg_types:  # any type
            for man in self.managers:
                if self._can_work(man):
                    if not disk_loader:
                        disk_loader = self.disk_loader_factory.new()
                        disk_loader.start()

                    if thread_internet_check.isAlive():
                        thread_internet_check.join()

                    mti = time.time()
                    man_res = man.read_installed(disk_loader=disk_loader, pkg_types=None, internet_available=net_check['available'])
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

                    thread_internet_check.join()
                    mti = time.time()
                    man_res = man.read_installed(disk_loader=disk_loader, pkg_types=None, internet_available=net_check['available'])
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
            return man.downgrade(app, root_password, handler)
        else:
            raise Exception("downgrade is not possible for {}".format(app.__class__.__name__))

    def clean_cache_for(self, app: SoftwarePackage):
        man = self._get_manager_for(app)

        if man:
            return man.clean_cache_for(app)

    def update(self, app: SoftwarePackage, root_password: str, handler: ProcessWatcher) -> bool:
        man = self._get_manager_for(app)

        if man:
            return man.update(app, root_password, handler)

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
            return man.get_history(app)

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        pass

    def is_enabled(self):
        return True

    def _get_manager_for(self, app: SoftwarePackage) -> SoftwareManager:
        man = self.map[app.__class__]
        return man if man and self._can_work(man) else None

    def cache_to_disk(self, pkg: SoftwarePackage, icon_bytes: bytes, only_icon: bool):
        if self.context.disk_cache and pkg.supports_disk_cache():
            man = self._get_manager_for(pkg)

            if man:
                return man.cache_to_disk(pkg, icon_bytes=icon_bytes, only_icon=only_icon)

    def requires_root(self, action: str, app: SoftwarePackage):
        man = self._get_manager_for(app)

        if man:
            return man.requires_root(action, app)

    def _prepare(self):
        if self.managers:
            for man in self.managers:
                if man not in self._already_prepared and self._can_work(man):
                    man.prepare()
                    self._already_prepared.append(man)

    def prepare(self):
        self.thread_prepare = Thread(target=self._prepare)
        self.thread_prepare.start()

    def list_updates(self, net_check: bool = None) -> List[PackageUpdate]:
        self._wait_to_be_ready()

        updates = []

        if self.managers:
            net_check = {}
            thread_internet_check = self._get_internet_check(net_check)

            for man in self.managers:
                if self._can_work(man):

                    if thread_internet_check.is_alive():
                        thread_internet_check.join()

                    man_updates = man.list_updates(internet_available=net_check['available'])
                    if man_updates:
                        updates.extend(man_updates)

        return updates

    def list_warnings(self, internet_available: bool = None) -> List[str]:
        warnings = []

        if self.managers:
            int_available = internet.is_available(self.context.http_client, self.context.logger)

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
            if self.managers and internet.is_available(self.context.http_client, self.context.logger):
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

    def execute_custom_action(self, action: PackageAction, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher):
        man = self._get_manager_for(pkg)

        if man:
            return exec('man.{}(pkg=pkg, root_password=root_password, watcher=watcher)'.format(action.manager_method))

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
