from typing import List

import requests
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest

from core import flatpak

__FLATHUB_URL__ = 'https://flathub.org'
__FLATHUB_API_URL__ = __FLATHUB_URL__ + '/api/v1'


class FlatpakManager:

    def __init__(self):
        self.packages = []
        self.packages_db = {}
        self.http_session = requests.Session()
        self._load_database()

    def _load_database(self):

        res = self.http_session.get(__FLATHUB_API_URL__ + '/apps')

        if res.status_code == 200:
            for app in res.json():
                self.packages_db[app['flatpakAppId']] = app

    def get_version(self):
        return flatpak.get_version()

    def read_installed(self) -> List[dict]:

        packages = flatpak.list_installed()

        if packages:
            packages.sort(key=lambda p: p['name'].lower())

            available_updates = flatpak.list_updates()

            for pak in packages:

                if self.packages_db:
                    pak_data = self.packages_db.get(pak['id'], None)
                else:
                    pak_data = None

                if not pak_data:
                    pak['latest_version'] = None
                    pak['icon'] = None
                else:
                    pak['latest_version'] = pak_data['currentReleaseVersion']
                    pak['icon'] = pak_data['iconDesktopUrl']

                    if pak['icon'].startswith('/'):
                        pak['icon'] = __FLATHUB_URL__ + pak['icon']

                pak['update'] = pak['id'] in available_updates

        self.packages = packages
        return [*self.packages]

    def update_packages(self, refs: List[str]) -> List[dict]:

        if self.packages:

            for ref in refs:
                package_found = [pak for pak in self.packages if pak['ref'] == ref]

                if package_found:
                    package_found = package_found[0]
                    updated = flatpak.update(ref)

                    if updated:
                        package_found['update'] = not updated

            return [*self.packages]

        return []
