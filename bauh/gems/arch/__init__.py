import os

from bauh.api.paths import CONFIG_DIR, TEMP_DIR, CACHE_PATH
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = f'{TEMP_DIR}/arch'
ARCH_CACHE_PATH = f'{CACHE_PATH}/arch'
CATEGORIES_FILE_PATH = f'{ARCH_CACHE_PATH}/categories.txt'
URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/arch/categories.txt'
URL_GPG_SERVERS = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/arch/gpgservers.txt'
ARCH_CONFIG_DIR = f'{CONFIG_DIR}/arch'
CUSTOM_MAKEPKG_FILE = f'{ARCH_CONFIG_DIR}/makepkg.conf'
AUR_INDEX_FILE = f'{ARCH_CACHE_PATH}/aur/index.txt'
AUR_INDEX_TS_FILE = f'{ARCH_CACHE_PATH}/aur/index.ts'
CONFIG_FILE = f'{CONFIG_DIR}/arch.yml'
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/arch/aur_suggestions.txt'
UPDATES_IGNORED_FILE = f'{ARCH_CONFIG_DIR}/updates_ignored.txt'
EDITABLE_PKGBUILDS_FILE = f'{ARCH_CONFIG_DIR}/aur/editable_pkgbuilds.txt'
IGNORED_REBUILD_CHECK_FILE = f'{ARCH_CONFIG_DIR}/aur/ignored_rebuild_check.txt'


def get_icon_path() -> str:
    return resource.get_path('img/arch.svg', ROOT_DIR)


def get_repo_icon_path() -> str:
    return resource.get_path('img/repo.svg', ROOT_DIR)
