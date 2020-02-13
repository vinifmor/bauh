import os
from pathlib import Path

from bauh.api.constants import CACHE_PATH, CONFIG_PATH, TEMP_DIR

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = '{}/aur'.format(TEMP_DIR)
ARCH_CACHE_PATH = CACHE_PATH + '/arch'
CATEGORIES_CACHE_DIR = ARCH_CACHE_PATH + '/categories'
CATEGORIES_FILE_PATH = CATEGORIES_CACHE_DIR + '/aur.txt'
URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/aur/categories.txt'
CONFIG_DIR = '{}/.config/bauh/arch'.format(Path.home())
CUSTOM_MAKEPKG_FILE = '{}/makepkg.conf'.format(CONFIG_DIR)
AUR_INDEX_FILE = '{}/aur.txt'.format(BUILD_DIR)
CONFIG_FILE = '{}/arch.yml'.format(CONFIG_PATH)
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/aur/suggestions.txt'
