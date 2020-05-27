import os
from pathlib import Path

from bauh.api.constants import CACHE_PATH, CONFIG_PATH, TEMP_DIR
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = '{}/arch'.format(TEMP_DIR)
PACKAGE_CACHE_DIR = '{}/pkg_cache'.format(BUILD_DIR)
ARCH_CACHE_PATH = CACHE_PATH + '/arch'
CATEGORIES_FILE_PATH = ARCH_CACHE_PATH + '/categories.txt'
URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/arch/categories.txt'
CONFIG_DIR = '{}/.config/bauh/arch'.format(str(Path.home()))
CUSTOM_MAKEPKG_FILE = '{}/makepkg.conf'.format(CONFIG_DIR)
AUR_INDEX_FILE = '{}/arch.txt'.format(BUILD_DIR)
CONFIG_FILE = '{}/arch.yml'.format(CONFIG_PATH)
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/arch/aur_suggestions.txt'
UPDATES_IGNORED_FILE = '{}/updates_ignored.txt'.format(CONFIG_DIR)


def get_icon_path() -> str:
    return resource.get_path('img/arch.svg', ROOT_DIR)


def get_repo_icon_path() -> str:
    return resource.get_path('img/repo.svg', ROOT_DIR)
