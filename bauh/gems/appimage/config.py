from bauh.commons.config import read_config as read
from bauh.gems.appimage import CONFIG_FILE


def read_config(update_file: bool = False) -> dict:
    default = {
        'database': {
            'expiration': 60
        }
    }
    return read(CONFIG_FILE, default, update_file=update_file)
