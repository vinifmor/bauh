import os

from bauh.api.constants import CACHE_PATH, CONFIG_PATH
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAP_CACHE_PATH = CACHE_PATH + '/snap'
CONFIG_FILE = '{}/snap.yml'.format(CONFIG_PATH)
CATEGORIES_FILE_PATH = SNAP_CACHE_PATH + '/categories.txt'
URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/snap/categories.txt'
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/snap/suggestions.txt'


def get_icon_path() -> str:
    return resource.get_path('img/snap.svg', ROOT_DIR)
