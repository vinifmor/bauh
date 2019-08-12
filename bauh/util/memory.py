import time
from threading import Thread
from typing import List

from bauh.util.cache import Cache


class CacheCleaner(Thread):

    def __init__(self, caches: List[Cache], check_interval: int = 15):
        super(CacheCleaner, self).__init__(daemon=True)
        self.caches = [c for c in caches if c.is_enabled()]
        self.check_interval = check_interval

    def run(self):

        if self.caches:
            while True:
                for cache in self.caches:
                    cache.clean_expired()

                time.sleep(self.check_interval)

