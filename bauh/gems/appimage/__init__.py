import os

from bauh.api.constants import HOME_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
INSTALLATION_PATH = '{}/.local/share/bauh/appimage/installed/'.format(HOME_PATH)
