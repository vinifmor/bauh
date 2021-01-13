from abc import ABC, abstractmethod
from typing import Type

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.model import SoftwarePackage


class DiskCacheLoader:
    """
    Reads cached data from the disk and fills package instances.
    """

    def map(self, cache: MemoryCache, pkg_type: Type[SoftwarePackage]):
        """
        maps a given cache instance for a given package type
        :param cache:
        :param pkg_type:
        :return:
        """
        pass

    def fill(self, pkg: SoftwarePackage, sync: bool = False):
        """
        fill cached data from the disk of a given package instance
        If a cache mapping was previously done, then data retrieved will be cached to memory as well.
        :param pkg:
        :param sync: if the package data must be filled synchronously
        :return:
        """
        pass


class DiskCacheLoaderFactory(ABC):

    @abstractmethod
    def map(self, pkg_type: Type[SoftwarePackage], cache: MemoryCache):
        """
        Associated a cache instance to instances of a given SoftwarePackage class
        :param pkg_type:
        :param cache:
        :return:
        """
        pass

    @abstractmethod
    def new(self) -> DiskCacheLoader:
        pass
