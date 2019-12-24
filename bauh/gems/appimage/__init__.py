import os

from bauh.api.constants import HOME_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_PATH = '{}/.local/share/bauh/appimage'.format(HOME_PATH)
INSTALLATION_PATH = LOCAL_PATH + '/installed/'
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/suggestions.txt'