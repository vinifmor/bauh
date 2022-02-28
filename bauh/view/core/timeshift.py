import shutil
from typing import Optional

from bauh.commons.system import SimpleProcess


def is_available() -> bool:
    return bool(shutil.which('timeshift'))


def delete_all_snapshots(root_password: Optional[str]) -> SimpleProcess:
    return SimpleProcess(['timeshift', '--delete-all', '--scripted'], root_password=root_password)


def create_snapshot(root_password: Optional[str], mode: str) -> SimpleProcess:
    return SimpleProcess(['timeshift', '--create', '--scripted', '--{}'.format(mode)], root_password=root_password)
