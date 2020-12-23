import datetime
import time
from threading import Lock, Thread
from typing import Optional

from bauh.api.abstract.cache import MemoryCache, MemoryCacheFactory


class DefaultMemoryCache(MemoryCache):
    """
    A synchronized cache implementation
    """

    def __init__(self, expiration_time: int):
        super(DefaultMemoryCache, self).__init__()
        self.expiration_time = expiration_time
        self._cache = {}
        self.lock = Lock()

    def is_enabled(self):
        return self.expiration_time < 0 or self.expiration_time > 0

    def add(self, key: str, val: object):
        if key and self.is_enabled():
            self.lock.acquire()
            self._add(key, val)
            self.lock.release()

    def _add(self, key: str, val: object):
        if key:
            self._cache[key] = {'val': val, 'expires_at': datetime.datetime.utcnow() + datetime.timedelta(seconds=self.expiration_time) if self.expiration_time > 0 else None}

    def add_non_existing(self, key: str, val: object):
        if key and self. is_enabled():
            self.lock.acquire()
            cur_val = self.get(key, lock=False)

            if cur_val is None:
                self._add(key, val)

            self.lock.release()

    def get(self, key: str, lock: bool = True):
        if key and self.is_enabled():
            val = self._cache.get(key)

            if val:
                expiration = val.get('expires_at')

                if expiration and expiration <= datetime.datetime.utcnow():
                    if lock:
                        self.lock.acquire()

                    del self._cache[key]

                    if lock:
                        self.lock.release()

                    return None

                return val['val']

    def delete(self, key):
        if key and self.is_enabled():
            if key in self._cache:
                self.lock.acquire()
                del self._cache[key]
                self.lock.release()

    def keys(self):
        return set(self._cache.keys()) if self.is_enabled() else set()

    def clean_expired(self):
        if self.is_enabled():
            for key in self.keys():
                self.get(key)


class CacheCleaner(Thread):

    def __init__(self, check_interval: int = 15):
        super(CacheCleaner, self).__init__(daemon=True)
        self.caches = []
        self.check_interval = check_interval

    def register(self, cache: MemoryCache):
        if cache.is_enabled():
            self.caches.append(cache)

    def run(self):
        if self.caches:
            while True:
                for cache in self.caches:
                    cache.clean_expired()

                time.sleep(self.check_interval)


class DefaultMemoryCacheFactory(MemoryCacheFactory):

    def __init__(self, expiration_time: int, cleaner: CacheCleaner = None):
        """
        :param expiration_time: default expiration time for all instantiated caches
        :param cleaner
        """
        super(DefaultMemoryCacheFactory, self).__init__()
        self.expiration_time = expiration_time
        self.cleaner = cleaner

    def new(self, expiration: Optional[int] = None) -> MemoryCache:
        instance = DefaultMemoryCache(expiration if expiration is not None else self.expiration_time)

        if self.cleaner:
            self.cleaner.register(instance)
            
        return instance
