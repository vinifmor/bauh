from abc import ABC, abstractmethod
from enum import Enum

from fpakman.core import resource


class ApplicationStatus(Enum):
    READY = 1
    LOADING_DATA = 2


class ApplicationData:

    def __init__(self, id: str, version: str, name: str = None, description: str = None, latest_version: str = None, icon_url: str = None):
        self.id = id
        self.name = name
        self.version = version
        self.description = description
        self.latest_version = latest_version
        self.icon_url = icon_url


class Application(ABC):

    def __init__(self, base_data: ApplicationData, status: ApplicationStatus = ApplicationStatus.READY, installed: bool = False, update: bool = False):
        self.base_data = base_data
        self.status = status
        self.installed = installed
        self.update = update

    @abstractmethod
    def has_history(self):
        pass

    @abstractmethod
    def has_info(self):
        pass

    @abstractmethod
    def can_be_downgraded(self):
        pass

    @abstractmethod
    def can_be_uninstalled(self):
        pass

    @abstractmethod
    def can_be_installed(self):
        pass

    @abstractmethod
    def can_be_refreshed(self):
        return self.installed

    @abstractmethod
    def get_type(self):
        pass

    def get_default_icon_path(self):
        return resource.get_path('img/logo.svg')

    @abstractmethod
    def is_library(self):
        pass

    def supports_disk_cache(self):
        return self.installed and not self.is_library()

    @abstractmethod
    def get_disk_cache_path(self):
        pass

    def get_disk_icon_path(self):
        return '{}/icon.png'.format(self.get_disk_cache_path())

    def get_disk_data_path(self):
        return '{}/data.json'.format(self.get_disk_cache_path())

    @abstractmethod
    def get_data_to_cache(self):
        pass

    @abstractmethod
    def fill_cached_data(self, data: dict):
        pass

    def __str__(self):
        return '{} (id={}, name={})'.format(self.__class__.__name__, self.base_data.id, self.base_data.name)


class ApplicationUpdate:

    def __init__(self, app_id: str, version: str, app_type: str):
        self.id = app_id
        self.version = version
        self.type = app_type

    def __str__(self):
        return '{} (id={}, type={}, new_version={})'.format(self.__class__.__name__, self.id, self.type, self.type)
