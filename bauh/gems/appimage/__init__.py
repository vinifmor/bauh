import os
from pathlib import Path
from typing import Optional

from bauh import __app_name__
from bauh.api.paths import CONFIG_DIR, TEMP_DIR, CACHE_DIR, BINARIES_DIR, SHARED_FILES_DIR
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
APPIMAGE_SHARED_DIR = f'{SHARED_FILES_DIR}/appimage'
INSTALLATION_DIR = f'{APPIMAGE_SHARED_DIR}/installed'
CONFIG_FILE = f'{CONFIG_DIR}/appimage.yml'
APPIMAGE_CONFIG_DIR = f'{CONFIG_DIR}/appimage'
UPDATES_IGNORED_FILE = f'{APPIMAGE_CONFIG_DIR}/updates_ignored.txt'
SYMLINKS_DIR = BINARIES_DIR
URL_COMPRESSED_DATABASES = f'https://raw.githubusercontent.com/vinifmor/{__app_name__}-files/master/appimage/dbs.tar.gz'
APPIMAGE_CACHE_DIR = f'{CACHE_DIR}/appimage'
DATABASE_APPS_FILE = f'{APPIMAGE_CACHE_DIR}/apps.db'
DATABASE_RELEASES_FILE = f'{APPIMAGE_CACHE_DIR}/releases.db'
DATABASES_TS_FILE = f'{APPIMAGE_CACHE_DIR}/dbs.ts'
DOWNLOAD_DIR = f'{TEMP_DIR}/appimage/download'


def get_icon_path() -> str:
    return resource.get_path('img/appimage.svg', ROOT_DIR)


def get_default_manual_installation_file_dir() -> Optional[str]:
    default_path = f'{Path.home()}/Downloads'
    return default_path if os.path.isdir(default_path) else None
