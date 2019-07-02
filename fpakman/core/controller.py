from datetime import datetime, timedelta
from threading import Lock
from typing import List

import requests

from fpakman.core import flatpak

__FLATHUB_URL__ = 'https://flathub.org'
__FLATHUB_API_URL__ = __FLATHUB_URL__ + '/api/v1'


class FlatpakManager:

    def __init__(self, cache_expire: int = 60 * 60):
        self.cache_apps = {}
        self.cache_expire = cache_expire
        self.http_session = requests.Session()
        self.lock_db_read = Lock()
        self.lock_read = Lock()

    def load_full_database(self):

        self.lock_db_read.acquire()

        try:
            res = self.http_session.get(__FLATHUB_API_URL__ + '/apps', timeout=30)

            if res.status_code == 200:
                for app in res.json():
                    self.cache_apps[app['flatpakAppId']] = app
        finally:
            self.lock_db_read.release()

    def _request_app_data(self, app_id: str):

        try:
            res = self.http_session.get('{}/apps/{}'.format(__FLATHUB_API_URL__, app_id), timeout=30)

            if res.status_code == 200:
                return res.json()
            else:
                print("Could not retrieve app data for id '{}'. Server response: {}".format(app_id, res.status_code))
        except:
            print("Could not retrieve app data for id '{}'. Timeout".format(app_id))
            return None

    def _fill_api_data(self, app: dict):

        api_data = self.cache_apps.get(app['id'])

        if (not app['runtime'] and not api_data) or (api_data and api_data.get('expires_at') and api_data['expires_at'] <= datetime.utcnow()):  # if api data is not cached or expired, tries to retrieve it
            api_data = self._request_app_data(app['id'])

            if api_data:

                if self.cache_expire > 0:
                    api_data['expires_at'] = datetime.utcnow() + timedelta(seconds=self.cache_expire)

                self.cache_apps[app['id']] = api_data

        if not api_data:
            for attr in ('latest_version', 'icon', 'description'):
                if attr not in app:
                    app[attr] = None
        else:
            app['latest_version'] = api_data.get('currentReleaseVersion')
            app['icon'] = api_data.get('iconMobileUrl')

            for attr in ('name', 'description'):
                if not app.get(attr):
                    app[attr] = api_data.get(attr)

            if app['icon'].startswith('/'):
                app['icon'] = __FLATHUB_URL__ + app['icon']

    def search(self, word: str) -> List[dict]:

        res = []
        apps_found = flatpak.search(word)

        if apps_found:

            already_read = set()
            installed_apps = self.read_installed()

            if installed_apps:
                for app in apps_found:
                    for installed_app in installed_apps:
                        if app['id'] == installed_app['id']:
                            res.append(installed_app)
                            already_read.add(app['id'])

            for app in apps_found:
                if app['id'] not in already_read:
                    app['update'] = False
                    app['installed'] = False
                    self._fill_api_data(app)
                    res.append(app)

        return res

    def read_installed(self) -> List[dict]:

        self.lock_read.acquire()

        try:
            installed = flatpak.list_installed()

            if installed:
                installed.sort(key=lambda p: p['name'].lower())

                available_updates = flatpak.list_updates_as_str()

                for app in installed:
                    self._fill_api_data(app)
                    app['update'] = app['id'] in available_updates
                    app['installed'] = True

            return installed

        finally:
            self.lock_read.release()

    def downgrade_app(self, app: dict, root_password: str):

        commits = flatpak.get_app_commits(app['ref'], app['origin'])
        commit_idx = commits.index(app['commit'])

        # downgrade is not possible if the app current commit in the first one:
        if commit_idx == len(commits) - 1:
            return None

        return flatpak.downgrade_and_stream(app['ref'], commits[commit_idx + 1], root_password)
