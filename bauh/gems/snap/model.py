from typing import List

from bauh.api.abstract.model import SoftwarePackage, CustomSoftwareAction
from bauh.commons import resource
from bauh.gems.snap import ROOT_DIR

KNOWN_RUNTIME_NAMES = {'snapd', 'snapcraft', 'multipass'}


class SnapApplication(SoftwarePackage):

    def __init__(self, id: str = None, name: str = None, version: str = None, latest_version: str = None,
                 description: str = None, publisher: str = None, rev: str = None, notes: str = None,
                 confinement: str = None, has_apps_field: bool = None, verified_publisher: bool = False, extra_actions: List[CustomSoftwareAction] = None):
        super(SnapApplication, self).__init__(id=id, name=name, version=version,
                                              latest_version=latest_version, description=description)
        self.publisher = publisher
        self.rev = rev
        self.notes = notes
        self.confinement = confinement
        self.has_apps_field = has_apps_field
        self.verified_publisher = verified_publisher
        self.extra_actions = extra_actions

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
        return not self.installed or ((self.has_apps_field is None or self.has_apps_field) and self.name.lower() not in KNOWN_RUNTIME_NAMES)

    def get_disk_cache_path(self):
        return super(SnapApplication, self).get_disk_cache_path() + '/installed/' + self.name

    def is_trustable(self) -> bool:
        return self.verified_publisher

    def get_data_to_cache(self):
        return {
            "icon_url": self.icon_url,
            'confinement': self.confinement,
            'description': self.description,
            'categories': self.categories
        }

    def fill_cached_data(self, data: dict):
        if data:
            for base_attr in ('icon_url', 'description', 'confinement', 'categories'):
                if data.get(base_attr):
                    setattr(self, base_attr, data[base_attr])

    def can_be_run(self) -> bool:
        return self.installed and self.is_application()

    def get_publisher(self):
        return self.publisher

    def get_custom_supported_actions(self) -> List[CustomSoftwareAction]:
        if self.installed:
            return self.extra_actions

    def supports_backup(self) -> bool:
        return True

    def __eq__(self, other):
        if isinstance(other, SnapApplication):
            return self.name == other.name
