from bauh.commons.config import YAMLConfigManager
from bauh.gems.debian import CONFIG_FILE


class DebianConfigManager(YAMLConfigManager):

    def __init__(self):
        super(DebianConfigManager, self).__init__(config_file_path=CONFIG_FILE)

    def get_default_config(self) -> dict:
        return {
                'suggestions.exp': 24,  # hours
                'index_apps.exp': 1440,  # 24 hours
                'sync_pkgs.time': 1440,  # 24 hours
                'pkg_sources.app': None,
                'remove.purge': False
                }
