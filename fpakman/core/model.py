from threading import Lock, Thread
from typing import List

import requests
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest

from fpakman.core import flatpak

__FLATHUB_URL__ = 'https://flathub.org'
__FLATHUB_API_URL__ = __FLATHUB_URL__ + '/api/v1'


class FlatpakManager:

    def __init__(self):
        self.apps = []
        self.apps_db = {}
        self.http_session = requests.Session()
        self.lock_db_read = Lock()

    def load_database_async(self):
        Thread(target=self.load_database, daemon=True).start()

    def load_database(self):

        self.lock_db_read.acquire()

        try:
            res = self.http_session.get(__FLATHUB_API_URL__ + '/apps')

            if res.status_code == 200:
                for app in res.json():
                    self.apps_db[app['flatpakAppId']] = app
        finally:
            self.lock_db_read.release()

    def get_version(self):
        return flatpak.get_version()

    def read_installed(self) -> List[dict]:

        installed = flatpak.list_installed()

        if installed:
            installed.sort(key=lambda p: p['name'].lower())

            available_updates = flatpak.list_updates_as_str()

            for app in installed:

                if not self.apps_db:
                    self.load_database()

                if self.apps_db:
                    app_data = self.apps_db.get(app['id'], None)
                else:
                    app_data = None

                if not app_data:
                    app['latest_version'] = None
                    app['icon'] = None
                else:
                    app['latest_version'] = app_data['currentReleaseVersion']
                    app['icon'] = app_data['iconMobileUrl']

                    if app['icon'].startswith('/'):
                        app['icon'] = __FLATHUB_URL__ + app['icon']

                app['update'] = app['id'] in available_updates

        self.apps = installed
        return [*self.apps]

    def update_apps(self, refs: List[str]) -> List[dict]:

        if self.apps:

            for ref in refs:
                package_found = [app for app in self.apps if app['ref'] == ref]

                if package_found:
                    package_found = package_found[0]
                    updated = flatpak.update(ref)

                    if updated:
                        package_found['update'] = not updated

            return [*self.apps]

        return []

    def update_app(self, ref: str):

        """
        :param ref:
        :return: the update command stream
        """

        if self.apps:

            package_found = [app for app in self.apps if app['ref'] == ref]

            if package_found:
                return flatpak.update_and_stream(ref)

        return None
