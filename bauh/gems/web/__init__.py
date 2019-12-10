import os

from bauh.api.constants import HOME_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_PATH = '{}/.local/share/bauh/web'.format(HOME_PATH)
NODE_DIR_PATH = '{}/node'.format(BIN_PATH)
NODE_BIN_PATH = '{}/bin/node'.format(NODE_DIR_PATH)
NPM_BIN_PATH = '{}/bin/npm'.format(NODE_DIR_PATH)
NODE_MODULES_PATH = '{}/node_modules'.format(BIN_PATH)
NATIVEFIER_BIN_PATH = '{}/.bin/nativefier'.format(NODE_MODULES_PATH)

