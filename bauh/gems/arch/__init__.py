import os
from pathlib import Path

from bauh.api.constants import CACHE_PATH, CONFIG_PATH, TEMP_DIR
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = '{}/arch'.format(TEMP_DIR)
ARCH_CACHE_PATH = CACHE_PATH + '/arch'
CATEGORIES_FILE_PATH = ARCH_CACHE_PATH + '/categories.txt'
URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/arch/categories.txt'
URL_GPG_SERVERS = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/arch/gpgservers.txt'
CONFIG_DIR = '{}/.config/bauh/arch'.format(str(Path.home()))
CUSTOM_MAKEPKG_FILE = '{}/makepkg.conf'.format(CONFIG_DIR)
AUR_INDEX_FILE = '{}/aur/index.txt'.format(ARCH_CACHE_PATH)
AUR_INDEX_TS_FILE = '{}/aur/index.ts'.format(ARCH_CACHE_PATH)
CONFIG_FILE = '{}/arch.yml'.format(CONFIG_PATH)
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/arch/aur_suggestions.txt'
UPDATES_IGNORED_FILE = '{}/updates_ignored.txt'.format(CONFIG_DIR)
EDITABLE_PKGBUILDS_FILE = '{}/aur/editable_pkgbuilds.txt'.format(CONFIG_DIR)
IGNORED_REBUILD_CHECK_FILE = '{}/aur/ignored_rebuild_check.txt'.format(CONFIG_DIR)


def get_icon_path() -> str:
    return resource.get_path('img/arch.svg', ROOT_DIR)


def get_repo_icon_path() -> str:
    return resource.get_path('img/repo.svg', ROOT_DIR)
