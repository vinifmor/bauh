import os

from bauh.api.constants import CACHE_PATH, HOME_PATH, CONFIG_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = '/tmp/bauh/aur'
ARCH_CACHE_PATH = CACHE_PATH + '/arch'
CATEGORIES_CACHE_DIR = ARCH_CACHE_PATH + '/categories'
CATEGORIES_FILE_PATH = CATEGORIES_CACHE_DIR + '/aur.txt'
URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/aur/categories.txt'
CONFIG_DIR = '{}/.config/bauh/arch'.format(HOME_PATH)
CUSTOM_MAKEPKG_FILE = '{}/makepkg.conf'.format(CONFIG_DIR)
AUR_INDEX_FILE = '{}/aur.txt'.format(BUILD_DIR)
CONFIG_FILE = '{}/arch.yml'.format(CONFIG_PATH)
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/aur/suggestions.txt'
