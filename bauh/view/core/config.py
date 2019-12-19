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

# TODO stopped here
class UpdatesSettings:

    def __init__(self, check_interval: int, **kwargs):
        self.check_interval = check_interval


class CacheSettings:

    def __init__(self, data_expiration: int, icon_expiration: int, **kwargs):
        self.data_expiration = data_expiration
        self.icon_expiration = icon_expiration


class Configuration:

    def __init__(self, gems: List[str], style: str, cache: dict, locale: str,
                 updates: dict, system_notifications: bool, disk_cache: bool, download_icons: bool,
                 check_packaging_once: bool, suggestions: bool, max_displayed: int, download_mthread: bool,
                 **kwargs):
        self.gems = gems
        self.style = style
        self.cache = CacheSettings(**cache)
        self.locale = locale
        self.updates = UpdatesSettings(**updates)
        self.system_notifications = system_notifications
        self.disk_cache = disk_cache
        self.download_icons = download_icons
        self.check_packaging_once = check_packaging_once
        self.suggestions = suggestions
        self.max_displayed = max_displayed
        self.download_mthread = download_mthread


def read_config(update_file: bool = False) -> Configuration:
    default = {
        'gems': None,
        'style': None,
        'cache_exp': 60 * 60,
        'icon_exp': 60 * 5,
        'locale': None,
        'updates': {
            'check_interval': 60
        },
        'system_notifications': True,
        'disk_cache': True,
        'download_icons': True,
        'check_packaging_once': False,
        'suggestions': True,
        'max_displayed': 50,  # table
        'download_mthread': True  # downloads
    }
    obj = read(FILE_PATH, default, update_file=update_file, update_async=True)
    return Configuration(**obj)


def save(config: Configuration):
    Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)

    with open(FILE_PATH, 'w+') as f:
        f.write(yaml.safe_dump(config.__dict__))


def remove_old_config(logger: logging.Logger):
    old_file = FILE_PATH.replace('.yml', '.json')
    if os.path.exists(old_file):
        try:
            os.remove(old_file)
            logger.info('Old configuration file {} deleted'.format(old_file))
        except:
            logger.error('Could not delete the old configuration file {}'.format(old_file))
            traceback.print_exc()
