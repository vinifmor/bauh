from pathlib import Path

from bauh import __app_name__
from bauh.commons.config import YAMLConfigManager

FILE_PATH = '{}/.config/{}/config.yml'.format(str(Path.home()), __app_name__)


class CoreConfigManager(YAMLConfigManager):

    def __init__(self):
        super(CoreConfigManager, self).__init__(config_file_path=FILE_PATH)

    def get_default_config(self) -> dict:
        return {
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
                'qt_style': 'fusion',
                'hdpi': True,
                "auto_scale": False,
                "scale_factor": 1.0,
                'theme': 'light',
                'system_theme': False

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
            },
            'boot': {
                'load_apps': True
            }
        }
