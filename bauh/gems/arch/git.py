import shutil
from io import StringIO
from logging import Logger
from typing import List, Tuple, Optional

from bauh.commons import system
from bauh.commons.system import SimpleProcess


def is_installed() -> bool:
    return bool(shutil.which('git'))


def list_commits(proj_dir: str, limit: int = -1, logger: Optional[Logger] = None) -> Optional[List[Tuple[str, int]]]:
    if limit == 0:
        return

    cmd = StringIO()
    cmd.write('git log --format="%H %ct"')

    if limit > 0:
        cmd.write(f' -{limit}')

    code, output = system.execute(cmd.getvalue(), cwd=proj_dir, shell=True)

    if code == 0 and output:
        commits = []
        for line in output.split('\n'):
            line_strip = line.strip()

            if line_strip:
                line_split = line_strip.split(' ', 1)

                if len(line_split) == 2:
                    commit_sha = line_split[0].strip()
                    try:
                        commit_date = int(line_split[1].strip())
                    except ValueError:
                        commit_date = None

                        if logger:
                            logger.error(f"Could not parse commit date {line_split[1]}")

                    commits.append((commit_sha, commit_date))

        return commits


def clone(url: str, target_dir: Optional[str], depth: int = -1, custom_user: Optional[str] = None) -> SimpleProcess:
    cmd = ['git', 'clone', url]

    if depth > 0:
        cmd.append(f'--depth={depth}')

    if target_dir:
        cmd.append(target_dir)

    return SimpleProcess(cmd=cmd, custom_user=custom_user)
