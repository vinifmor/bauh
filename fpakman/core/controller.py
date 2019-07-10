from abc import ABC, abstractmethod
from datetime import datetime
from threading import Lock
from typing import List

import requests

from fpakman.core import flatpak
from fpakman.core.model import FlatpakApplication, ApplicationData, ApplicationStatus, Application
from fpakman.core.worker import FlatpakAsyncDataLoaderManager
from fpakman.util.cache import Cache


class ApplicationManager(ABC):

    @abstractmethod
    def search(self, word: str) -> List[Application]:
        pass

    @abstractmethod
    def read_installed(self) -> List[Application]:
        pass

    @abstractmethod
    def downgrade_app(self, app: Application, root_password: str):
        pass

    @abstractmethod
    def clean_cache_for(self, app: Application):
        pass

    @abstractmethod
    def can_downgrade(self):
        pass

    @abstractmethod
    def update_and_stream(self, app: Application):
        pass

    @abstractmethod
    def uninstall_and_stream(self, app: Application):
        pass

    @abstractmethod
    def get_app_type(self) -> str:
        pass

    @abstractmethod
    def get_info(self, app: Application) -> dict:
        pass

    @abstractmethod
    def get_history(self, app: Application) -> List[dict]:
        pass

    @abstractmethod
    def install_and_stream(self, app: Application):
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        pass


class FlatpakManager(ApplicationManager):

    def __init__(self, api_cache: Cache):
        self.api_cache = api_cache
        self.http_session = requests.Session()
        self.lock_read = Lock()
        self.async_data_loader = FlatpakAsyncDataLoaderManager(api_cache=self.api_cache)
        flatpak.set_default_remotes()

    def get_app_type(self):
        return FlatpakApplication

    def _map_to_model(self, app: dict) -> FlatpakApplication:

        model = FlatpakApplication(arch=app.get('arch'),
                                   branch=app.get('branch'),
                                   origin=app.get('origin'),
                                   runtime=app.get('runtime'),
                                   ref=app.get('ref'),
                                   commit=app.get('commit'),
                                   base_data=ApplicationData(id=app.get('id'),
                                                             name=app.get('name'),
                                                             version=app.get('version'),
                                                             latest_version=app.get('latest_version')))

        api_data = self.api_cache.get(app['id'])

        expired_data = api_data and api_data.get('expires_at') and api_data['expires_at'] <= datetime.utcnow()

        if not api_data or expired_data:
            if not app['runtime']:
                model.status = ApplicationStatus.LOADING_DATA
                self.async_data_loader.load(model)

        else:  # filling cached data
            for attr, val in api_data.items():
                if attr != 'expires_at' and val:
                    setattr(model.base_data, attr, val)

        return model

    def search(self, word: str) -> List[FlatpakApplication]:

        res = []
        apps_found = flatpak.search(word)

        if apps_found:

            already_read = set()
            installed_apps = self.read_installed(keep_workers=True)

            if installed_apps:
                for app_found in apps_found:
                    for installed_app in installed_apps:
                        if app_found['id'] == installed_app.base_data.id:
                            res.append(installed_app)
                            already_read.add(app_found['id'])

            for app_found in apps_found:
                if app_found['id'] not in already_read:
                    res.append(self._map_to_model(app_found))

            self.async_data_loader.stop_current_workers()

        return res

    def read_installed(self, keep_workers: bool = False) -> List[FlatpakApplication]:

        self.lock_read.acquire()

        try:
            installed = flatpak.list_installed()

            if installed:
                installed.sort(key=lambda p: p['name'].lower())

                available_updates = flatpak.list_updates_as_str()

                models = []

                for app in installed:
                    model = self._map_to_model(app)
                    model.installed = True
                    model.update = app['id'] in available_updates
                    models.append(model)

                if not keep_workers:
                    self.async_data_loader.stop_current_workers()

                return models

            return []

        finally:
            self.lock_read.release()

    def can_downgrade(self):
        return True

    def downgrade_app(self, app: FlatpakApplication, root_password: str):

        commits = flatpak.get_app_commits(app.ref, app.origin)
        commit_idx = commits.index(app.commit)

        # downgrade is not possible if the app current commit in the first one:
        if commit_idx == len(commits) - 1:
            return None

        return flatpak.downgrade_and_stream(app.ref, commits[commit_idx + 1], root_password)

    def clean_cache_for(self, app: FlatpakApplication):
        self.api_cache.delete(app.base_data.id)

    def update_and_stream(self, app: FlatpakApplication):
        return flatpak.update_and_stream(app.ref)

    def uninstall_and_stream(self, app: FlatpakApplication):
        return flatpak.uninstall_and_stream(app.ref)

    def get_info(self, app: FlatpakApplication) -> dict:
        app_info = flatpak.get_app_info_fields(app.base_data.id, app.branch)
        app_info['name'] = app.base_data.name
        app_info['type'] = 'runtime' if app.runtime else 'app'
        app_info['description'] = app.base_data.description
        return app_info

    def get_history(self, app: FlatpakApplication) -> List[dict]:
        return flatpak.get_app_commits_data(app.ref, app.origin)

    def install_and_stream(self, app: FlatpakApplication):
        return flatpak.install_and_stream(app.base_data.id, app.origin)

    def is_enabled(self):
        return flatpak.is_installed()


class GenericApplicationManager(ApplicationManager):

    def __init__(self, managers: List[ApplicationManager]):
        self.managers = managers
        self.map = {m.get_app_type(): m for m in self.managers}

    def search(self, word: str) -> List[Application]:
        apps = []
        for man in self.managers:
            if man.is_enabled():
                apps.extend(man.search(word))

        return apps

    def read_installed(self) -> List[Application]:
        installed = []
        for man in self.managers:
            if man.is_enabled():
                installed.extend(man.read_installed())

        return installed

    def can_downgrade(self):
        return True

    def downgrade_app(self, app: Application, root_password: str):
        man = self._get_manager_for(app)

        if man and man.can_downgrade():
            return man.downgrade_app(app, root_password)
        else:
            raise Exception("downgrade is not possible for {}".format(app.__class__.__name__))

    def clean_cache_for(self, app: Application):
        man = self._get_manager_for(app)

        if man:
            return man.clean_cache_for(app)

    def update_and_stream(self, app: Application):
        man = self._get_manager_for(app)

        if man:
            return man.update_and_stream(app)

    def uninstall_and_stream(self, app: Application):
        man = self._get_manager_for(app)

        if man:
            return man.uninstall_and_stream(app)

    def install_and_stream(self, app: Application):
        man = self._get_manager_for(app)

        if man:
            return man.install_and_stream(app)

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

    def _get_manager_for(self, app: Application):
        man = self.map[app.__class__]
        return man if man and man.is_enabled() else None
