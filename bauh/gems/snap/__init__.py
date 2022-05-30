import os

from bauh.api.paths import CONFIG_DIR, CACHE_DIR
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAP_CACHE_DIR = f'{CACHE_DIR}/snap'
CONFIG_FILE = f'{CONFIG_DIR}/snap.yml'
CATEGORIES_FILE_PATH = f'{SNAP_CACHE_DIR}/categories.txt'
URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/snap/categories.txt'


def get_icon_path() -> str:
    return resource.get_path('img/snap.svg', ROOT_DIR)
