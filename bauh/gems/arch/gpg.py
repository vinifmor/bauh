from bauh.commons.system import SystemProcess, new_subprocess


def receive_key(key: str) -> SystemProcess:
    return SystemProcess(new_subprocess(['gpg', '--recv-key', key]), check_error_output=False)
