from fpakman.core import resource
from fpakman.core.flatpak.constants import FLATPAK_CACHE_PATH
from fpakman.core.model import Application, ApplicationData


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
        return self.installed

    def has_info(self):
        return self.installed

    def can_be_downgraded(self):
        return self.installed

    def can_be_uninstalled(self):
        return self.installed

    def can_be_installed(self):
        return not self.installed

    def get_type(self):
        return 'flatpak'

    def can_be_refreshed(self):
        return False

    def get_default_icon_path(self):
        return resource.get_path('img/flathub.svg')

    def is_library(self):
        return self.runtime

    def get_disk_cache_path(self):
        return '{}/{}'.format(FLATPAK_CACHE_PATH, self.base_data.id)

    def get_data_to_cache(self):
        return {
            'description': self.base_data.description,
            'icon_url': self.base_data.icon_url,
            'latest_version': self.base_data.latest_version,
            'version': self.base_data.version,
            'name': self.base_data.name
        }

    def fill_cached_data(self, data: dict):
        for attr in self.get_data_to_cache().keys():
            if not getattr(self.base_data, attr):
                setattr(self.base_data, attr, data[attr])
