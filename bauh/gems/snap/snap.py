import os
import subprocess
from io import StringIO
from typing import Tuple, Optional

from bauh.commons.system import run_cmd, SimpleProcess

BASE_CMD = 'snap'


def is_installed() -> bool:
    return bool(run_cmd('which {}'.format(BASE_CMD), print_error=False))


def uninstall_and_stream(app_name: str, root_password: str) -> SimpleProcess:
    return SimpleProcess(cmd=[BASE_CMD, 'remove', app_name],
                         root_password=root_password,
                         shell=True)


def install_and_stream(app_name: str, confinement: str, root_password: str, channel: Optional[str] = None) -> SimpleProcess:

    install_cmd = [BASE_CMD, 'install', app_name]  # default

    if confinement == 'classic':
        install_cmd.append('--classic')

    if channel:
        install_cmd.append('--channel={}'.format(channel))

    return SimpleProcess(install_cmd, root_password=root_password, shell=True)


def downgrade_and_stream(app_name: str, root_password: str) -> SimpleProcess:
    return SimpleProcess(cmd=[BASE_CMD, 'revert', app_name],
                         root_password=root_password,
                         shell=True)


def refresh_and_stream(app_name: str, root_password: str, channel: Optional[str] = None) -> SimpleProcess:
    cmd = [BASE_CMD, 'refresh', app_name]

    if channel:
        cmd.append('--channel={}'.format(channel))

    return SimpleProcess(cmd=cmd,
                         root_password=root_password,
                         error_phrases={'no updates available'},
                         shell=True)


def run(cmd: str):
    subprocess.Popen(['snap run {}'.format(cmd)], shell=True, env={**os.environ})


def is_api_available() -> Tuple[bool, str]:
    output = StringIO()
    for o in SimpleProcess([BASE_CMD, 'search']).instance.stdout:
        if o:
            output.write(o.decode())

    output.seek(0)
    output = output.read()
    return 'error:' not in output, output
