from typing import List

from bauh.api.abstract.model import SoftwarePackage
from bauh.commons import resource
from bauh.gems.appimage import ROOT_DIR, INSTALLATION_PATH

CACHED_ATTRS = {'name', 'description', 'version', 'url_download', 'author', 'license', 'source', 'icon_path'}


class AppImage(SoftwarePackage):

    def __init__(self, name: str = None, description: str = None, github: str = None, source: str = None, version: str = None,
                 url_download: str = None, url_icon: str = None, license: str = None, author: str = None,
                 pictures: List[str] = None, icon_path: str = None, installed: bool = False):
        super(AppImage, self).__init__(id=name, name=name, version=version, latest_version=version,
                                       icon_url=url_icon, license=license, description=description,
                                       installed=installed)
        self.source = source
        self.github = github
        self.pictures = pictures
        self.url_download = url_download
        self.icon_path = icon_path
        self.author = author

    def can_be_installed(self):
        return not self.installed and self.url_download

    def has_history(self):
        # TODO
        return False

    def has_info(self):
        return True

    def can_be_downgraded(self):
        # TODO
        return False

    def get_type(self):
        return 'AppImage'

    def get_default_icon_path(self):
        return self.get_type_icon_path()

    def get_type_icon_path(self):
        return resource.get_path('img/appimage.png', ROOT_DIR)

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
        if self.name:
            return INSTALLATION_PATH + self.name.lower()

    def get_disk_icon_path(self):
        return self.icon_path
