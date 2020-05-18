import os
from pathlib import Path

from bauh.commons import resource

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SUGGESTIONS_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/flatpak/suggestions.txt'
CONFIG_FILE = '{}/.config/bauh/flatpak.yml'.format(Path.home())

def get_icon_path() -> str:
    return resource.get_path('img/flatpak.svg', ROOT_DIR)
