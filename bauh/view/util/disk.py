import json
import logging
import os
import time
from threading import Thread, Lock
from typing import Type, Dict, Any, Optional

import yaml

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.disk import DiskCacheLoader, DiskCacheLoaderFactory
from bauh.api.abstract.model import SoftwarePackage


class AsyncDiskCacheLoader(Thread, DiskCacheLoader):

    def __init__(self, cache_map: Dict[Type[SoftwarePackage], MemoryCache], logger: logging.Logger):
        super(AsyncDiskCacheLoader, self).__init__(daemon=True)
        self.pkgs = []
        self._work = True
        self.lock = Lock()
        self.cache_map = cache_map
        self.logger = logger
        self.processed = 0
        self._working = False

    def fill(self, pkg: SoftwarePackage, sync: bool = False):
        """
        Adds a package which data must be read from the disk to a queue (if not sync)
        :param pkg:
        :param sync:
        :return:
        """
        if pkg and pkg.supports_disk_cache():
            if sync or not self._working:
                self._fill_cached_data(pkg)
            else:
                self.pkgs.append(pkg)

    def read(self, pkg: SoftwarePackage) -> Optional[Dict[str, Any]]:
        if pkg and pkg.supports_disk_cache():
            data_path = pkg.get_disk_data_path()

            if data_path and os.path.isfile(data_path):
                ext = data_path.split('.')[-1]

                try:
                    with open(data_path) as f:
                        file_content = f.read()
                except FileNotFoundError:
                    return

                if file_content:
                    if ext == 'json':
                        cached_data = json.loads(file_content)
                    elif ext in {'yml', 'yaml'}:
                        cached_data = yaml.load(file_content)
                    else:
                        raise Exception(f'The cached data file {data_path} has an unsupported format')

                    if cached_data:
                        return cached_data

                else:
                    self.logger.warning(f"No cached content in file {data_path}")

    def stop_working(self):
        self._work = False

    def run(self):
        self._working = True
        last = 0

        while True:
            time.sleep(0.00001)
            if len(self.pkgs) > self.processed:
                pkg = self.pkgs[last]

                self._fill_cached_data(pkg)
                self.processed += 1
                last += 1
            elif not self._work:
                break

        self._working = False

    def _fill_cached_data(self, pkg: SoftwarePackage) -> bool:
        cached_data = self.read(pkg)

        if cached_data:
            pkg.fill_cached_data(cached_data)
            cache = self.cache_map.get(pkg.__class__)

            if cache:
                cache.add_non_existing(str(pkg.id), cached_data)

            return True

        return False


class DefaultDiskCacheLoaderFactory(DiskCacheLoaderFactory):

    def __init__(self, logger: logging.Logger):
        super(DefaultDiskCacheLoaderFactory, self).__init__()
        self.logger = logger
        self.cache_map = {}

    def map(self, pkg_type: Type[SoftwarePackage], cache: MemoryCache):
        if pkg_type:
            if pkg_type not in self.cache_map:
                self.cache_map[pkg_type] = cache

    def new(self) -> AsyncDiskCacheLoader:
        return AsyncDiskCacheLoader(cache_map=self.cache_map, logger=self.logger)
