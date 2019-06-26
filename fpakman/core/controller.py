from datetime import datetime, timedelta
from threading import Lock, Thread
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

    # TODO remove if not necessary for future releases
    def load_full_database_async(self):
        Thread(target=self.load_full_database, daemon=True).start()

    # TODO remove if not necessary for future releases
    def load_full_database(self):

        self.lock_db_read.acquire()

        try:
            res = self.http_session.get(__FLATHUB_API_URL__ + '/apps')

            if res.status_code == 200:
                for app in res.json():
                    self.cache_apps[app['flatpakAppId']] = app
        finally:
            self.lock_db_read.release()

    def _request_app_data(self, app_id: str):

        try:
            res = self.http_session.get('{}/apps/{}'.format(__FLATHUB_API_URL__, app_id), timeout=60)

            if res.status_code == 200:
                return res.json()
            else:
                print("Could not retrieve app data for id '{}'. Server response: {}".format(app_id, res.status_code))
        except:
            print("Could not retrieve app data for id '{}'. Timeout".format(app_id))
            return None

    def read_installed(self) -> List[dict]:

        self.lock_read.acquire()

        try:
            installed = flatpak.list_installed()

            if installed:
                installed.sort(key=lambda p: p['name'].lower())

                available_updates = flatpak.list_updates_as_str()

                for app in installed:

                    app_data = self.cache_apps.get(app['id'])

                    if (not app['runtime'] and not app_data) or (app_data and app_data['expires_at'] <= datetime.utcnow()):  # if data is not cached or expired, tries to retrieve it
                        app_data = self._request_app_data(app['id'])
                        app_data['expires_at'] = datetime.utcnow() + timedelta(seconds=self.cache_expire)
                        self.cache_apps[app['id']] = app_data

                    if not app_data:
                        app['latest_version'] = None
                        app['icon'] = None
                    else:
                        app['latest_version'] = app_data['currentReleaseVersion']
                        app['icon'] = app_data['iconMobileUrl']

                        if app['icon'].startswith('/'):
                            app['icon'] = __FLATHUB_URL__ + app['icon']

                    app['update'] = app['id'] in available_updates

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
