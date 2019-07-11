import json
import os
from pathlib import Path
from threading import Thread, Lock
from typing import List

from fpakman.core.model import Application, FlatpakApplication
from fpakman.util.cache import Cache


class DiskCacheLoader(Thread):

    def __init__(self, enabled: bool, flatpak_api_cache: Cache, apps: List[Application] = []):
        super(DiskCacheLoader, self).__init__(daemon=True)
        self.apps = apps
        self.stop = False
        self.lock = Lock()
        self.flatpak_api_cache = flatpak_api_cache
        self.enabled = enabled

    def run(self):

        if self.enabled:
            while True:
                if self.apps:
                    self.lock.acquire()
                    app = self.apps[0]
                    del self.apps[0]
                    self.lock.release()
                    self.fill_cached_data(app)
                elif self.stop:
                    break

    def add(self, app: Application):
        if self.enabled:
            if app and app.supports_disk_cache():
                self.lock.acquire()
                self.apps.append(app)
                self.lock.release()

    def fill_cached_data(self, app: Application):
        if self.enabled:
            if os.path.exists(app.get_disk_data_path()):
                with open(app.get_disk_data_path()) as f:
                    cached_data = json.loads(f.read())
                    app.fill_cached_data(cached_data)

                    if isinstance(app, FlatpakApplication):
                        self.flatpak_api_cache.add_non_existing(app.base_data.id, cached_data)


class DiskCacheLoaderFactory:

    def __init__(self, disk_cache: bool, flatpak_api_cache: Cache):
        self.disk_cache = disk_cache
        self.flatpak_api_cache = flatpak_api_cache

    def new(self):
        return DiskCacheLoader(enabled=self.disk_cache, flatpak_api_cache=self.flatpak_api_cache)


def save(app: Application, icon_bytes: bytes = None, only_icon: bool = False):

    if app.supports_disk_cache():

        if not only_icon:
            Path(app.get_disk_cache_path()).mkdir(parents=True, exist_ok=True)

            if isinstance(app, FlatpakApplication):
                data = app.get_data_to_cache()

                with open(app.get_disk_data_path(), 'w+') as f:
                    f.write(json.dumps(data))

        if icon_bytes:
            Path(app.get_disk_cache_path()).mkdir(parents=True, exist_ok=True)

            with open(app.get_disk_icon_path(), 'wb+') as f:
                f.write(icon_bytes)
