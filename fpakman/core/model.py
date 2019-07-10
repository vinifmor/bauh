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
    def get_type(self):
        pass

    def get_default_logo_path(self):
        return resource.get_path('img/logo.svg')

    @abstractmethod
    def is_library(self):
        pass


class FlatpakApplication(Application):

    def __init__(self, base_data: ApplicationData, branch: str, arch: str, origin: str, runtime: bool, ref: str, commit: str):
        super(FlatpakApplication, self).__init__(base_data=base_data)
        self.ref = ref
        self.branch = branch
        self.arch = arch
        self.origin = origin
        self.runtime = runtime
        self.commit = commit

    def is_incomplete(self):
        return self.base_data.description is None and self.base_data.icon_url

    def has_history(self):
        return True

    def has_info(self):
        return True

    def can_be_downgraded(self):
        return not self.runtime

    def can_be_uninstalled(self):
        return True

    def can_be_installed(self):
        return True

    def get_type(self):
        return 'flatpak'

    def get_default_logo_path(self):
        return resource.get_path('img/flathub.svg')

    def is_library(self):
        return self.runtime
