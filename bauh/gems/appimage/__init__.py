import os
from pathlib import Path
from typing import Optional

from bauh.api.constants import CONFIG_PATH, CACHE_PATH
from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_PATH = '{}/.local/share/bauh/appimage'.format(str(Path.home()))
INSTALLATION_PATH = LOCAL_PATH + '/installed/'
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/suggestions.txt'
CONFIG_FILE = '{}/appimage.yml'.format(CONFIG_PATH)
CONFIG_DIR = '{}/appimage'.format(CONFIG_PATH)
UPDATES_IGNORED_FILE = '{}/updates_ignored.txt'.format(CONFIG_DIR)
SYMLINKS_DIR = '{}/.local/bin'.format(str(Path.home()))
URL_COMPRESSED_DATABASES = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/dbs.tar.gz'
APPIMAGE_CACHE_PATH = '{}/appimage'.format(CACHE_PATH)
DATABASE_APPS_FILE = '{}/apps.db'.format(APPIMAGE_CACHE_PATH)
DATABASE_RELEASES_FILE = '{}/releases.db'.format(APPIMAGE_CACHE_PATH)
DATABASES_TS_FILE = '{}/dbs.ts'.format(APPIMAGE_CACHE_PATH)
DESKTOP_ENTRIES_PATH = '{}/.local/share/applications'.format(str(Path.home()))
SUGGESTIONS_CACHED_FILE = '{}/suggestions.txt'.format(APPIMAGE_CACHE_PATH)
SUGGESTIONS_CACHED_TS_FILE = '{}/suggestions.ts'.format(APPIMAGE_CACHE_PATH)


def get_icon_path() -> str:
    return resource.get_path('img/appimage.svg', ROOT_DIR)


def get_default_manual_installation_file_dir() -> Optional[str]:
    default_path = '{}/Downloads'.format(str(Path.home()))
    return default_path if os.path.isdir(default_path) else None
