from pathlib import Path

from bauh.api import user

CACHE_PATH = '{}/.cache/bauh'.format(str(Path.home()))
CONFIG_PATH = '{}/.config/bauh'.format(str(Path.home()))
USER_THEMES_PATH = '{}/.local/share/bauh/themes'.format(str(Path.home()))
DESKTOP_ENTRIES_DIR = '{}/.local/share/applications'.format(str(Path.home()))
TEMP_DIR = '/tmp/bauh{}'.format('_root' if user.is_root() else '')
