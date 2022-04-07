import os
import shutil
from typing import List, Optional

from bauh.commons.system import SimpleProcess, run_cmd
from bauh.gems.web import NATIVEFIER_BIN_PATH, NODE_PATHS, ELECTRON_CACHE_DIR


def install(url: str, name: str, output_dir: str, electron_version: Optional[str], cwd: str, system: bool,
            user_agent: Optional[str] = None, extra_options: List[str] = None) -> SimpleProcess:
    cmd = [NATIVEFIER_BIN_PATH if not system else 'nativefier', url, '--name', name, output_dir]

    if electron_version:
        cmd.append('-e')
        cmd.append(electron_version)

    if user_agent:
        cmd.extend(('--user-agent', user_agent))

    if extra_options:
        cmd.extend(extra_options)

    extra_env = {'XDG_CACHE_HOME': os.path.dirname(ELECTRON_CACHE_DIR)} if not os.getenv('XDG_CACHE_HOME') else None
    return SimpleProcess(cmd, cwd=cwd, extra_paths=NODE_PATHS if not system else None,
                         extra_env=extra_env)


def is_available() -> bool:
    return bool(shutil.which('nativefier'))


def get_version() -> str:
    return run_cmd('{} --version'.format(NATIVEFIER_BIN_PATH), print_error=False, extra_paths=NODE_PATHS)


