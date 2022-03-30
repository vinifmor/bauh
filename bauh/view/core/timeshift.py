import re
import shutil
from typing import Optional, Generator

from bauh import __app_name__
from bauh.commons.system import SimpleProcess, new_root_subprocess

RE_SNAPSHOTS = re.compile(r'\d+\s+>\s+([\w\-_]+)\s+.+<{}>'.format(__app_name__))


def is_available() -> bool:
    return bool(shutil.which('timeshift'))


def delete_all_snapshots(root_password: Optional[str]) -> SimpleProcess:
    return SimpleProcess(('timeshift', '--delete-all', '--scripted'), root_password=root_password)


def delete(snapshot_name: str, root_password: Optional[str]) -> SimpleProcess:
    return SimpleProcess(('timeshift', '--delete', '--snapshot', snapshot_name),
                         shell=True, root_password=root_password)


def create_snapshot(root_password: Optional[str], mode: str) -> SimpleProcess:
    return SimpleProcess(('timeshift', '--create', '--scripted', f'--{mode}', '--comments', f'<{__app_name__}>'),
                         root_password=root_password)


def read_created_snapshots(root_password: Optional[str]) -> Generator[str, None, None]:
    proc = new_root_subprocess(cmd=('timeshift', '--list'), root_password=root_password, shell=True)
    proc.wait()

    if proc.returncode == 0:
        output = '\n'.join((o.decode() for o in proc.stdout))

        if output:
            for name in RE_SNAPSHOTS.findall(output):
                yield name
