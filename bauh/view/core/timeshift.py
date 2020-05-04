from bauh.commons.system import run_cmd, SimpleProcess


def is_available() -> bool:
    return bool(run_cmd('which timeshift', print_error=False))


def delete_all_snapshots(root_password: str) -> SimpleProcess:
    return SimpleProcess(['timeshift', '--delete-all', '--scripted'], root_password=root_password)


def create_snapshot(root_password: str, mode: str) -> SimpleProcess:
    return SimpleProcess(['timeshift', '--create', '--scripted', '--{}'.format(mode)], root_password=root_password)
