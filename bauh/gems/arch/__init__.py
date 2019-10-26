import os

from bauh.api.constants import CACHE_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = '/tmp/bauh/aur'
ARCH_CACHE_PATH = CACHE_PATH + '/arch'
CATEGORIES_CACHE_DIR = ARCH_CACHE_PATH + '/categories'
CATEGORIES_FILE_PATH = CATEGORIES_CACHE_DIR + '/aur.txt'
URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/aur/categories.txt'
