from typing import Optional

from bauh.commons.system import SystemProcess, new_subprocess


def receive_key(key: str, server: Optional[str] = None) -> SystemProcess:
    cmd = ['gpg']

    if server:
        cmd.extend(['--keyserver', server])

    cmd.extend(['--recv-key', key])

    return SystemProcess(new_subprocess(cmd), check_error_output=False)
