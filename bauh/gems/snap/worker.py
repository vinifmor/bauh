import logging
import os
import traceback
from pathlib import Path
from threading import Thread
from typing import Dict, List

import requests

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.model import PackageStatus
from bauh.api.http import HttpClient
from bauh.gems.snap import snap, SNAP_CACHE_PATH
from bauh.gems.snap.constants import SNAP_API_URL
from bauh.gems.snap.model import SnapApplication


class SnapAsyncDataLoader(Thread):

    def __init__(self, app: SnapApplication, manager: SoftwareManager, api_cache: MemoryCache,
                 context: ApplicationContext):
        super(SnapAsyncDataLoader, self).__init__(daemon=True)
        self.app = app
        self.id_ = '{}#{}'.format(self.__class__.__name__, id(self))
        self.manager = manager
        self.http_client = context.http_client
        self.api_cache = api_cache
        self.persist = False
        self.download_icons = context.download_icons
        self.logger = context.logger

    def run(self):
        if self.app:
            self.app.status = PackageStatus.LOADING_DATA

            try:
                res = self.http_client.session.get('{}/search?q={}'.format(SNAP_API_URL, self.app.name))

                if res:
                    try:
                        snap_list = res.json()['_embedded']['clickindex:package']
                    except:
                        self.logger.warning('Snap API response responded differently from expected for app: {}'.format(self.app.name))
                        return

                    if not snap_list:
                        self.logger.warning("Could not retrieve app data for id '{}'. Server response: {}. Body: {}".format(self.app.id, res.status_code, res.content.decode()))
                    else:
                        snap_data = snap_list[0]

                        api_data = {
                            'confinement': snap_data.get('confinement'),
                            'description': snap_data.get('description'),
                            'icon_url': snap_data.get('icon_url') if self.download_icons else None
                        }

                        self.api_cache.add(self.app.id, api_data)
                        self.app.confinement = api_data['confinement']
                        self.app.icon_url = api_data['icon_url']

                        if not api_data.get('description'):
                            api_data['description'] = snap.get_info(self.app.name, ('description',)).get('description')

                        self.app.description = api_data['description']
                        self.persist = self.app.supports_disk_cache()
                else:
                    self.logger.warning("Could not retrieve app data for id '{}'. Server response: {}. Body: {}".format(self.app.id, res.status_code, res.content.decode()))
            except:
                self.logger.error("Could not retrieve app data for id '{}'".format(self.app.id))
                traceback.print_exc()

            self.app.status = PackageStatus.READY

            if self.persist:
                self.manager.cache_to_disk(pkg=self.app, icon_bytes=None, only_icon=False)


class CategoriesDownloader(Thread):

    URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/snap/categories.txt'
    CATEGORIES_FILE_PATH = SNAP_CACHE_PATH + '/categories.txt'

    def __init__(self, http_client: HttpClient, logger: logging.Logger, manager: SoftwareManager, disk_cache: bool):
        super(CategoriesDownloader, self).__init__(daemon=True)
        self.http_client = http_client
        self.logger = logger
        self.manager = manager
        self.disk_cache = disk_cache

    def _read_categories_from_disk(self) -> dict:
        if self.disk_cache and os.path.exists(self.CATEGORIES_FILE_PATH):
            self.logger.info("Reading cached categories from the disk")

            with open(self.CATEGORIES_FILE_PATH) as f:
                categories = f.read()

            return self._map_categories(categories)

        return {}

    def _map_categories(self, categories: str) -> dict:
        categories_map = {}
        for l in categories.split('\n'):
            if l:
                data = l.split('=')
                categories_map[data[0]] = [c.strip() for c in data[1].split(',') if c]

        return categories_map

    def _cache_categories_to_disk(self, categories: str):
        self.logger.info('Caching Snap categories to the disk')

        try:
            Path(SNAP_CACHE_PATH).mkdir(parents=True, exist_ok=True)

            with open(self.CATEGORIES_FILE_PATH, 'w+') as f:
                f.write(categories)

            self.logger.info("Snap categories cached to the disk as '{}'".format(self.CATEGORIES_FILE_PATH))
        except:
            self.logger.error("Could not cache Snap categories to the disk as '{}'".format(self.CATEGORIES_FILE_PATH))
            traceback.print_exc()

    def get_categories(self) -> Dict[str, List[str]]:
        self.logger.info('Downloading Snap category definitions from {}'.format(self.URL_CATEGORIES_FILE))

        try:
            res = self.http_client.get(self.URL_CATEGORIES_FILE)

            if res:
                try:
                    categories = self._map_categories(res.text)
                    self.logger.info('Loaded categories for {} Snap applications'.format(len(categories)))

                    if self.disk_cache and categories:
                        Thread(target=self._cache_categories_to_disk, args=(res.text,), daemon=True).start()

                    return categories
                except:
                    self.logger.error("Could not parse categories definitions")
                    traceback.print_exc()
            else:
                self.logger.info('Could not download {}'.format(self.URL_CATEGORIES_FILE))

        except requests.exceptions.ConnectionError:
            self.logger.warning('The internet connection seems to be off.')

        return self._read_categories_from_disk()

    def run(self):
        categories = self.get_categories()

        if categories:
            self.logger.info("Settings categories to {}".format(self.manager.__class__.__name__))
            self.manager.categories = categories

        self.logger.info('Finished')
