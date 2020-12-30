from bauh.commons.config import YAMLConfigManager
from bauh.gems.snap import CONFIG_FILE


class SnapConfigManager(YAMLConfigManager):

    def __init__(self):
        super(SnapConfigManager, self).__init__(config_file_path=CONFIG_FILE)

    def get_default_config(self) -> dict:
        return {'install_channel': False, 'categories_exp': 24}
