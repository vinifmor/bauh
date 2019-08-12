from bauh.core import resource
from bauh.core.model import Application, ApplicationData
from bauh.core.snap.constants import SNAP_CACHE_PATH


class SnapApplication(Application):

    def __init__(self, base_data: ApplicationData, publisher: str, rev: str, notes: str, app_type: str, confinement: str = None):
        super(SnapApplication, self).__init__(base_data=base_data)
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

    def can_be_uninstalled(self):
        return self.installed

    def can_be_installed(self):
        return not self.installed

    def can_be_refreshed(self):
        return self.installed

    def get_type(self):
        return 'snap'

    def get_default_icon_path(self):
        return resource.get_path('img/snapcraft.png')

    def is_library(self):
        return self.type in ('core', 'base', 'snapd') or self.base_data.name.startswith('gtk-') or self.base_data.name.startswith('gnome-')

    def get_disk_cache_path(self):
        return '{}/{}'.format(SNAP_CACHE_PATH, self.base_data.name)

    def get_data_to_cache(self):
        return {
            "icon_url": self.base_data.icon_url,
            'confinement': self.confinement,
            'description': self.base_data.description
        }

    def fill_cached_data(self, data: dict):
        if data:
            for base_attr in ('icon_url', 'description'):
                if data.get(base_attr):
                    setattr(self.base_data, base_attr, data[base_attr])

            if data.get('confinement'):
                self.confinement = data['confinement']
