from pathlib import Path

import yaml

from bauh import __app_name__
from bauh.commons.config import read_config as read

CONFIG_PATH = '{}/.config/{}'.format(Path.home(), __app_name__)
FILE_PATH = '{}/config.yml'.format(CONFIG_PATH)


def read_config(update_file: bool = False) -> dict:
    default = {
        'gems': None,
        'memory_cache': {
            'data_expiration': 60 * 60,
            'icon_expiration': 60 * 5
        },
        'locale': None,
        'updates': {
            'check_interval': 30,
            'ask_for_reboot': True
        },
        'system': {
          'notifications': True,
          'single_dependency_checking': False
        },
        'suggestions': {
            'enabled': True,
            'by_type': 10
        },
        'ui': {
            'table': {
                'max_displayed': 50
            },
            'tray': {
                'default_icon': None,
                'updates_icon': None
            },
            'style': None,
            'hdpi': True,
            "auto_scale": False

        },
        'download': {
            'multithreaded': True,
            'multithreaded_client': None,
            'icons': True
        },
        'store_root_password': True,
        'disk': {
            'trim': {
                'after_upgrade': False
            }
        },
        'backup': {
            'enabled': True,
            'install': None,
            'uninstall': None,
            'downgrade': None,
            'upgrade': None,
            'mode': 'incremental',
            'type': 'rsync'
        }

    }
    return read(FILE_PATH, default, update_file=update_file, update_async=True)


def save(config: dict):
    Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)

    with open(FILE_PATH, 'w+') as f:
        f.write(yaml.safe_dump(config))
