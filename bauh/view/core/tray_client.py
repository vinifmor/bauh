from pathlib import Path

from bauh.api.constants import CACHE_PATH

TRAY_CHECK_FILE = '{}/notify_tray'.format(CACHE_PATH)  # it is a file that signals to the tray icon it should recheck for updates


def notify_tray():
    Path(CACHE_PATH).mkdir(exist_ok=True, parents=True)

    with open(TRAY_CHECK_FILE, 'w+') as f:
        f.write('')
