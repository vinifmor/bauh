import glob
import os
from pathlib import Path
from typing import List

from bauh.api.abstract.model import SoftwarePackage
from bauh.commons import resource, user
from bauh.gems.web import ROOT_DIR


class WebApplication(SoftwarePackage):

    def __init__(self, id: str = None, url: str = None, name: str = None, description: str = None, icon_url: str = None,
                 installation_dir: str = None, desktop_entry: str = None, installed: bool = False, version: str = None,
                 categories: List[str] = None, custom_icon: str = None, preset_options: List[str] = None, save_icon: bool = True,
                 options_set: List[str] = None, package_name: str = None, source_url: str = None):
        super(WebApplication, self).__init__(id=id if id else url, name=name, description=description,
                                             icon_url=icon_url, installed=installed, version=version,
                                             categories=categories)
        self.url = url
        self.source_url = source_url if source_url else url
        self.installation_dir = installation_dir
        self.desktop_entry = desktop_entry
        self.preset_options = preset_options
        self.save_icon = save_icon  # if the icon_url should be used instead of the one retrieved by nativefier
        self.options_set = options_set
        self.package_name = package_name
        self.custom_icon = custom_icon
        self.set_custom_icon(custom_icon)

    def get_source_url(self):
        if self.source_url:
            return self.source_url

        return self.url

    def set_version(self, version: str):
        self.version = str(version) if version else None
        self.latest_version = version

    def has_history(self):
        return False

    def has_info(self):
        return True

    @staticmethod
    def _get_cached_attrs() -> tuple:
        return 'id', 'name', 'version', 'url', 'description', 'icon_url', 'installation_dir', \
               'desktop_entry', 'categories', 'custom_icon', 'options_set', 'save_icon', 'package_name', 'source_url'

    def can_be_downgraded(self):
        return False

    def get_exec_path(self) -> str:
        if self.installation_dir:
            return '{}/{}'.format(self.installation_dir, self.id)

    def get_command(self) -> str:
        if self.installation_dir:
            return '{}{}'.format(self.get_exec_path(), ' --no-sandbox' if user.is_root() else '')

    def get_type(self):
        return 'web'

    def get_type_icon_path(self) -> str:
        return self.get_default_icon_path()

    def get_default_icon_path(self) -> str:
        return resource.get_path('img/web.svg', ROOT_DIR)

    def get_disk_data_path(self) -> str:
        return '{}/data.yml'.format(self.get_disk_cache_path())

    def get_disk_icon_path(self) -> str:
        if self.custom_icon:
            return self.custom_icon

        if self.installation_dir:
            return '{}/resources/app/icon.png'.format(self.installation_dir)

    def is_application(self):
        return True

    def supports_disk_cache(self):
        return self.installed

    def get_disk_cache_path(self):
        return self.installation_dir

    def get_data_to_cache(self) -> dict:
        data = {}

        for attr in self._get_cached_attrs():
            if hasattr(self, attr):
                val = getattr(self, attr)

                if val is not None:
                    data[attr] = val

        return data

    def fill_cached_data(self, data: dict):
        for attr in self._get_cached_attrs():
            val = data.get(attr)

            if val and hasattr(self, attr):
                setattr(self, attr, val)

        self.set_custom_icon(self.custom_icon)

    def can_be_run(self) -> bool:
        return self.installed and bool(self.installation_dir)

    def is_trustable(self) -> bool:
        return False

    def get_publisher(self) -> str:
        return 'bauh'

    def has_screenshots(self) -> bool:
        return False

    def get_autostart_path(self) -> str:
        if self.desktop_entry:
            return '{}/.config/autostart/{}'.format(Path.home(), self.desktop_entry.split('/')[-1])

    def set_custom_icon(self, custom_icon: str):
        self.custom_icon = custom_icon

        if custom_icon:
            self.icon_url = custom_icon

    def get_config_dir(self) -> str:
        if self.package_name:
            config_dir = '{}/.config/{}'.format(str(Path.home()), self.package_name)

            if os.path.exists(config_dir):
                return config_dir
        else:
            if self.installation_dir:
                config_path = '{}/.config'.format(str(Path.home()))

                if os.path.exists(config_path):
                    config_dirs = glob.glob('{}/{}-nativefier-*'.format(config_path, self.installation_dir.split('/')[-1]))

                    if config_dirs:
                        return config_dirs[0]

    def supports_backup(self) -> bool:
        return False

    def __eq__(self, other):
        if isinstance(other, WebApplication):
            return self.name == other.name and self.url == other.url
