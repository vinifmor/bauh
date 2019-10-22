import logging
import os
import traceback
from pathlib import Path
from threading import Thread
from typing import Dict, List

import requests

from bauh.api.abstract.controller import SoftwareManager
from bauh.api.http import HttpClient


class CategoriesDownloader(Thread):

    def __init__(self, id_: str, http_client: HttpClient, logger: logging.Logger, manager: SoftwareManager,
                 disk_cache: bool, url_categories_file: str, disk_cache_dir: str, categories_path: str):
        super(CategoriesDownloader, self).__init__(daemon=True)
        self.id_ = id_
        self.http_client = http_client
        self.logger = logger
        self.manager = manager
        self.disk_cache = disk_cache
        self.url_categories_file = url_categories_file
        self.disk_cache_dir = disk_cache_dir
        self.categories_path = categories_path

    def _msg(self, msg: str):
        return '{}({}): {}'.format(self.__class__.__name__, self.id_, msg)

    def _read_categories_from_disk(self) -> Dict[str, List[str]]:
        if self.disk_cache and os.path.exists(self.categories_path):
            self.logger.info(self._msg("Reading cached categories from the disk"))

            with open(self.categories_path) as f:
                categories = f.read()

            return self._map_categories(categories)

        return {}

    def _map_categories(self, categories: str) -> Dict[str, List[str]]:
        categories_map = {}
        for l in categories.split('\n'):
            if l:
                data = l.split('=')
                categories_map[data[0]] = [c.strip() for c in data[1].split(',') if c]

        return categories_map

    def _cache_categories_to_disk(self, categories: str):
        self.logger.info(self._msg('Caching categories to the disk'))

        try:
            Path(self.disk_cache_dir).mkdir(parents=True, exist_ok=True)

            with open(self.categories_path, 'w+') as f:
                f.write(categories)

            self.logger.info(self._msg("Categories cached to the disk as '{}'".format(self.categories_path)))
        except:
            self.logger.error(self._msg("Could not cache categories to the disk as '{}'".format(self.categories_path)))
            traceback.print_exc()

    def download_categories(self) -> Dict[str, List[str]]:
        self.logger.info(self._msg('Downloading category definitions from {}'.format(self.url_categories_file)))

        try:
            res = self.http_client.get(self.url_categories_file)

            if res:
                try:
                    categories = self._map_categories(res.text)
                    self.logger.info(self._msg('Loaded categories for {} applications'.format(len(categories))))

                    if self.disk_cache and categories:
                        Thread(target=self._cache_categories_to_disk, args=(res.text,), daemon=True).start()

                    return categories
                except:
                    self.logger.error(self._msg("Could not parse categories definitions"))
                    traceback.print_exc()
            else:
                self.logger.info(self._msg('Could not download {}'.format(self.url_categories_file)))

        except requests.exceptions.ConnectionError:
            self.logger.warning(self._msg('The internet connection seems to be off.'))

        return {}

    def _set_categories(self, categories: dict):
        if categories:
            self.logger.info(self._msg("Settings {} categories to {}".format(len(categories), self.manager.__class__.__name__)))
            self.manager.categories = categories

    def _download_and_set(self):
        self._set_categories(self.download_categories())

    def run(self):
        cached = self._read_categories_from_disk()

        if cached:
            self._set_categories(cached)
            Thread(target=self._download_and_set, daemon=True).start()
        else:
            self._download_and_set()

        self.logger.info(self._msg('Finished'))
