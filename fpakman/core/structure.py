from pathlib import Path

from fpakman import __app_name__

home_path = Path.home()
cache_path = '{}/.cache/{}'.format(home_path, __app_name__)
flatpak_cache_path = '{}/flatpak/installed'.format(cache_path)


def prepare_folder_structure(disk_cache: bool):
    if disk_cache:
        Path(flatpak_cache_path).mkdir(parents=True, exist_ok=True)
