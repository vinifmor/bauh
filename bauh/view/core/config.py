import logging
import os
import traceback
from pathlib import Path
from typing import List

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
            'check_interval': 30
        },
        'system': {
          'notifications': True,
          'single_dependency_checking': False
        },
        'disk_cache': {
            'enabled': True
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
            'style': None
        },
        'download': {
            'multithreaded': True,
            'icons': True
        }
    }
    return read(FILE_PATH, default, update_file=update_file, update_async=True)


def save(config: dict):
    Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)

    with open(FILE_PATH, 'w+') as f:
        f.write(yaml.safe_dump(config))


def remove_old_config(logger: logging.Logger):
    old_file = FILE_PATH.replace('.yml', '.json')
    if os.path.exists(old_file):
        try:
            os.remove(old_file)
            logger.info('Old configuration file {} deleted'.format(old_file))
        except:
            logger.error('Could not delete the old configuration file {}'.format(old_file))
            traceback.print_exc()
