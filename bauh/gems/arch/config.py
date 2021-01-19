from pathlib import Path

from bauh.commons.config import YAMLConfigManager
from bauh.gems.arch import CONFIG_FILE, BUILD_DIR


def get_build_dir(arch_config: dict) -> str:
    build_dir = arch_config.get('aur_build_dir')

    if not build_dir:
        build_dir = BUILD_DIR

    Path(build_dir).mkdir(parents=True, exist_ok=True)
    return build_dir


class ArchConfigManager(YAMLConfigManager):

    def __init__(self):
        super(ArchConfigManager, self).__init__(config_file_path=CONFIG_FILE)

    def get_default_config(self) -> dict:
        return {'optimize': True,
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
                'suggest_optdep_uninstall': False,
                'aur_idx_exp': 1,
                'categories_exp': 24,
                'aur_rebuild_detector': True,
                "aur_rebuild_detector_no_bin": True}
