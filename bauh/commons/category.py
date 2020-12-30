import logging
import os
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Dict, List, Optional

import requests

from bauh.api.abstract.controller import SoftwareManager
from bauh.api.http import HttpClient
from bauh.commons.internet import InternetChecker
from bauh.commons.util import map_timestamp_file


class CategoriesDownloader(Thread):

    def __init__(self, id_: str, http_client: HttpClient, logger: logging.Logger, manager: SoftwareManager,
                 url_categories_file: str, categories_path: str, internet_checker: InternetChecker,
                 expiration: Optional[int] = None, internet_connection: Optional[bool] = True, before=None, after=None):
        """
        :param id_:
        :param http_client:
        :param logger:
        :param manager:
        :param url_categories_file:
        :param categories_path:
        :param expiration: cached file expiration in hours
        :param internet_checker
        :param before:
        :param after:
        """
        super(CategoriesDownloader, self).__init__(daemon=True)
        self.id_ = id_
        self.http_client = http_client
        self.logger = logger
        self.manager = manager
        self.url_categories_file = url_categories_file
        self.categories_path = categories_path
        self.before = before
        self.after = after
        self.expiration = expiration
        self.internet_connection = internet_connection
        self.internet_checker = internet_checker

    def _msg(self, msg: str):
        return '{} [{}]: {}'.format(self.__class__.__name__, self.id_, msg)

    def _read_categories_from_disk(self) -> Dict[str, List[str]]:
        if os.path.exists(self.categories_path):
            self.logger.info(self._msg("Reading cached categories file {}".format(self.categories_path)))

            with open(self.categories_path) as f:
                categories = f.read()

            return self._map_categories(categories)
        else:
            self.logger.warning("No cached categories file {} found".format(self.categories_path))
            return {}

    def _map_categories(self, categories: str) -> Dict[str, List[str]]:
        categories_map = {}
        for l in categories.split('\n'):
            if l:
                data = l.split('=')
                categories_map[data[0]] = [c.strip() for c in data[1].split(',') if c]

        return categories_map

    def _cache_categories_to_disk(self, categories_str: str, timestamp: float):
        self.logger.info(self._msg('Caching downloaded categories to disk'))

        try:
            Path(os.path.dirname(self.categories_path)).mkdir(parents=True, exist_ok=True)

            with open(self.categories_path, 'w+') as f:
                f.write(categories_str)

            self.logger.info(self._msg("Categories cached to file '{}'".format(self.categories_path)))

            categories_ts_path = map_timestamp_file(self.categories_path)
            with open(categories_ts_path, 'w+') as f:
                f.write(str(timestamp))

            self.logger.info(self._msg("Categories timestamp ({}) cached to file '{}'".format(timestamp, categories_ts_path)))
        except:
            self.logger.error(self._msg("Could not cache categories to the disk as '{}'".format(self.categories_path)))
            traceback.print_exc()

    def download_categories(self) -> Dict[str, List[str]]:
        self.logger.info(self._msg('Downloading category definitions from {}'.format(self.url_categories_file)))

        try:
            timestamp = datetime.utcnow().timestamp()
            res = self.http_client.get(self.url_categories_file)
        except requests.exceptions.ConnectionError:
            self.logger.error(self._msg('[{}] Could not download categories. The internet connection seems to be off.'.format(self.id_)))
            return {}

        if not res:
            self.logger.info(self._msg('Could not download {}'.format(self.url_categories_file)))
            return {}

        try:
            categories = self._map_categories(res.text)
            self.logger.info(self._msg('Loaded categories for {} applications'.format(len(categories))))
        except:
            self.logger.error(self._msg("Could not parse categories definitions"))
            traceback.print_exc()
            return {}

        if categories:
            self._cache_categories_to_disk(categories_str=res.text, timestamp=timestamp)

        return categories

    def should_download(self) -> bool:
        if self.internet_connection is False or (self.internet_connection is None and not self.internet_checker.is_available()):
            self.logger.warning(self._msg("No internet connection. The categories file '{}' cannot be updated.".format(self.categories_path)))
            return False

        if self.expiration is None or self.expiration <= 0:
            self.logger.warning(self._msg("No expiration set for the categories file '{}'. It should be downloaded".format(self.categories_path)))
            return True

        if not os.path.exists(self.categories_path):
            self.logger.warning(self._msg("Categories file '{}' does not exist. It should be downloaded.".format(self.categories_path)))
            return True

        categories_ts_path = map_timestamp_file(self.categories_path)

        if not os.path.exists(categories_ts_path):
            self.logger.warning(self._msg("Categories timestamp file '{}' does not exist. The categories file should be re-downloaded.".format(categories_ts_path)))
            return True

        with open(categories_ts_path) as f:
            timestamp_str = f.read()

        try:
            categories_timestamp = datetime.fromtimestamp(float(timestamp_str))
        except:
            self.logger.error(self._msg("An exception occurred when trying to parse the categories file timestamp from '{}'. The categories file should be re-downloaded.".format(categories_ts_path)))
            traceback.print_exc()
            return True

        should_download = (categories_timestamp + timedelta(hours=self.expiration) <= datetime.utcnow())

        if should_download:
            self.logger.info(self._msg("Cached categories file '{}' has expired. A new one should be downloaded.".format(self.categories_path)))
            return True
        else:
            self.logger.info(self._msg("Cached categories file '{}' is up to date. No need to re-download it.".format(self.categories_path)))
            return False

    def run(self):
        ti = time.time()
        if self.before:
            self.before()

        should_download = self.should_download()

        if not should_download:
            cached = self._read_categories_from_disk()
            self.manager.categories = cached
        else:
            self.download_categories()

        if self.after:
            self.after()

        tf = time.time()
        self.logger.info(self._msg('Finished. Took {0:.2f} seconds'.format(tf - ti)))
