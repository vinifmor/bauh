import re
from typing import List, Optional

from bauh.api.abstract.model import SoftwarePackage, CustomSoftwareAction
from bauh.commons import resource
from bauh.gems.appimage import ROOT_DIR, INSTALLATION_PATH
from bauh.view.util.translation import I18n

RE_MANY_SPACES = re.compile(r'\s+')

CACHED_ATTRS = {'name', 'description', 'version', 'url_download', 'author', 'license', 'source',
                'icon_path', 'github', 'categories', 'imported', 'install_dir', 'symlink'}


class AppImage(SoftwarePackage):

    def __init__(self, name: str = None, description: str = None, github: str = None, source: str = None, version: str = None,
                 url_download: str = None, url_icon: str = None, url_screenshot: str = None, license: str = None, author: str = None,
                 categories=None, icon_path: str = None, installed: bool = False,
                 url_download_latest_version: str = None, local_file_path: str = None, imported: bool = False,
                 i18n: I18n = None, install_dir: str = None, custom_actions: List[CustomSoftwareAction] = None, updates_ignored: bool = False,
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
        self.custom_actions = custom_actions
        self.updates_ignored = updates_ignored
        self.symlink = symlink

    def __repr__(self):
        return "{} (name={}, github={})".format(self.__class__.__name__, self.name, self.github)

    def can_be_installed(self):
        return not self.installed and self.url_download

    def has_history(self):
        return self.installed and not self.imported

    def has_info(self):
        return True

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

        for a in CACHED_ATTRS:
            val = getattr(self, a)
            if val:
                data[a] = val

        return data

    def fill_cached_data(self, data: dict):
        for a in CACHED_ATTRS:
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
            return INSTALLATION_PATH + self.name.lower()

    def get_disk_icon_path(self):
        return self.icon_path

    def has_screenshots(self):
        return not self.installed and self.url_screenshot

    def get_display_name(self) -> str:
        if self.name and self.imported:
            return '{} ({})'.format(self.name, self.i18n['imported'])

        return self.name

    def get_custom_supported_actions(self) -> List[CustomSoftwareAction]:
        if self.imported:
            return self.custom_actions

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
            return RE_MANY_SPACES.sub('-', self.name.lower().strip())
