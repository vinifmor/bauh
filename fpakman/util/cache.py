from datetime import datetime, timedelta
from threading import Lock


class Cache:

    def __init__(self, expiration_time: int):
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
            self._cache[key] = {'val': val, 'expires_at': datetime.utcnow() + timedelta(seconds=self.expiration_time) if self.expiration_time > 0 else None}

    def add_non_existing(self, key: str, val: object):

        if key and self. is_enabled():
            self.lock.acquire()
            cur_val = self.get(key)

            if cur_val is None:
                self._add(key, val)

            self.lock.release()

    def get(self, key: str):
        if key and self.is_enabled():
            val = self._cache.get(key)

            if val:
                expiration = val.get('expires_at')

                if expiration and expiration <= datetime.utcnow():
                    self.lock.acquire()
                    del self._cache[key]
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
