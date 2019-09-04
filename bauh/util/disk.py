import json
import os
from threading import Thread, Lock
from typing import Type, Dict

from bauh_api.abstract.cache import MemoryCache
from bauh_api.abstract.disk import DiskCacheLoader, DiskCacheLoaderFactory
from bauh_api.abstract.model import SoftwarePackage


class AsyncDiskCacheLoader(Thread, DiskCacheLoader):

    def __init__(self, enabled: bool, cache_map: Dict[Type[SoftwarePackage], MemoryCache]):
        super(AsyncDiskCacheLoader, self).__init__(daemon=True)
        self.apps = []
        self.stop = False
        self.lock = Lock()
        self.cache_map = cache_map
        self.enabled = enabled

    def fill(self, pkg: SoftwarePackage):
        """
        Adds a package which data must be read from the disk to a queue.
        :param pkg:
        :return:
        """
        if self.enabled:
            if pkg and pkg.supports_disk_cache():
                self.lock.acquire()
                self.apps.append(pkg)
                self.lock.release()

    def run(self):
        if self.enabled:
            while True:
                if self.apps:
                    self.lock.acquire()
                    app = self.apps[0]
                    del self.apps[0]
                    self.lock.release()
                    self._fill_cached_data(app)
                elif self.stop:
                    break

    def _fill_cached_data(self, pkg: SoftwarePackage):
        if self.enabled:
            if os.path.exists(pkg.get_disk_data_path()):
                with open(pkg.get_disk_data_path()) as f:
                    cached_data = json.loads(f.read())
                    pkg.fill_cached_data(cached_data)
                    cache = self.cache_map.get(pkg.__class__)\

                    if cache:
                        cache.add_non_existing(pkg.id, cached_data)


class DefaultDiskCacheLoaderFactory(DiskCacheLoaderFactory):

    def __init__(self, disk_cache_enabled: bool):
        super(DefaultDiskCacheLoaderFactory, self).__init__()
        self.disk_cache_enabled = disk_cache_enabled
        self.cache_map = {}

    def map(self, pkg_type: Type[SoftwarePackage], cache: MemoryCache):
        if pkg_type:
            if pkg_type in self.cache_map:
                raise Exception('{} is already mapped')

            self.cache_map[pkg_type] = cache

    def new(self) -> AsyncDiskCacheLoader:
        return AsyncDiskCacheLoader(enabled=self.disk_cache_enabled, cache_map=self.cache_map)
