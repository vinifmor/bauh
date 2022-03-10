import os

from bauh.api.paths import CACHE_DIR, CONFIG_DIR
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

DEBIAN_CACHE_DIR = f'{CACHE_DIR}/debian'
APP_INDEX_FILE = f'{DEBIAN_CACHE_DIR}/apps_idx.json'
CONFIG_FILE = f'{CONFIG_DIR}/debian.yml'
PACKAGE_SYNC_TIMESTAMP_FILE = f'{DEBIAN_CACHE_DIR}/sync_pkgs.ts'
DEBIAN_ICON_PATH = resource.get_path('img/debian.svg', ROOT_DIR)
