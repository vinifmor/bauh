from typing import Optional, Set, Iterable, Tuple

from bauh.api.abstract.model import SoftwarePackage, CustomSoftwareAction
from bauh.commons import resource
from bauh.gems.snap import ROOT_DIR


class SnapApplication(SoftwarePackage):

    __actions: Optional[Tuple[CustomSoftwareAction, CustomSoftwareAction]] = None

    @classmethod
    def actions(cls) -> Tuple[CustomSoftwareAction, CustomSoftwareAction]:
        if cls.__actions is None:
            cls.__actions = (
                CustomSoftwareAction(i18n_status_key='snap.action.refresh.status',
                                     i18n_label_key='snap.action.refresh.label',
                                     i18n_description_key='snap.action.refresh.desc',
                                     icon_path=resource.get_path('img/refresh.svg', ROOT_DIR),
                                     manager_method='refresh',
                                     requires_root=True,
                                     i18n_confirm_key='snap.action.refresh.confirm'),
                CustomSoftwareAction(i18n_status_key='snap.action.channel.status',
                                     i18n_label_key='snap.action.channel.label',
                                     i18n_confirm_key='snap.action.channel.confirm',
                                     i18n_description_key='snap.action.channel.desc',
                                     icon_path=resource.get_path('img/refresh.svg', ROOT_DIR),
                                     manager_method='change_channel',
                                     requires_root=True,
                                     requires_confirmation=False)
            )

        return cls.__actions

    def __init__(self, id: str = None, name: str = None, version: str = None, latest_version: str = None,
                 description: str = None, publisher: str = None, rev: str = None, notes: str = None,
                 confinement: str = None, verified_publisher: bool = False,
                 screenshots: Optional[Set[str]] = None,
                 license: Optional[str] = None,
                 installed: bool = False,
                 icon_url: Optional[str] = None,
                 download_size: Optional[int] = None,
                 developer: Optional[str] = None,
                 contact: Optional[str] = None,
                 tracking: Optional[str] = None,
                 app_type: Optional[str] = None,
                 channel: Optional[str] = None,
                 app: bool = False,
                 installed_size: Optional[int] = None):
        super(SnapApplication, self).__init__(id=id, name=name, version=version,
                                              latest_version=latest_version, description=description,
                                              license=license, installed=installed, icon_url=icon_url)
        self.publisher = publisher
        self.rev = rev
        self.notes = notes
        self.confinement = confinement
        self.verified_publisher = verified_publisher
        self.screenshots = screenshots
        self.download_size = download_size
        self.developer = developer
        self.contact = contact
        self.tracking = tracking
        self.type = app_type
        self.channel = channel
        self.app = app
        self.installed_size = installed_size

    def supports_disk_cache(self):
        return self.installed

    def has_history(self):
        return False

    def has_info(self):
        return True

    def can_be_downgraded(self):
        return self.installed

    def get_type(self):
        return 'snap'

    def get_default_icon_path(self):
        return resource.get_path('img/snap.svg', ROOT_DIR)

    def get_type_icon_path(self):
        return self.get_default_icon_path()

    def is_application(self) -> bool:
        if self.installed:
            return self.app
        else:
            return self.type == 'app'

    def get_disk_cache_path(self):
        return f'{super(SnapApplication, self).get_disk_cache_path()}/installed/{self.name}'

    def is_trustable(self) -> bool:
        return self.verified_publisher

    def get_data_to_cache(self):
        return {
            'categories': self.categories
        }

    def fill_cached_data(self, data: dict):
        if data:
            for base_attr in self.get_data_to_cache().keys():
                if data.get(base_attr):
                    setattr(self, base_attr, data[base_attr])

    def can_be_run(self) -> bool:
        return bool(self.installed and self.is_application())

    def get_publisher(self):
        return self.publisher

    def get_custom_actions(self) -> Optional[Iterable[CustomSoftwareAction]]:
        if self.installed:
            return self.actions()

    def supports_backup(self) -> bool:
        return True

    def has_screenshots(self) -> bool:
        return not self.installed and self.screenshots

    def __eq__(self, other):
        if isinstance(other, SnapApplication):
            return self.name == other.name
