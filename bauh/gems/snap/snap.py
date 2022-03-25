import os
import shutil
import subprocess
from io import StringIO
from typing import Tuple, Optional

from bauh.commons.system import SimpleProcess


def is_installed() -> bool:
    return bool(shutil.which('snap'))


def uninstall_and_stream(app_name: str, root_password: Optional[str]) -> SimpleProcess:
    return SimpleProcess(cmd=('snap', 'remove', app_name),
                         root_password=root_password,
                         lang=None,
                         shell=True)


def install_and_stream(app_name: str, confinement: str, root_password: Optional[str], channel: Optional[str] = None) -> SimpleProcess:

    install_cmd = ['snap', 'install', app_name]  # default

    if confinement == 'classic':
        install_cmd.append('--classic')

    if channel:
        install_cmd.append(f'--channel={channel}')

    return SimpleProcess(install_cmd, root_password=root_password, shell=True, lang=None)


def downgrade_and_stream(app_name: str, root_password: Optional[str]) -> SimpleProcess:
    return SimpleProcess(cmd=('snap', 'revert', app_name),
                         root_password=root_password,
                         shell=True,
                         lang=None)


def refresh_and_stream(app_name: str, root_password: Optional[str], channel: Optional[str] = None) -> SimpleProcess:
    cmd = ['snap', 'refresh', app_name]

    if channel:
        cmd.append(f'--channel={channel}')

    return SimpleProcess(cmd=cmd,
                         root_password=root_password,
                         lang=None,
                         shell=True)


def run(cmd: str):
    subprocess.Popen((f'snap run {cmd}',), shell=True, env={**os.environ})


def is_api_available() -> Tuple[bool, str]:
    output = StringIO()
    for o in SimpleProcess(('snap', 'search'), lang=None).instance.stdout:
        if o:
            output.write(o.decode())

    output.seek(0)
    output = output.read()
    return 'error:' not in output, output
