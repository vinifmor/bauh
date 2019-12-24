from bauh.api.constants import CONFIG_PATH
from bauh.commons.config import read_config as read


def read_config(update_file: bool = False) -> dict:
    default = {
        'db_updater': {
            'interval': 60 * 20,
            'enabled': True
        }
    }
    return read('{}/appimage.yml'.format(CONFIG_PATH), default, update_file=update_file)
