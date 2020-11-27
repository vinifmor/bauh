import os
from pathlib import Path

CACHE_PATH = '{}/.cache/bauh'.format(str(Path.home()))
CONFIG_PATH = '{}/.config/bauh'.format(str(Path.home()))
USER_THEMES_PATH = '{}/.local/share/bauh/themes'.format(str(Path.home()))
DESKTOP_ENTRIES_DIR = '{}/.local/share/applications'.format(str(Path.home()))
TEMP_DIR = '/tmp/bauh{}'.format('_root' if os.getuid() == 0 else '')
