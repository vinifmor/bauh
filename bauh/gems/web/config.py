from bauh.commons.config import YAMLConfigManager
from bauh.gems.web import CONFIG_FILE


class WebConfigManager(YAMLConfigManager):

    def __init__(self):
        super(WebConfigManager, self).__init__(config_file_path=CONFIG_FILE)

    def get_default_config(self) -> dict:
        return {
            'environment': {
                'system': False,
                'electron': {'version': None},
                'cache_exp': 24
            },
            'suggestions': {
                'cache_exp': 24
            }
        }
