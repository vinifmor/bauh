import os
from pathlib import Path

from packaging.version import parse as parse_version

from bauh import __app_name__
from bauh.api import user
from bauh.api.paths import CONFIG_DIR
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = f'{CONFIG_DIR}/flatpak.yml'
FLATPAK_CONFIG_DIR = f'{CONFIG_DIR}/flatpak'
UPDATES_IGNORED_FILE = f'{FLATPAK_CONFIG_DIR}/updates_ignored.txt'
EXPORTS_PATH = '/usr/share/flatpak/exports/share' if user.is_root() else f'{Path.home()}/.local/share/flatpak/exports/share'
VERSION_1_2 = parse_version('1.2')
VERSION_1_3 = parse_version('1.3')
VERSION_1_4 = parse_version('1.4')
VERSION_1_5 = parse_version('1.5')
VERSION_1_12 = parse_version('1.12')


def get_icon_path() -> str:
    return resource.get_path('img/flatpak.svg', ROOT_DIR)
