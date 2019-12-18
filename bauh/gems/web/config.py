from bauh.commons.config import read_config as read
from bauh.gems.web import CONFIG_FILE


def read_config(update_file: bool = False) -> dict:
    default_config = {
        'environment': {
            'system': False,
            'electron': {'version': None}
        }
    }

    return read(CONFIG_FILE, default_config, update_file)

