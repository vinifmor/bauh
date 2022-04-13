from typing import Optional, Tuple, Collection, Iterable, Generator

from bauh.api.abstract.model import SoftwarePackage, CustomSoftwareAction
from bauh.commons import resource
from bauh.gems.debian import DEBIAN_ICON_PATH, ROOT_DIR


class DebianApplication:
    """
    For packages that represent applications
    """

    def __init__(self, name: str, exe_path: str, icon_path: str, categories: Optional[Tuple] = None):
        self.name = name
        self.exe_path = exe_path
        self.icon_path = icon_path
        self.categories = categories

    def __eq__(self, other):
        if isinstance(other, DebianApplication):
            return self.__dict__ == other.__dict__

        return False

    def __hash__(self) -> int:
        hash_sum = 0

        for k, v in self.__dict__.items():
            hash_sum += hash(v)

        return hash_sum

    def __repr__(self):
        return f"{self.__class__.__name__} ({', '.join((f'{k}={v}' for k, v in self.__dict__.items()))})"

    def to_index(self) -> dict:
        return {self.name: {f: v for f, v in self.__dict__.items() if f != 'name'}}


class DebianPackage(SoftwarePackage):

    __actions_purge: Optional[Tuple[CustomSoftwareAction, ...]] = None

    @classmethod
    def actions_purge(cls) -> Tuple[CustomSoftwareAction, ...]:
        if cls.__actions_purge is None:
            cls.__actions_purge = (CustomSoftwareAction(i18n_label_key='debian.action.purge',
                                                        i18n_status_key='debian.action.purge.status',
                                                        i18n_description_key='debian.action.purge.desc',
                                                        icon_path=resource.get_path('img/clean.svg', ROOT_DIR),
                                                        manager_method='purge',
                                                        requires_root=True,
                                                        requires_confirmation=False),)

        return cls.__actions_purge

    def __init__(self, name: str = None, version: Optional[str] = None, latest_version: Optional[str] = None,
                 description: Optional[str] = None, maintainer: Optional[str] = None, installed: bool = False,
                 update: bool = False, app: Optional[DebianApplication] = None, compressed_size: Optional[int] = None,
                 uncompressed_size: Optional[int] = None, categories: Tuple[str] = None,
                 updates_ignored: Optional[bool] = None, transaction_size: Optional[float] = None,
                 global_purge: bool = False):
        super(DebianPackage, self).__init__(id=name, name=name, version=version, installed=installed,
                                            description=description, update=update,
                                            latest_version=latest_version if latest_version is not None else version)
        self.maintainer = maintainer
        self.compressed_size = compressed_size
        self.uncompressed_size = uncompressed_size
        self.categories = categories
        self.app = app
        self.bind_app(app)
        self.updates_ignored = updates_ignored
        self.transaction_size = transaction_size  # size in bytes related to a transaction (install, upgrade, remove)
        self.global_purge = global_purge  # if global purge is already enabled

    def bind_app(self, app: Optional[DebianApplication]):
        self.app = app

        if app and app.categories:
            self.categories = app.categories

    def has_history(self) -> bool:
        return False

    def has_screenshots(self) -> bool:
        return False

    def has_info(self) -> bool:
        return True

    def can_be_downgraded(self) -> bool:
        return False

    def get_type(self):
        return 'debian'

    def get_default_icon_path(self) -> str:
        return self.get_type_icon_path()

    def get_type_icon_path(self) -> str:
        return DEBIAN_ICON_PATH

    def is_application(self):
        return bool(self.app)

    def get_data_to_cache(self) -> dict:
        pass

    def fill_cached_data(self, data: dict):
        pass

    def can_be_run(self) -> bool:
        return bool(self.app)

    def get_publisher(self) -> str:
        return self.maintainer

    def supports_backup(self) -> bool:
        return True

    def get_disk_icon_path(self) -> Optional[str]:
        if self.app:
            return self.app.icon_path

    def get_custom_actions(self) -> Optional[Iterable[CustomSoftwareAction]]:
        if self.installed and not self.global_purge:
            return self.actions_purge()

    def is_update_ignored(self) -> bool:
        return bool(self.updates_ignored)

    def supports_ignored_updates(self) -> bool:
        return True

    def __eq__(self, other):
        if isinstance(other, DebianPackage):
            return self.name == other.name

        return False

    def __hash__(self):
        return hash(self.name)

    def __repr__(self) -> str:
        attrs = ', '.join((f'{p}={v}' for p, v in sorted(self.__dict__.items())))
        return f"{self.__class__.__name__} ({attrs})"


class DebianTransaction:

    def __init__(self, to_install: Optional[Collection[DebianPackage]],
                 to_remove: Optional[Collection[DebianPackage]],
                 to_upgrade: Optional[Collection[DebianPackage]]):

        self.to_install = to_install
        self.to_remove = to_remove
        self.to_upgrade = to_upgrade

    @property
    def all_packages(self) -> Generator[DebianPackage, None, None]:
        for pkgs in (self.to_install, self.to_remove, self.to_upgrade):
            if pkgs:
                yield from pkgs

    def __eq__(self, other) -> bool:
        return self.__dict__ == other.__dict__ if isinstance(other, DebianTransaction) else False

    def __hash__(self) -> int:
        return sum((hash(v)for v in self.__dict__.values()))
