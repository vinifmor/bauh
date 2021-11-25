import os
from pathlib import Path
from typing import Optional

from bauh.api.paths import CONFIG_DIR, TEMP_DIR, CACHE_DIR
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_PATH = '{}/.local/share/bauh/appimage'.format(str(Path.home()))
INSTALLATION_PATH = LOCAL_PATH + '/installed/'
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/suggestions.txt'
CONFIG_FILE = f'{CONFIG_DIR}/appimage.yml'
APPIMAGE_CONFIG_DIR = f'{CONFIG_DIR}/appimage'
UPDATES_IGNORED_FILE = f'{APPIMAGE_CONFIG_DIR}/updates_ignored.txt'
SYMLINKS_DIR = '{}/.local/bin'.format(str(Path.home()))
URL_COMPRESSED_DATABASES = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/dbs.tar.gz'
APPIMAGE_CACHE_DIR = f'{CACHE_DIR}/appimage'
DATABASE_APPS_FILE = f'{APPIMAGE_CACHE_DIR}/apps.db'
DATABASE_RELEASES_FILE = f'{APPIMAGE_CACHE_DIR}/releases.db'
DATABASES_TS_FILE = f'{APPIMAGE_CACHE_DIR}/dbs.ts'
SUGGESTIONS_CACHED_FILE = f'{APPIMAGE_CACHE_DIR}/suggestions.txt'
SUGGESTIONS_CACHED_TS_FILE = f'{APPIMAGE_CACHE_DIR}/suggestions.ts'
DOWNLOAD_DIR = f'{TEMP_DIR}/appimage/download'


def get_icon_path() -> str:
    return resource.get_path('img/appimage.svg', ROOT_DIR)


def get_default_manual_installation_file_dir() -> Optional[str]:
    default_path = '{}/Downloads'.format(str(Path.home()))
    return default_path if os.path.isdir(default_path) else None
