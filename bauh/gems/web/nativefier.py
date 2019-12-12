from typing import List

from bauh.commons.system import SimpleProcess
from bauh.gems.web import NATIVEFIER_BIN_PATH


def install(url: str, name: str, output_dir: str, electron_version: str, cwd: str, extra_options: List[str] = None) -> SimpleProcess:
    cmd = [NATIVEFIER_BIN_PATH, url, '--name', name, '-e', electron_version, output_dir]

    if extra_options:
        cmd.extend(extra_options)

    return SimpleProcess(cmd, cwd=cwd)
