from bauh.api.abstract.model import SoftwarePackage
from bauh.api.constants import CACHE_PATH
from bauh.commons import resource
from bauh.gems.web import ROOT_DIR


class WebApplication(SoftwarePackage):

    def __init__(self, url: str, name: str, description: str, icon_url: str):
        super(WebApplication, self).__init__(id=url, name=name, description=description, icon_url=icon_url)
        self.url = url

    def has_history(self):
        return False

    def has_info(self):
        return False

    def can_be_downgraded(self):
        return False

    def get_type(self):
        return 'web'

    def get_type_icon_path(self) -> str:
        return self.get_default_icon_path()

    def get_default_icon_path(self) -> str:
        return resource.get_path('img/web.png', ROOT_DIR)

    def is_application(self):
        return True

    def supports_disk_cache(self):
        return self.installed and self.is_application()

    def get_disk_cache_path(self):
        return CACHE_PATH + '/' + self.get_type()

    def get_data_to_cache(self) -> dict:
        """
        :return: the application data that should be cached in disk / memory for quick access
        """
        pass

    def fill_cached_data(self, data: dict):
        pass

    def can_be_run(self) -> bool:
        return self.installed

    def is_trustable(self) -> bool:
        return False

    def get_publisher(self) -> str:
        pass

    def has_screenshots(self) -> bool:
        return False
