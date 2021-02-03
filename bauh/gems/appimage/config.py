from bauh.commons.config import YAMLConfigManager
from bauh.gems.appimage import CONFIG_FILE


class AppImageConfigManager(YAMLConfigManager):

    def __init__(self):
        super(AppImageConfigManager, self).__init__(config_file_path=CONFIG_FILE)

    def get_default_config(self) -> dict:
        return {
            'database': {
                'expiration': 60
            },
            'suggestions': {
                'expiration': 24
            }
        }
