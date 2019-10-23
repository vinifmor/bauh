from bauh.api.abstract.model import SoftwarePackage

from bauh.commons import resource
from bauh.gems.flatpak import ROOT_DIR


class FlatpakApplication(SoftwarePackage):

    def __init__(self, id: str = None, name: str = None, version: str = None, latest_version: str = None, description: str = None,
                 branch: str = None, arch: str = None, origin: str = None, runtime: bool = False, ref: str = None, commit: str = None):
        super(FlatpakApplication, self).__init__(id=id, name=name, version=version,
                                                 latest_version=latest_version, description=description)
        self.ref = ref
        self.branch = branch
        self.arch = arch
        self.origin = origin
        self.runtime = runtime
        self.commit = commit

        if runtime:
            self.categories = ['runtime']

    def is_incomplete(self):
        return self.description is None and self.icon_url

    def has_history(self):
        return self.installed and self.ref

    def has_info(self):
        return bool(self.id)

    def can_be_downgraded(self):
        return self.installed and self.ref

    def get_type(self):
        return 'flatpak'

    def get_default_icon_path(self):
        return resource.get_path('img/flathub.svg', ROOT_DIR)

    def get_type_icon_path(self):
        return self.get_default_icon_path()

    def is_application(self):
        return not self.runtime

    def get_disk_cache_path(self):
        return super(FlatpakApplication, self).get_disk_cache_path() + '/installed/' + self.id

    def get_data_to_cache(self):
        return {
            'description': self.description,
            'icon_url': self.icon_url,
            'latest_version': self.latest_version,
            'version': self.version,
            'name': self.name,
            'categories': self.categories
        }

    def fill_cached_data(self, data: dict):
        for attr in self.get_data_to_cache().keys():
            if data.get(attr) and not getattr(self, attr):
                setattr(self, attr, data[attr])

    def can_be_run(self) -> bool:
        return self.installed and not self.runtime

    def get_publisher(self):
        return self.origin
