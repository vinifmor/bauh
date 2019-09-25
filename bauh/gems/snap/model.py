from typing import List

from bauh.api.abstract.model import SoftwarePackage, PackageAction
from bauh.commons import resource

from bauh.gems.snap import ROOT_DIR

EXTRA_INSTALLED_ACTIONS = [
    PackageAction(i18n_status_key='snap.action.refresh.status',
                  i18_label_key='snap.action.refresh.label',
                  icon_path=resource.get_path('img/refresh.svg', ROOT_DIR),
                  manager_method='refresh',
                  requires_root=True)
]

KNOWN_APP_NAMES = {'gnome-calculator', 'gnome-system-monitor', 'gnome-logs'}
KNOWN_RUNTIME_NAMES = {'snapd', 'core', 'core18', 'snapcraft', 'multipass'}
KNOWN_RUNTIME_PREFIXES = {'gtk-', 'gnome-', 'kde-', 'gtk2-'}
KNOWN_RUNTIME_TYPES = {'base', 'core', 'os'}


class SnapApplication(SoftwarePackage):

    def __init__(self, id: str = None, name: str = None, version: str = None, latest_version: str = None,
                 description: str = None, publisher: str = None, rev: str = None, notes: str = None,
                 app_type: str = None, confinement: str = None):
        super(SnapApplication, self).__init__(id=id, name=name, version=version,
                                              latest_version=latest_version, description=description)
        self.publisher = publisher
        self.rev = rev
        self.notes = notes
        self.type = app_type
        self.confinement = confinement

    def has_history(self):
        return False

    def has_info(self):
        return True

    def can_be_downgraded(self):
        return self.installed

    def get_type(self):
        return 'snap'

    def get_default_icon_path(self):
        return resource.get_path('img/snap.png', ROOT_DIR)

    def get_type_icon_path(self):
        return self.get_default_icon_path()

    def is_application(self):
        return not self.type and (self.name in KNOWN_APP_NAMES) or (self.name not in KNOWN_RUNTIME_NAMES and self.type not in KNOWN_RUNTIME_TYPES and not self._name_starts_with(KNOWN_RUNTIME_PREFIXES))

    def _name_starts_with(self, words: set):
        for word in words:
            if self.name.startswith(word):
                return True

        return False

    def get_disk_cache_path(self):
        return super(SnapApplication, self).get_disk_cache_path() + '/installed/' + self.name

    def get_data_to_cache(self):
        return {
            "icon_url": self.icon_url,
            'confinement': self.confinement,
            'description': self.description
        }

    def fill_cached_data(self, data: dict):
        if data:
            for base_attr in ('icon_url', 'description'):
                if data.get(base_attr):
                    setattr(self, base_attr, data[base_attr])

            if data.get('confinement'):
                self.confinement = data['confinement']

    def can_be_run(self) -> bool:
        return self.installed and self.is_application()

    def get_publisher(self):
        return self.publisher

    def get_custom_supported_actions(self) -> List[PackageAction]:
        if self.installed:
            return EXTRA_INSTALLED_ACTIONS
