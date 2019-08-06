import time
from abc import ABC, abstractmethod
from argparse import Namespace
from typing import List, Dict

from fpakman.core.disk import DiskCacheLoader, DiskCacheLoaderFactory
from fpakman.core.model import Application, ApplicationUpdate
from fpakman.core.system import FpakmanProcess


class ApplicationManager(ABC):

    def __init__(self, app_args, locale_keys: dict):
        self.app_args = app_args
        self.locale_keys = locale_keys

    @abstractmethod
    def search(self, word: str, disk_loader: DiskCacheLoader) -> Dict[str, List[Application]]:
        pass

    @abstractmethod
    def read_installed(self, disk_loader: DiskCacheLoader) -> List[Application]:
        pass

    @abstractmethod
    def downgrade_app(self, app: Application, root_password: str) -> FpakmanProcess:
        pass

    @abstractmethod
    def clean_cache_for(self, app: Application):
        pass

    @abstractmethod
    def can_downgrade(self):
        pass

    @abstractmethod
    def update_and_stream(self, app: Application) -> FpakmanProcess:
        pass

    @abstractmethod
    def uninstall_and_stream(self, app: Application, root_password: str) -> FpakmanProcess:
        pass

    @abstractmethod
    def get_app_type(self):
        pass

    @abstractmethod
    def get_info(self, app: Application) -> dict:
        pass

    @abstractmethod
    def get_history(self, app: Application) -> List[dict]:
        pass

    @abstractmethod
    def install_and_stream(self, app: Application, root_password: str) -> FpakmanProcess:
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        pass

    @abstractmethod
    def cache_to_disk(self, app: Application, icon_bytes: bytes, only_icon: bool):
        pass

    @abstractmethod
    def requires_root(self, action: str, app: Application):
        pass

    @abstractmethod
    def refresh(self, app: Application, root_password: str) -> FpakmanProcess:
        pass

    @abstractmethod
    def prepare(self):
        """
        Callback executed before the ApplicationManager starts to work.
        :return:
        """
        pass

    @abstractmethod
    def list_updates(self) -> List[ApplicationUpdate]:
        pass

    @abstractmethod
    def list_warnings(self) -> List[str]:
        pass

    @abstractmethod
    def list_suggestions(self, limit: int) -> List[Application]:
        pass


class GenericApplicationManager(ApplicationManager):

    def __init__(self, managers: List[ApplicationManager], disk_loader_factory: DiskCacheLoaderFactory, app_args: Namespace):
        super(ApplicationManager, self).__init__()
        self.managers = managers
        self.map = {m.get_app_type(): m for m in self.managers}
        self.disk_loader_factory = disk_loader_factory
        self._enabled_map = {} if app_args.check_packaging_once else None

    def _sort(self, apps: List[Application], word: str) -> List[Application]:
        exact_name_matches, contains_name_matches, others = [], [], []

        for app in apps:
            lower_name = app.base_data.name.lower()

            if word == lower_name:
                exact_name_matches.append(app)
            elif word in lower_name:
                contains_name_matches.append(app)
            else:
                others.append(app)

        res = []
        for app_list in (exact_name_matches, contains_name_matches, others):
            app_list.sort(key=lambda a: a.base_data.name.lower())
            res.extend(app_list)

        return res

    def _is_enabled(self, man: ApplicationManager):

        if self._enabled_map is not None:
            enabled = self._enabled_map.get(man.get_app_type())

            if enabled is None:
                enabled = man.is_enabled()
                self._enabled_map[man.get_app_type()] = enabled

            return enabled
        else:
            return man.is_enabled()

    def search(self, word: str, disk_loader: DiskCacheLoader = None) -> Dict[str, List[Application]]:
        res = {'installed': [], 'new': []}

        norm_word = word.strip().lower()
        disk_loader = None

        for man in self.managers:
            if self._is_enabled(man):
                if not disk_loader:
                    disk_loader = self.disk_loader_factory.new()
                    disk_loader.start()

                apps_found = man.search(word=norm_word, disk_loader=disk_loader)
                res['installed'].extend(apps_found['installed'])
                res['new'].extend(apps_found['new'])

        if disk_loader:
            disk_loader.stop = True
            disk_loader.join()

        for key in res:
            res[key] = self._sort(res[key], norm_word)

        return res

    def read_installed(self, disk_loader: DiskCacheLoader = None) -> List[Application]:
        installed = []

        disk_loader = None

        for man in self.managers:
            if self._is_enabled(man):
                if not disk_loader:
                    disk_loader = self.disk_loader_factory.new()
                    disk_loader.start()

                installed.extend(man.read_installed(disk_loader=disk_loader))

        if disk_loader:
            disk_loader.stop = True
            disk_loader.join()

        installed.sort(key=lambda a: a.base_data.name.lower())

        return installed

    def can_downgrade(self):
        return True

    def downgrade_app(self, app: Application, root_password: str) -> FpakmanProcess:
        man = self._get_manager_for(app)

        if man and man.can_downgrade():
            return man.downgrade_app(app, root_password)
        else:
            raise Exception("downgrade is not possible for {}".format(app.__class__.__name__))

    def clean_cache_for(self, app: Application):
        man = self._get_manager_for(app)

        if man:
            return man.clean_cache_for(app)

    def update_and_stream(self, app: Application) -> FpakmanProcess:
        man = self._get_manager_for(app)

        if man:
            return man.update_and_stream(app)

    def uninstall_and_stream(self, app: Application, root_password: str) -> FpakmanProcess:
        man = self._get_manager_for(app)

        if man:
            return man.uninstall_and_stream(app, root_password)

    def install_and_stream(self, app: Application, root_password: str) -> FpakmanProcess:
        man = self._get_manager_for(app)

        if man:
            return man.install_and_stream(app, root_password)

    def get_info(self, app: Application):
        man = self._get_manager_for(app)

        if man:
            return man.get_info(app)

    def get_history(self, app: Application):
        man = self._get_manager_for(app)

        if man:
            return man.get_history(app)

    def get_app_type(self):
        return None

    def is_enabled(self):
        return True

    def _get_manager_for(self, app: Application) -> ApplicationManager:
        man = self.map[app.__class__]
        return man if man and self._is_enabled(man) else None

    def cache_to_disk(self, app: Application, icon_bytes: bytes, only_icon: bool):
        if self.disk_loader_factory.disk_cache and app.supports_disk_cache():
            man = self._get_manager_for(app)

            if man:
                return man.cache_to_disk(app, icon_bytes=icon_bytes, only_icon=only_icon)

    def requires_root(self, action: str, app: Application):
        man = self._get_manager_for(app)

        if man:
            return man.requires_root(action, app)

    def refresh(self, app: Application, root_password: str) -> FpakmanProcess:
        man = self._get_manager_for(app)

        if man:
            return man.refresh(app, root_password)

    def prepare(self):
        if self.managers:
            for man in self.managers:
                if self._is_enabled(man):
                    man.prepare()

    def list_updates(self) -> List[ApplicationUpdate]:
        updates = []

        if self.managers:
            for man in self.managers:
                if self._is_enabled(man):
                    updates.extend(man.list_updates())

        return updates

    def list_warnings(self) -> List[str]:
        if self.managers:
            warnings = None

            for man in self.managers:
                man_warnings = man.list_warnings()

                if man_warnings:
                    if warnings is None:
                        warnings = []

                    warnings.extend(man_warnings)

            return warnings

    def list_suggestions(self, limit: int) -> List[Application]:
        if self.managers:
            suggestions = []
            for man in self.managers:
                if self._is_enabled(man):
                    suggestions.extend(man.list_suggestions(6))
            return suggestions
