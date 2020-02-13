import os
from pathlib import Path

CACHE_PATH = '{}/.cache/bauh'.format(Path.home())
CONFIG_PATH = '{}/.config/bauh'.format(Path.home())
DESKTOP_ENTRIES_DIR = '{}/.local/share/applications'.format(Path.home())
TEMP_DIR = '/tmp/bauh{}'.format('_root' if os.getuid() == 0 else '')
