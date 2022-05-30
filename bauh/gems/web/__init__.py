import os

from bauh import __app_name__
from bauh.api.paths import DESKTOP_ENTRIES_DIR, CONFIG_DIR, TEMP_DIR, CACHE_DIR, SHARED_FILES_DIR
from bauh.commons import resource
from bauh.commons.util import map_timestamp_file

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_SHARED_DIR = f'{SHARED_FILES_DIR}/web'
WEB_CACHE_DIR = f'{CACHE_DIR}/web'
INSTALLED_PATH = f'{WEB_SHARED_DIR}/installed'
ENV_PATH = f'{WEB_SHARED_DIR}/env'
FIX_FILE_PATH = WEB_SHARED_DIR + '/fixes/{electron_branch}/{app_id}.js'
NODE_DIR_PATH = f'{ENV_PATH}/node'
NODE_PATHS = {f'{NODE_DIR_PATH}/bin'}
NODE_BIN_PATH = f'{NODE_DIR_PATH}/bin/node'
NPM_BIN_PATH = f'{NODE_DIR_PATH}/bin/npm'
NODE_MODULES_PATH = f'{ENV_PATH}/node_modules'
NATIVEFIER_BIN_PATH = f'{NODE_MODULES_PATH}/.bin/nativefier'
ELECTRON_CACHE_DIR = f'{ENV_PATH}/electron'
URL_ENVIRONMENT_SETTINGS = f'https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/env/v2/environment.yml'
DESKTOP_ENTRY_PATH_PATTERN = f'{DESKTOP_ENTRIES_DIR}/{__app_name__}.web.' + '{name}.desktop'
URL_FIX_PATTERN = "https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/env/v2/fix/{domain}/{electron_branch}/fix.js"
URL_PROPS_PATTERN = "https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/env/v2/fix/{domain}/{electron_branch}/properties"
UA_CHROME = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
TEMP_PATH = f'{TEMP_DIR}/web'
SEARCH_INDEX_FILE = f'{WEB_CACHE_DIR}/index.yml'
CONFIG_FILE = f'{CONFIG_DIR}/web.yml'
ENVIRONMENT_SETTINGS_CACHED_FILE = f'{WEB_CACHE_DIR}/environment.yml'
ENVIRONMENT_SETTINGS_TS_FILE = f'{WEB_CACHE_DIR}/environment.ts'


def get_icon_path() -> str:
    return resource.get_path('img/web.svg', ROOT_DIR)
