import os

from bauh.api.constants import HOME_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = '{}/.local/share/bauh/appimage'.format(HOME_PATH)
INSTALLATION_PATH = BASE_PATH + '/installed/'
