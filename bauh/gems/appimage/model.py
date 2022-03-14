import re
from io import StringIO
from re import Pattern
from typing import Optional, Iterable, Tuple

from bauh.api.abstract.model import SoftwarePackage, CustomSoftwareAction
from bauh.commons import resource
from bauh.gems.appimage import ROOT_DIR, INSTALLATION_DIR
from bauh.view.util.translation import I18n


class AppImage(SoftwarePackage):

    __actions_local_installation: Optional[Tuple[CustomSoftwareAction, ...]] = None
    __cached_attrs: Optional[Tuple[str, ...]] = None
    __re_many_spaces: Optional[Pattern] = None

    @classmethod
    def actions_local_installation(cls) -> Tuple[CustomSoftwareAction, ...]:
        if cls.__actions_local_installation is None:
            cls.__actions_local_installation = (CustomSoftwareAction(i18n_label_key='appimage.custom_action.manual_update',
                                                                     i18n_status_key='appimage.custom_action.manual_update.status',
                                                                     i18n_description_key='appimage.custom_action.manual_update.desc',
                                                                     manager_method='update_file',
                                                                     requires_root=False,
                                                                     icon_path=resource.get_path('img/refresh.svg', ROOT_DIR),
                                                                     requires_confirmation=False),)

        return cls.__actions_local_installation

    @classmethod
    def cached_attrs(cls) -> Tuple[str, ...]:
        if cls.__cached_attrs is None:
            cls.__cached_attrs = ('name', 'description', 'version', 'url_download', 'author', 'license', 'source',
                                  'icon_path', 'github', 'categories', 'imported', 'install_dir', 'symlink')

        return cls.__cached_attrs

    @classmethod
    def re_many_spaces(cls) -> Pattern:
        if cls.__re_many_spaces is None:
            cls.__re_many_spaces = re.compile(r'\s+')

        return cls.__re_many_spaces

    def __init__(self, name: str = None, description: str = None, github: str = None, source: str = None, version: str = None,
                 url_download: str = None, url_icon: str = None, url_screenshot: str = None, license: str = None, author: str = None,
                 categories=None, icon_path: str = None, installed: bool = False,
                 url_download_latest_version: str = None, local_file_path: str = None, imported: bool = False,
                 i18n: I18n = None, install_dir: str = None, updates_ignored: bool = False,
                 symlink: str = None, **kwargs):
        super(AppImage, self).__init__(id=name, name=name, version=version, latest_version=version,
                                       icon_url=url_icon, license=license, description=description,
                                       installed=installed)
        self.source = source
        self.github = github
        self.categories = (categories.split(',') if isinstance(categories, str) else categories) if categories else None
        self.url_download = url_download
        self.icon_path = icon_path
        self.url_screenshot = url_screenshot
        self.author = author
        self.url_download_latest_version = url_download_latest_version
        self.local_file_path = local_file_path
        self.imported = imported
        self.i18n = i18n
        self.install_dir = install_dir
        self.updates_ignored = updates_ignored
        self.symlink = symlink

    def __repr__(self):
        return "{} (name={}, github={})".format(self.__class__.__name__, self.name, self.github)

    def can_be_installed(self):
        return not self.installed and self.url_download

    def has_history(self):
        return self.installed and not self.imported

    def has_info(self):
        return self.installed if self.imported else True

    def can_be_downgraded(self):
        return self.installed and not self.imported

    def get_type(self):
        return 'AppImage'

    def get_default_icon_path(self):
        return self.get_type_icon_path()

    def get_type_icon_path(self):
        return resource.get_path('img/appimage.svg', ROOT_DIR)

    def is_application(self):
        return True

    def get_data_to_cache(self) -> dict:
        data = {}

        for a in self.cached_attrs():
            val = getattr(self, a)
            if val:
                data[a] = val

        return data

    def fill_cached_data(self, data: dict):
        for a in self.cached_attrs():
            val = data.get(a)

            if val:
                setattr(self, a, val)

    def can_be_run(self) -> bool:
        return self.installed

    def get_publisher(self) -> str:
        return self.author

    def get_disk_cache_path(self) -> str:
        if self.install_dir:
            return self.install_dir
        elif self.name:
            return f'{INSTALLATION_DIR}/{self.name.lower()}'

    def get_disk_icon_path(self):
        return self.icon_path

    def has_screenshots(self):
        return not self.installed and self.url_screenshot

    def get_name_tooltip(self) -> str:
        if self.name and self.imported:
            return '{} ({})'.format(self.name, self.i18n['imported'])

        return self.name

    def get_custom_actions(self) -> Optional[Iterable[CustomSoftwareAction]]:
        if self.installed and self.imported:
            return self.actions_local_installation()

    def supports_backup(self) -> bool:
        return False

    def supports_ignored_updates(self) -> bool:
        return self.installed and not self.imported

    def is_update_ignored(self) -> bool:
        return self.updates_ignored

    def __eq__(self, other):
        if isinstance(other, AppImage):
            return self.name == other.name and self.local_file_path == other.local_file_path

    def get_clean_name(self) -> Optional[str]:
        if self.name:
            return self.re_many_spaces().sub('-', self.name.lower().strip())

    def to_desktop_entry(self) -> str:
        de = StringIO()
        de.write("[Desktop Entry]\nType=Application\nName={}\n".format(self.name))

        if self.description:
            de.write("Comment={}\n".format(self.description.replace('\n', ' ')))

        if self.install_dir and self.local_file_path:
            de.write('Exec="{}/{}"\n'.format(self.install_dir, self.local_file_path.split('/')[-1]))

        if self.icon_path:
            de.write('Icon={}\n'.format(self.icon_path))

        if self.categories:
            de.write('Categories={};\n'.format(';'.join((c for c in self.categories if c.lower() != 'imported'))))

        de.write('Terminal=false')
        de.seek(0)
        return de.read()
