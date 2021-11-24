import os
from pathlib import Path
from typing import Optional

from bauh.api.paths import CONFIG_PATH, TEMP_DIR, CACHE_PATH
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_PATH = '{}/.local/share/bauh/appimage'.format(str(Path.home()))
INSTALLATION_PATH = LOCAL_PATH + '/installed/'
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/suggestions.txt'
CONFIG_FILE = f'{CONFIG_PATH}/appimage.yml'
CONFIG_DIR = f'{CONFIG_PATH}/appimage'
UPDATES_IGNORED_FILE = '{}/updates_ignored.txt'.format(CONFIG_DIR)
SYMLINKS_DIR = '{}/.local/bin'.format(str(Path.home()))
URL_COMPRESSED_DATABASES = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/dbs.tar.gz'
APPIMAGE_CACHE_PATH = f'{CACHE_PATH}/appimage'
DATABASE_APPS_FILE = f'{APPIMAGE_CACHE_PATH}/apps.db'
DATABASE_RELEASES_FILE = f'{APPIMAGE_CACHE_PATH}/releases.db'
DATABASES_TS_FILE = f'{APPIMAGE_CACHE_PATH}/dbs.ts'
DESKTOP_ENTRIES_PATH = '{}/.local/share/applications'.format(str(Path.home()))
SUGGESTIONS_CACHED_FILE = f'{APPIMAGE_CACHE_PATH}/suggestions.txt'
SUGGESTIONS_CACHED_TS_FILE = f'{APPIMAGE_CACHE_PATH}/suggestions.ts'
DOWNLOAD_DIR = f'{TEMP_DIR}/appimage/download'


def get_icon_path() -> str:
    return resource.get_path('img/appimage.svg', ROOT_DIR)


def get_default_manual_installation_file_dir() -> Optional[str]:
    default_path = '{}/Downloads'.format(str(Path.home()))
    return default_path if os.path.isdir(default_path) else None
