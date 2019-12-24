import os
from pathlib import Path

from bauh.api.constants import HOME_PATH, DESKTOP_ENTRIES_DIR, CONFIG_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_PATH = '{}/.local/share/bauh/web'.format(Path.home())
INSTALLED_PATH = '{}/installed'.format(WEB_PATH)
ENV_PATH = '{}/env'.format(WEB_PATH)
NODE_DIR_PATH = '{}/node'.format(ENV_PATH)
NODE_PATHS = {NODE_DIR_PATH + '/bin'}
NODE_BIN_PATH = '{}/bin/node'.format(NODE_DIR_PATH)
NPM_BIN_PATH = '{}/bin/npm'.format(NODE_DIR_PATH)
NODE_MODULES_PATH = '{}/node_modules'.format(ENV_PATH)
NATIVEFIER_BIN_PATH = '{}/.bin/nativefier'.format(NODE_MODULES_PATH)
ELECTRON_PATH = '{}/.cache/electron'.format(HOME_PATH)
ELECTRON_DOWNLOAD_URL = 'https://github.com/electron/electron/releases/download/v{version}/electron-v{version}-linux-{arch}.zip'
ELECTRON_SHA256_URL = 'https://github.com/electron/electron/releases/download/v{version}/SHASUMS256.txt'
URL_ENVIRONMENT_SETTINGS = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/environment.yml'
DESKTOP_ENTRY_PATH_PATTERN = DESKTOP_ENTRIES_DIR + '/bauh.web.{name}.desktop'
URL_FIX_PATTERN = "https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/fix/{url}.js"
URL_SUGGESTIONS = "https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/suggestions.yml"
UA_CHROME = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'
TEMP_PATH = '/tmp/bauh/web'
SEARCH_INDEX_FILE = '{}/index.yml'.format(TEMP_PATH)
SUGGESTIONS_CACHE_FILE = '{}/suggestions.txt'.format(TEMP_PATH)
CONFIG_FILE = '{}/web.yml'.format(CONFIG_PATH)
URL_NATIVEFIER = 'https://github.com/jiahaog/nativefier/archive/v{version}.tar.gz'

