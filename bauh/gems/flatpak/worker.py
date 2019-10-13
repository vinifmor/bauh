import traceback
from threading import Thread

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.model import PackageStatus
from bauh.api.http import HttpClient

from bauh.gems.flatpak import flatpak
from bauh.gems.flatpak.constants import FLATHUB_API_URL, FLATHUB_URL
from bauh.gems.flatpak.model import FlatpakApplication


class FlatpakAsyncDataLoader(Thread):

    def __init__(self, app: FlatpakApplication, manager: SoftwareManager, context: ApplicationContext, api_cache: MemoryCache):
        super(FlatpakAsyncDataLoader, self).__init__(daemon=True)
        self.app = app
        self.manager = manager
        self.http_client = context.http_client
        self.api_cache = api_cache
        self.persist = False
        self.logger = context.logger

    def run(self):
        if self.app:
            self.app.status = PackageStatus.LOADING_DATA

            try:
                res = self.http_client.get('{}/apps/{}'.format(FLATHUB_API_URL, self.app.id))

                if res and res.text:
                    data = res.json()

                    if not self.app.version:
                        self.app.version = data.get('version')

                    if not self.app.name:
                        self.app.name = data.get('name')

                    self.app.description = data.get('description', data.get('summary', None))
                    self.app.icon_url = data.get('iconMobileUrl', None)
                    self.app.latest_version = data.get('currentReleaseVersion', self.app.version)

                    if self.app.latest_version and (not self.app.version or not self.app.update):
                        self.app.version = self.app.latest_version

                    if not self.app.installed and self.app.latest_version:
                        self.app.version = self.app.latest_version

                    if self.app.icon_url and self.app.icon_url.startswith('/'):
                        self.app.icon_url = FLATHUB_URL + self.app.icon_url

                    if data.get('categories'):
                        self.app.categories = [c['name'] for c in data['categories']]

                    loaded_data = self.app.get_data_to_cache()

                    self.api_cache.add(self.app.id, loaded_data)
                    self.persist = self.app.supports_disk_cache()
                else:
                    self.logger.warning("Could not retrieve app data for id '{}'. Server response: {}. Body: {}".format(self.app.id, res.status_code, res.content.decode()))
            except:
                self.logger.error("Could not retrieve app data for id '{}'".format(self.app.id))
                traceback.print_exc()

            self.app.status = PackageStatus.READY

            if self.persist:
                self.manager.cache_to_disk(pkg=self.app, icon_bytes=None, only_icon=False)


class FlatpakUpdateLoader(Thread):

    def __init__(self, app: FlatpakApplication, http_client: HttpClient):
        super(FlatpakUpdateLoader, self).__init__(daemon=True)
        self.app = app
        self.http_client = http_client

    def run(self):
        try:
            data = self.http_client.get_json('{}/apps/{}'.format(FLATHUB_API_URL, self.app.id))

            if data and data.get('currentReleaseVersion'):
                self.app.version = data['currentReleaseVersion']
                self.app.latest_version = self.app.version
        except:
            traceback.print_exc()
