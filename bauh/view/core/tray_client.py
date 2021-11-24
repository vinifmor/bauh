from pathlib import Path

from bauh.api.paths import CACHE_PATH

TRAY_CHECK_FILE = f'{CACHE_PATH}/notify_tray'  # it is a file that signals to the tray icon it should recheck for updates


def notify_tray():
    Path(CACHE_PATH).mkdir(exist_ok=True, parents=True)

    with open(TRAY_CHECK_FILE, 'w+') as f:
        f.write('')
