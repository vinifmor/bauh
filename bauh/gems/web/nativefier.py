from typing import List, Optional

from bauh.commons.system import SimpleProcess, run_cmd
from bauh.gems.web import NATIVEFIER_BIN_PATH, NODE_PATHS


def install(url: str, name: str, output_dir: str, electron_version: Optional[str], cwd: str, system: bool, extra_options: List[str] = None) -> SimpleProcess:
    cmd = [NATIVEFIER_BIN_PATH if not system else 'nativefier', url, '--name', name, output_dir]

    if electron_version:
        cmd.append('-e')
        cmd.append(electron_version)

    if extra_options:
        cmd.extend(extra_options)

    return SimpleProcess(cmd, cwd=cwd, extra_paths=NODE_PATHS if not system else None)


def is_available() -> bool:
    res = run_cmd('which nativefier', print_error=False)
    return res and not res.strip().startswith('which ')


def get_version() -> str:
    return run_cmd('{} --version'.format(NATIVEFIER_BIN_PATH), print_error=False, extra_paths=NODE_PATHS)


