from packaging.version import Version

from bauh.api.abstract.model import SoftwarePackage, PackageStatus
from bauh.commons import resource
from bauh.gems.flatpak import ROOT_DIR, VERSION_1_2
from bauh.view.util.translation import I18n


class FlatpakApplication(SoftwarePackage):

    def __init__(self, id: str = None, name: str = None, version: str = None, latest_version: str = None,
                 description: str = None, branch: str = None, arch: str = None, origin: str = None,
                 runtime: bool = False, ref: str = None, commit: str = None, installation: str = None,
                 i18n: I18n = None, partial: bool = False, updates_ignored: bool = False,  installed: bool = False,
                 update: bool = False, update_component: bool = False):
        super(FlatpakApplication, self).__init__(id=id, name=name, version=version, latest_version=latest_version,
                                                 description=description, installed=installed, update=update)
        self.ref = ref
        self.branch = branch
        self.arch = arch
        self.origin = origin
        self.runtime = runtime
        self.commit = commit
        self.partial = partial
        self.installation = installation if installation else 'system'
        self.i18n = i18n
        self.base_id = None
        self.base_ref = None
        self.updates_ignored = updates_ignored
        self.update_component = update_component  # if it is a new app/runtime that has come as an update

        if runtime:
            self.categories = ['runtime']

    def is_incomplete(self):
        return self.description is None and self.icon_url

    def has_history(self) -> bool:
        return not self.partial and not self.update_component and self.installed and self.ref

    def has_info(self):
        return bool(self.id)

    def can_be_downgraded(self):
        return not self.partial and not self.update_component and self.installed and self.ref

    def get_type(self):
        return 'flatpak'

    def get_default_icon_path(self):
        return resource.get_path('img/flatpak.svg', ROOT_DIR)

    def get_type_icon_path(self):
        return self.get_default_icon_path()

    def is_application(self):
        return not self.runtime and not self.partial and not self.update_component

    def get_disk_cache_path(self):
        return super(FlatpakApplication, self).get_disk_cache_path() + '/installed/' + self.id

    def get_data_to_cache(self):
        if not self.update_component:
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
        return self.installed and not self.runtime and not self.partial and not self.update_component

    def get_publisher(self):
        return self.origin

    def gen_partial(self, partial_id: str) -> "FlatpakApplication":
        partial = FlatpakApplication()
        partial.partial = True
        partial.id = partial_id
        partial.base_id = self.id
        partial.installation = self.installation
        partial.origin = self.origin
        partial.branch = self.branch
        partial.i18n = self.i18n
        partial.arch = self.arch
        partial.name = self.name
        partial.version = self.version
        partial.latest_version = self.latest_version
        partial.installed = self.installed
        partial.runtime = True

        if self.ref:
            partial.base_ref = self.ref
            partial.ref = '/'.join((partial_id, *self.ref.split('/')[1:]))
            partial.status = PackageStatus.READY
            partial.name += ' ({})'.format(partial_id.split('.')[-1])

        return partial

    def get_name_tooltip(self) -> str:
        if self.installed and self.installation and self.i18n is not None:
            return '{} ({})'.format(self.name, self.i18n['flatpak.info.installation.{}'.format(self.installation.lower().strip())])

        return self.name

    def supports_backup(self) -> bool:
        return True

    def supports_ignored_updates(self) -> bool:
        return self.installed

    def is_update_ignored(self) -> bool:
        return self.updates_ignored

    def get_update_ignore_key(self) -> str:
        return '{}:{}:{}'.format(self.installation, self.id, self.branch)

    def __eq__(self, other):
        if isinstance(other, FlatpakApplication):
            return self.id == other.id and self.installation == other.installation and self.branch == other.branch \
                   and self.runtime == other.runtime and self.partial == other.partial and \
                   self.update_component == other.update_component

    def __hash__(self) -> int:
        hash_sum = 0
        for attr in ('id', 'installation', 'branch', 'runtime', 'partial', 'update_component'):
            hash_sum += hash(getattr(self, attr))

        return hash_sum

    def get_disk_icon_path(self) -> str:
        if not self.runtime:
            return super(FlatpakApplication, self).get_disk_icon_path()

    def get_update_id(self, flatpak_version: Version) -> str:
        if flatpak_version >= VERSION_1_2:
            return f'{self.id}/{self.branch}/{self.installation}/{self.origin}'
        else:
            return f'{self.installation}/{self.ref}'

    def can_be_installed(self) -> bool:
        return not self.update_component and not self.installed

    def can_be_updated(self) -> bool:
        return self.update_component or super(FlatpakApplication, self).can_be_updated()

    def can_be_uninstalled(self) -> bool:
        return not self.update_component and super(FlatpakApplication, self).can_be_uninstalled()

    def update_ref(self):
        if self.id and self.arch and self.branch:
            self.ref = f'{self.id}/{self.arch}/{self.branch}'

    def __repr__(self) -> str:
        return f'Flatpak (id={self.id}, branch={self.branch}, origin={self.origin}, installation={self.installation},' \
               f' partial={self.partial}, update_component={self.update_component})'

    def __str__(self):
        return self.__repr__()
