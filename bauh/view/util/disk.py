import json
import logging
import os
import time
from threading import Thread, Lock
from typing import Type, Dict

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
        if os.path.exists(pkg.get_disk_data_path()):
            disk_path = pkg.get_disk_data_path()
            ext = disk_path.split('.')[-1]

            with open(disk_path) as f:
                if ext == 'json':
                    cached_data = json.loads(f.read())
                elif ext in {'yml', 'yaml'}:
                    cached_data = yaml.load(f.read())
                else:
                    raise Exception('The cached data file {} has an unsupported format'.format(disk_path))

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
