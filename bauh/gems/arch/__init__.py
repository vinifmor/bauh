import os
from typing import Optional

from bauh import __app_name__
from bauh.api.paths import CONFIG_DIR, TEMP_DIR, CACHE_DIR, get_temp_dir
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ARCH_CACHE_DIR = f'{CACHE_DIR}/arch'
CATEGORIES_FILE_PATH = f'{ARCH_CACHE_DIR}/categories.txt'
URL_CATEGORIES_FILE = f'https://raw.githubusercontent.com/vinifmor/{__app_name__}-files/master/arch/categories.txt'
URL_GPG_SERVERS = f'https://raw.githubusercontent.com/vinifmor/{__app_name__}-files/master/arch/gpgservers.txt'
ARCH_CONFIG_DIR = f'{CONFIG_DIR}/arch'
CUSTOM_MAKEPKG_FILE = f'{ARCH_CONFIG_DIR}/makepkg.conf'
AUR_INDEX_FILE = f'{ARCH_CACHE_DIR}/aur/index.txt'
AUR_INDEX_TS_FILE = f'{ARCH_CACHE_DIR}/aur/index.ts'
CONFIG_FILE = f'{CONFIG_DIR}/arch.yml'
UPDATES_IGNORED_FILE = f'{ARCH_CONFIG_DIR}/updates_ignored.txt'
EDITABLE_PKGBUILDS_FILE = f'{ARCH_CONFIG_DIR}/aur/editable_pkgbuilds.txt'
IGNORED_REBUILD_CHECK_FILE = f'{ARCH_CONFIG_DIR}/aur/ignored_rebuild_check.txt'


def get_pkgbuild_dir(user: Optional[str] = None) -> str:
    return f'{get_temp_dir(user) if user else TEMP_DIR}/arch'


def get_icon_path() -> str:
    return resource.get_path('img/arch.svg', ROOT_DIR)


def get_repo_icon_path() -> str:
    return resource.get_path('img/repo.svg', ROOT_DIR)
