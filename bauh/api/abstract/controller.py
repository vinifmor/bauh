import json
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Set, Type

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageUpdate, PackageHistory, PackageSuggestion, PackageAction


class SearchResult:

    def __init__(self, installed: List[SoftwarePackage], new: List[SoftwarePackage], total: int):
        """
        :param installed: already installed packages
        :param new: new packages found
        :param total: total number of applications actually found
        """
        self.installed = installed
        self.new = new
        self.total = total


class SoftwareManager(ABC):

    """
    Base controller class that will be called by the graphical interface to execute operations.
    """

    def __init__(self, context: ApplicationContext):
        """
        :param context:
        """
        self.context = context

    @abstractmethod
    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int) -> SearchResult:
        """
        :param words: the words typed by the user
        :param disk_loader: a running disk loader thread that loads package data from the disk asynchronously
        :param limit: the max number of packages to be retrieved. <= 1 should retrieve everything
        :return:
        """
        pass

    @abstractmethod
    def read_installed(self, disk_loader: DiskCacheLoader, limit: int, only_apps: bool, pkg_types: Set[Type[SoftwarePackage]], internet_available: bool) -> SearchResult:
        """
        :param disk_loader:  a running disk loader thread that loads application data from the disk asynchronously
        :param limit: the max number of packages to be retrieved. <= 1 should retrieve everything
        :param only_apps: if only application packages should be retrieved
        :param pkg_types: use 'None' to bring any or specify some
        :param internet_available: if there is internet connection
        :return:
        """
        pass

    @abstractmethod
    def downgrade(self, pkg: SoftwarePackage, root_password: str, handler: ProcessWatcher) -> bool:
        """
        downgrades a package version
        :param pkg:
        :param root_password: the root user password (if required)
        :param handler: a subprocess handler
        :return:
        """
        pass

    def clean_cache_for(self, pkg: SoftwarePackage):
        """
        Cleans cached package cached data. This default implementation only cleans the cached data from the heard disk
        :param pkg:
        :return:
        """
        if pkg.supports_disk_cache() and os.path.exists(pkg.get_disk_cache_path()):
            shutil.rmtree(pkg.get_disk_cache_path())

    @abstractmethod
    def update(self, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        """
        :param pkg:
        :param root_password: the root user password (if required)
        :param watcher:
        :return:
        """
        pass

    @abstractmethod
    def uninstall(self, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        """
        :param pkg:
        :param root_password: the root user password (if required)
        :param watcher:
        :return: if the uninstall succeeded
        """
        pass

    @abstractmethod
    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        """
        :return: the managed package class type
        """
        pass

    @abstractmethod
    def get_info(self, pkg: SoftwarePackage) -> dict:
        """
        retrieve the package information
        :param pkg:
        :return: a dictionary with the attributes to be shown
        """
        pass

    @abstractmethod
    def get_history(self, pkg: SoftwarePackage) -> PackageHistory:
        """
        :param pkg:
        :return:
        """
        pass

    @abstractmethod
    def install(self, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        """
        :param pkg:
        :param root_password: the root user password (if required)
        :param watcher:
        :return: if the installation succeeded
        """
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """
        :return: if the instance is enabled
        """
        pass

    @abstractmethod
    def set_enabled(self, enabled: bool):
        """
        :param enabled:
        :return:
        """
        pass

    @abstractmethod
    def can_work(self) -> bool:
        """
        :return: if the instance can work based on what is installed in the user's machine.
        """

    def cache_to_disk(self, pkg: SoftwarePackage, icon_bytes: bytes, only_icon: bool):
        """
        Saves the package data to the hard disk.
        :param pkg:
        :param icon_bytes:
        :param only_icon: if only the icon should be saved
        :return:
        """
        if self.context.disk_cache and pkg.supports_disk_cache():

            if not only_icon:
                Path(pkg.get_disk_cache_path()).mkdir(parents=True, exist_ok=True)
                data = pkg.get_data_to_cache()

                if data:
                    with open(pkg.get_disk_data_path(), 'w+') as f:
                        f.write(json.dumps(data))

            if icon_bytes:
                Path(pkg.get_disk_cache_path()).mkdir(parents=True, exist_ok=True)

                with open(pkg.get_disk_icon_path(), 'wb+') as f:
                    f.write(icon_bytes)

    @abstractmethod
    def requires_root(self, action: str, pkg: SoftwarePackage):
        """
        if a given action requires root privileges to be executed. Current actions are: 'install', 'uninstall', 'downgrade', 'search', 'refresh'
        :param action:
        :param pkg:
        :return:
        """
        pass

    @abstractmethod
    def prepare(self):
        """
        It prepares the manager to start working. It will be called by GUI. Do not call it within.
        :return:
        """
        pass

    @abstractmethod
    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        """
        :param internet_available
        :return: available package updates
        """
        pass

    @abstractmethod
    def list_warnings(self) -> List[str]:
        """
        :return: a list of warnings to be shown to the user
        """
        pass

    @abstractmethod
    def list_suggestions(self, limit: int) -> List[PackageSuggestion]:
        """
        :param limit: max suggestions to be returned. If limit < 0, it should not be considered
        :return: a list of package suggestions
        """
        pass

    def execute_custom_action(self, action: PackageAction, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        """
        At the moment the GUI implements this action. No need to implement it yourself.
        :param action:
        :param pkg:
        :param root_password:
        :param watcher:
        :return: if the action resulted in success
        """
        pass

    @abstractmethod
    def is_default_enabled(self) -> bool:
        """
        :return: if the instance is enabled by default when there is no user settings defining which gems are enabled.
        """

    @abstractmethod
    def launch(self, pkg: SoftwarePackage):
        pass
