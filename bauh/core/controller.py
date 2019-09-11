from argparse import Namespace
from threading import Thread
from typing import List, Set, Type

from bauh.api.abstract.controller import SoftwareManager, SearchResult, ApplicationContext
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageUpdate, PackageHistory, PackageSuggestion, PackageAction

SUGGESTIONS_LIMIT = 5


class GenericSoftwareManager(SoftwareManager):

    def __init__(self, managers: List[SoftwareManager], context: ApplicationContext, app_args: Namespace):
        super(GenericSoftwareManager, self).__init__(context=context)
        self.managers = managers
        self.map = {t: m for m in self.managers for t in m.get_managed_types()}
        self._enabled_map = {} if app_args.check_packaging_once else None
        self.thread_prepare = None
        self.i18n = context.i18n
        self.disk_loader_factory = context.disk_loader_factory

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

    def _is_enabled(self, man: SoftwareManager):

        if self._enabled_map is not None:
            enabled = self._enabled_map.get(man.get_managed_types())

            if enabled is None:
                enabled = man.is_enabled()
                self._enabled_map[man.get_managed_types()] = enabled

            return enabled
        else:
            return man.is_enabled()

    def _search(self, word: str, man: SoftwareManager, disk_loader, res: SearchResult):
        if self._is_enabled(man):
            apps_found = man.search(words=word, disk_loader=disk_loader)
            res.installed.extend(apps_found.installed)
            res.new.extend(apps_found.new)

    def search(self, word: str, disk_loader: DiskCacheLoader = None, limit: int = -1) -> SearchResult:
        self._wait_to_be_ready()

        res = SearchResult([], [], 0)

        norm_word = word.strip().lower()
        disk_loader = self.disk_loader_factory.new()
        disk_loader.start()

        threads = []

        for man in self.managers:
            t = Thread(target=self._search, args=(norm_word, man, disk_loader, res))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        if disk_loader:
            disk_loader.stop = True
            disk_loader.join()

        res.installed = self._sort(res.installed, norm_word)
        res.new = self._sort(res.new, norm_word)
        res.total = len(res.installed) + len(res.new)

        return res

    def _wait_to_be_ready(self):
        if self.thread_prepare:
            self.thread_prepare.join()
            self.thread_prepare = None

    def read_installed(self, disk_loader: DiskCacheLoader = None, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None) -> SearchResult:
        self._wait_to_be_ready()

        res = SearchResult([], None, 0)

        disk_loader = None

        if not pkg_types:  # any type
            for man in self.managers:
                if self._is_enabled(man):
                    if not disk_loader:
                        disk_loader = self.disk_loader_factory.new()
                        disk_loader.start()

                    man_res = man.read_installed(disk_loader=disk_loader, pkg_types=None)
                    res.installed.extend(man_res.installed)
                    res.total += man_res.total
        else:
            man_already_used = []

            for t in pkg_types:
                man = self.map.get(t)
                if man and (man not in man_already_used) and self._is_enabled(man):

                    if not disk_loader:
                        disk_loader = self.disk_loader_factory.new()
                        disk_loader.start()

                    man_res = man.read_installed(disk_loader=disk_loader, pkg_types=None)
                    res.installed.extend(man_res.installed)
                    res.total += man_res.total

        if disk_loader:
            disk_loader.stop = True
            disk_loader.join()

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
            return man.install(app, root_password, handler)

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
        return man if man and self._is_enabled(man) else None

    def cache_to_disk(self, app: SoftwarePackage, icon_bytes: bytes, only_icon: bool):
        if self.context.disk_cache and app.supports_disk_cache():
            man = self._get_manager_for(app)

            if man:
                return man.cache_to_disk(app, icon_bytes=icon_bytes, only_icon=only_icon)

    def requires_root(self, action: str, app: SoftwarePackage):
        man = self._get_manager_for(app)

        if man:
            return man.requires_root(action, app)

    def refresh(self, app: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        self._wait_to_be_ready()

        man = self._get_manager_for(app)

        if man:
            return man.refresh(app, root_password, watcher)

    def _prepare(self):
        if self.managers:
            for man in self.managers:
                if self._is_enabled(man):
                    man.prepare()

    def prepare(self):
        self.thread_prepare = Thread(target=self._prepare)
        self.thread_prepare.start()

    def list_updates(self) -> List[PackageUpdate]:
        self._wait_to_be_ready()

        updates = []

        if self.managers:
            for man in self.managers:
                if self._is_enabled(man):
                    man_updates = man.list_updates()
                    if man_updates:
                        updates.extend(man_updates)

        return updates

    def list_warnings(self) -> List[str]:
        warnings = []

        if self.managers:
            for man in self.managers:
                man_warnings = man.list_warnings()

                if man_warnings:
                    if warnings is None:
                        warnings = []

                    warnings.extend(man_warnings)
        else:
            warnings.append(self.i18n['warning.no_managers'])

        return warnings

    def _fill_suggestions(self, suggestions: list, man: SoftwareManager, limit: int):
        if self._is_enabled(man):
            man_sugs = man.list_suggestions(limit)

            if man_sugs:
                if len(man_sugs) > limit:
                    man_sugs = man_sugs[0:limit]

                suggestions.extend(man_sugs)

    def list_suggestions(self, limit: int) -> List[PackageSuggestion]:
        if self.managers:
            suggestions, threads = [], []
            for man in self.managers:
                t = Thread(target=self._fill_suggestions, args=(suggestions, man, SUGGESTIONS_LIMIT))
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            if suggestions:
                suggestions.sort(key=lambda s: s.priority.value, reverse=True)

            return suggestions

    def execute_custom_action(self, action: PackageAction, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher):
        man = self._get_manager_for(pkg)

        if man:
            return exec('man.{}(pkg=pkg, root_password=root_password, watcher=watcher)'.format(action.manager_method))
