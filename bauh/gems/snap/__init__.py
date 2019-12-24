import os

from bauh.api.constants import CACHE_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAP_CACHE_PATH = CACHE_PATH + '/snap'
CATEGORIES_FILE_PATH = SNAP_CACHE_PATH + '/categories.txt'
URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/snap/categories.txt'
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/snap/suggestions.txt'
