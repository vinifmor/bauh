from bauh.commons.config import read_config as read
from bauh.gems.arch import CONFIG_FILE


def read_config(update_file: bool = False) -> dict:
    template = {'optimize': True,
                "sync_databases": True,
                "simple_checking": False,
                "clean_cached": True,
                'aur': True,
                'repositories': True,
                "refresh_mirrors_startup": False,
                "sync_databases_startup": True,
                'mirrors_sort_limit': 10}
    return read(CONFIG_FILE, template, update_file=update_file)
