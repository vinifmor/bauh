import traceback
from io import StringIO
from threading import Thread

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.model import PackageStatus
from bauh.api.http import HttpClient
from bauh.gems.flatpak.constants import FLATHUB_API_URL, FLATHUB_URL
from bauh.gems.flatpak.model import FlatpakApplication


class FlatpakAsyncDataLoader(Thread):

    def __init__(self, app: FlatpakApplication, manager: SoftwareManager, context: ApplicationContext, api_cache: MemoryCache, category_cache: MemoryCache):
        super(FlatpakAsyncDataLoader, self).__init__(daemon=True)
        self.app = app
        self.manager = manager
        self.http_client = context.http_client
        self.api_cache = api_cache
        self.persist = False
        self.logger = context.logger
        self.category_cache = category_cache

    @staticmethod
    def format_category(category: str) -> str:
        word = StringIO()
        last_l = None
        for idx, l in enumerate(category):
            if idx != 0 and last_l != ' ' and l.isupper() and idx + 1 < len(category) and category[idx + 1].islower():
                word.write(' ')

            last_l = l.lower()
            word.write(last_l)

        word.seek(0)
        return word.read()

    def run(self):
        if self.app:
            self.app.status = PackageStatus.LOADING_DATA

            try:
                res = self.http_client.get('{}/apps/{}'.format(FLATHUB_API_URL, self.app.id))

                if res and res.text:
                    data = res.json()

                    if not data:
                        self.logger.warning("No data returned for id {} ({})".format(self.app.id, self.app.name))
                    else:
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
                            cats = []
                            for c in data['categories']:
                                cached = self.category_cache.get(c['name'])

                                if not cached:
                                    cached = self.format_category(c['name'])
                                    self.category_cache.add_non_existing(c['name'], cached)

                                cats.append(cached)

                            self.app.categories = cats

                        loaded_data = self.app.get_data_to_cache()

                        self.api_cache.add(self.app.id, loaded_data)
                        self.persist = self.app.supports_disk_cache()
                else:
                    self.logger.warning("Could not retrieve app data for id '{}'. Server response: {}. Body: {}".format(self.app.id, res.status_code if res else '?', res.content.decode() if res else '?'))
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
