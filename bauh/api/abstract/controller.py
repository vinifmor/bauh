import json
import os
import shutil
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import List, Set, Type, Tuple, Optional

import yaml

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import SoftwarePackage, PackageUpdate, PackageHistory, PackageSuggestion, \
    CustomSoftwareAction
from bauh.api.abstract.view import ViewComponent


class SearchResult:

    def __init__(self, installed: Optional[List[SoftwarePackage]], new: Optional[List[SoftwarePackage]], total: int):
        """
        :param installed: already installed packages
        :param new: new packages found
        :param total: total number of applications actually found
        """
        self.installed = installed
        self.new = new
        self.total = total

    def update_total(self):
        total = 0

        if self.installed:
            total += len(self.installed)

        if self.new:
            total += len(self.new)

        self.total = total

    @classmethod
    def empty(cls):
        return cls(installed=[], new=[], total=0)


class UpgradeRequirement:

    def __init__(self, pkg: SoftwarePackage, reason: str = None, required_size: int = None, extra_size: int = None, sorting_priority: int = 0):
        """

        :param pkg:
        :param reason:
        :param required_size: size in BYTES required to upgrade the package
        :param extra_size: the extra size IN BYTES the upgrade will allocate in relation to the already allocated
        :param sorting_priority: an int representing the sorting priority (higher numbers = higher priority)
        """
        self.pkg = pkg
        self.reason = reason
        self.required_size = required_size
        self.extra_size = extra_size
        self.sorting_priority = sorting_priority

    @staticmethod
    def sort_by_priority(req: "UpgradeRequirement") -> Tuple[int, str]:
        return -req.sorting_priority, req.pkg.name


class UpgradeRequirements:

    def __init__(self, to_install: Optional[List[UpgradeRequirement]], to_remove: Optional[List[UpgradeRequirement]],
                 to_upgrade: List[UpgradeRequirement], cannot_upgrade: Optional[List[UpgradeRequirement]]):
        """
        :param to_install: additional packages that must be installed with the upgrade
        :param to_remove: non upgrading packages that should be removed due to conflicts with upgrading packages
        :param to_upgrade: the final packages to update
        :param cannot_upgrade: packages which conflict with each other
        """
        self.to_install = to_install
        self.to_remove = to_remove  # when an upgrading package conflicts with a not upgrading package ( check all the non-upgrading packages deps an add here [including those selected to upgrade as well]
        self.to_upgrade = to_upgrade
        self.cannot_upgrade = cannot_upgrade
        self.context = {}  # caches relevant data to actually perform the upgrade


class TransactionResult:
    """
    The result of a given operation
    """

    def __init__(self, success: bool, installed: Optional[List[SoftwarePackage]], removed: Optional[List[SoftwarePackage]]):
        self.success = success
        self.installed = installed
        self.removed = removed

    @staticmethod
    def fail() -> "TransactionResult":
        return TransactionResult(success=False, installed=None, removed=None)


class SoftwareAction(Enum):
    PREPARE = 0
    SEARCH = 1
    INSTALL = 2
    UNINSTALL = 3
    UPGRADE = 4
    DOWNGRADE = 5


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
    def search(self, words: str, disk_loader: Optional[DiskCacheLoader], limit: int, is_url: bool) -> SearchResult:
        """
        :param words: the words typed by the user
        :param disk_loader: a running disk loader thread that loads package data from the disk asynchronously
        :param limit: the max number of packages to be retrieved. <= 1 should retrieve everything
        :param is_url: if "words" is a URL
        :return:
        """
        pass

    @abstractmethod
    def read_installed(self, disk_loader: Optional[DiskCacheLoader], limit: int, only_apps: bool, pkg_types: Optional[Set[Type[SoftwarePackage]]], internet_available: bool) -> SearchResult:
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

    def get_upgrade_requirements(self, pkgs: List[SoftwarePackage], root_password: str, watcher: ProcessWatcher) -> UpgradeRequirements:
        """
        return additional required software that needs to be installed / removed / updated before updating a list of packages
        :param pkgs:
        :param watcher
        :return:
        """
        return UpgradeRequirements(None, None, [UpgradeRequirement(p) for p in pkgs], None)

    @abstractmethod
    def upgrade(self, requirements: UpgradeRequirements, root_password: str, watcher: ProcessWatcher) -> bool:
        """
        :param requirements:
        :param root_password: the root user password (if required)
        :param watcher:
        :return:
        """
        pass

    @abstractmethod
    def uninstall(self, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher, disk_loader: Optional[DiskCacheLoader]) -> TransactionResult:
        """
        :param pkg:
        :param root_password: the root user password (if required)
        :param watcher:
        :param disk_loader:
        :return:
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
    def install(self, pkg: SoftwarePackage, root_password: str, disk_loader: Optional[DiskCacheLoader], watcher: ProcessWatcher) -> TransactionResult:
        """
        :param pkg:
        :param root_password: the root user password (if required)
        :param disk_loader
        :param watcher:
        :return:
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

    def cache_to_disk(self, pkg: SoftwarePackage, icon_bytes: Optional[bytes], only_icon: bool):
        """
        Saves the package data to the hard disk.
        :param pkg:
        :param icon_bytes:
        :param only_icon: if only the icon should be saved
        :return:
        """
        if pkg.supports_disk_cache():
            self.serialize_to_disk(pkg, icon_bytes, only_icon)

    def serialize_to_disk(self, pkg: SoftwarePackage, icon_bytes: Optional[bytes], only_icon: bool):
        """
        Sames as above, but does not check if disk cache is enabled or supported by the package instance
        :param pkg:
        :param icon_bytes:
        :param only_icon:
        :return:
        """
        if not only_icon:
            Path(pkg.get_disk_cache_path()).mkdir(parents=True, exist_ok=True)
            data = pkg.get_data_to_cache()

            if data:
                disk_path = pkg.get_disk_data_path()
                ext = disk_path.split('.')[-1]

                if ext == 'json':
                    with open(disk_path, 'w+') as f:
                        f.write(json.dumps(data))
                elif ext in ('yml', 'yaml'):
                    with open(disk_path, 'w+') as f:
                        f.write(yaml.dump(data))

        if icon_bytes:
            Path(pkg.get_disk_cache_path()).mkdir(parents=True, exist_ok=True)

            with open(pkg.get_disk_icon_path(), 'wb+') as f:
                f.write(icon_bytes)

    @abstractmethod
    def requires_root(self, action: SoftwareAction, pkg: Optional[SoftwarePackage]) -> bool:
        """
        if a given action requires root privileges to be executed. 'install', 'uninstall', 'downgrade', 'search', 'prepare'
        :param action:
        :param pkg:
        :return:
        """
        pass

    @abstractmethod
    def prepare(self, task_manager: Optional[TaskManager], root_password: Optional[str], internet_available: Optional[bool]):
        """
        It prepares the manager to start working. It will be called by GUI. Do not call it within.
        :param task_manager: a task manager instance used to register ongoing tasks during prepare
        :param root_password
        :param internet_available: if there is internet connection available
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
    def list_warnings(self, internet_available: bool) -> List[str]:
        """
        :param internet_available
        :return: a list of warnings to be shown to the user
        """
        pass

    @abstractmethod
    def list_suggestions(self, limit: int, filter_installed: bool) -> List[PackageSuggestion]:
        """
        :param limit: max suggestions to be returned. If limit < 0, it should not be considered
        :param filter_installed: if the installed suggestions should not be retrieved
        :return: a list of package suggestions
        """
        pass

    def execute_custom_action(self, action: CustomSoftwareAction, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
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

    @abstractmethod
    def get_screenshots(self, pkg: SoftwarePackage) -> List[str]:
        """
        :return: screenshot urls for the given package
        """
        pass

    def clear_data(self, logs: bool = True):
        """
        Removes all data created by the SoftwareManager instance
        """
        pass

    def get_settings(self, screen_width: int, screen_height: int) -> ViewComponent:
        """
        :param screen_width
        :param screen_height
        :return: a form abstraction with all available settings
        """
        pass

    def save_settings(self, component: ViewComponent) -> Tuple[bool, Optional[List[str]]]:
        """
        :return: a tuple with a bool informing if the settings were saved and a list of error messages
        """
        pass

    def get_custom_actions(self) -> List[CustomSoftwareAction]:
        """
        :return: custom actions
        """
        pass

    def fill_sizes(self, pkgs: List[SoftwarePackage]):
        pass

    def ignore_update(self, pkg: SoftwarePackage):
        pass

    def revert_ignored_update(self, pkg: SoftwarePackage):
        pass
