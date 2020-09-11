from pathlib import Path

from bauh.commons.config import read_config as read
from bauh.gems.arch import CONFIG_FILE, BUILD_DIR


def read_config(update_file: bool = False) -> dict:
    template = {'optimize': True,
                "sync_databases": True,
                "clean_cached": True,
                'aur': True,
                'repositories': True,
                "refresh_mirrors_startup": False,
                "sync_databases_startup": True,
                'mirrors_sort_limit': 5,
                'repositories_mthread_download': False,
                'automatch_providers': True,
                'edit_aur_pkgbuild': False,
                'aur_build_dir': None,
                'aur_remove_build_dir': True,
                'aur_build_only_chosen': True,
                'check_dependency_breakage': True,
                'suggest_unneeded_uninstall': False,
                'suggest_optdep_uninstall': False}
    return read(CONFIG_FILE, template, update_file=update_file)


def get_build_dir(arch_config: dict) -> str:
    build_dir = arch_config.get('aur_build_dir')

    if not build_dir:
        build_dir = BUILD_DIR

    Path(build_dir).mkdir(parents=True, exist_ok=True)
    return build_dir
