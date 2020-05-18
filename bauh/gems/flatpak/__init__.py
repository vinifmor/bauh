import os

from bauh.api.constants import CONFIG_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/flatpak/suggestions.txt'
CONFIG_FILE = '{}/flatpak.yml'.format(CONFIG_PATH)
CONFIG_DIR = '{}/flatpak'.format(CONFIG_PATH)
UPDATES_IGNORED_FILE = '{}/updates_ignored.txt'.format(CONFIG_DIR)
