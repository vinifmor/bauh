from bauh.commons.system import SimpleProcess
from bauh.gems.web import NATIVEFIER_BIN_PATH


def install(url: str, name: str, output_dir: str, electron_version: str, cwd: str) -> SimpleProcess:
    return SimpleProcess([NATIVEFIER_BIN_PATH, url, '--name', name, '-e', electron_version, output_dir], cwd=cwd)
