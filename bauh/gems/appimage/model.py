from typing import List

from bauh.api.abstract.model import SoftwarePackage
from bauh.commons import resource
from bauh.gems.appimage import ROOT_DIR


class AppImage(SoftwarePackage):

    def __init__(self, name: str = None, description: str = None, github: str = None, source: str = None, version: str = None,
                 url_download: str = None, url_icon: str = None, license: str = None, pictures: List[str] = None):
        super(AppImage, self).__init__(name=name, version=version, latest_version=version,
                                       icon_url=url_icon, license=license, description=description)
        self.source = source
        self.github = github
        self.pictures = pictures
        self.url_download = url_download

    def can_be_installed(self):
        return not self.installed and self.url_download

    def has_history(self):
        # TODO
        return False

    def has_info(self):
        # TODO
        return False

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
        # TODO
        pass

    def fill_cached_data(self, data: dict):
        # TODO
        pass

    def can_be_run(self) -> str:
        # TODO
        return False

    def get_publisher(self) -> str:
        # TODO
        pass
