from bauh.commons.config import read_config as read
from bauh.gems.arch import CONFIG_FILE


def read_config(update_file: bool = False) -> dict:
    template = {'optimize': True, 'transitive_checking': True}
    return read(CONFIG_FILE, template, update_file=update_file)
