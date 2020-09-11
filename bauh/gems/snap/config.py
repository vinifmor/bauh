from bauh.commons.config import read_config as read
from bauh.gems.snap import CONFIG_FILE


def read_config(update_file: bool = False) -> dict:
    template = {'install_channel': False}
    return read(CONFIG_FILE, template, update_file=update_file)
