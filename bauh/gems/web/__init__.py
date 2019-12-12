import os

from bauh.api.constants import HOME_PATH, DESKTOP_ENTRIES_DIR

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_PATH = '{}/.local/share/bauh/web'.format(HOME_PATH)
INSTALLED_PATH = '{}/installed'.format(BIN_PATH)
NODE_DIR_PATH = '{}/node'.format(BIN_PATH)
NODE_BIN_PATH = '{}/bin/node'.format(NODE_DIR_PATH)
NPM_BIN_PATH = '{}/bin/npm'.format(NODE_DIR_PATH)
NODE_MODULES_PATH = '{}/node_modules'.format(BIN_PATH)
NATIVEFIER_BIN_PATH = '{}/.bin/nativefier'.format(NODE_MODULES_PATH)
ELECTRON_PATH = '{}/.cache/electron'.format(HOME_PATH)
ELECTRON_DOWNLOAD_URL = 'https://github.com/electron/electron/releases/download/v{version}/electron-v{version}-linux-{arch}.zip'
ELECTRON_SHA256_URL = 'https://github.com/electron/electron/releases/download/v{version}/SHASUMS256.txt'
URL_ENVIRONMENT_SETTINGS = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/environment.yml'
DESKTOP_ENTRY_PATH_PATTERN = DESKTOP_ENTRIES_DIR + '/bauh.web.{name}.desktop'
URL_FIX_PATTERN = "https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/fix/{url}.js"
