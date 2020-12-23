from abc import ABC, abstractmethod
from typing import Set, Optional


class MemoryCache(ABC):
    """
    Represents a memory cache.
    """

    @abstractmethod
    def is_enabled(self):
        pass

    @abstractmethod
    def add(self, key: str, val: object):
        pass

    @abstractmethod
    def add_non_existing(self, key: str, val: object):
        pass

    @abstractmethod
    def get(self, key: str):
        pass

    @abstractmethod
    def delete(self, key):
        pass

    @abstractmethod
    def keys(self) -> Set[str]:
        pass

    @abstractmethod
    def clean_expired(self):
        pass


class MemoryCacheFactory(ABC):
    """
    Instantiate new memory cache instances.
    """

    @abstractmethod
    def new(self, expiration: Optional[int]) -> MemoryCache:
        """
        :param expiration: expiration time for the cache keys in seconds. Use -1 to disable this feature.
        :return:
        """
        pass
