from datetime import datetime
from threading import Lock
from typing import List

import requests

from fpakman.core import flatpak
from fpakman.core.model import FlatpakApplication, ApplicationData, ApplicationStatus
from fpakman.core.worker import FlatpakAsyncDataLoaderManager
from fpakman.util.cache import Cache


class FlatpakManager:

    def __init__(self, api_cache: Cache):
        self.api_cache = api_cache
        self.http_session = requests.Session()
        self.lock_read = Lock()
        self.async_data_loader = FlatpakAsyncDataLoaderManager(api_cache=self.api_cache)

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

    def downgrade_app(self, app: FlatpakApplication, root_password: str):

        commits = flatpak.get_app_commits(app.ref, app.origin)
        commit_idx = commits.index(app.commit)

        # downgrade is not possible if the app current commit in the first one:
        if commit_idx == len(commits) - 1:
            return None

        return flatpak.downgrade_and_stream(app.ref, commits[commit_idx + 1], root_password)

    def clean_cache_for(self, app_id: str):
        self.api_cache.delete(app_id)
