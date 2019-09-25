from datetime import datetime
from typing import List

from bauh.commons.system import new_subprocess


def is_enabled() -> bool:
    try:
        new_subprocess(['git', '--version'])
        return True
    except FileNotFoundError:
        return False


def list_commits(proj_dir:str) -> List[dict]:
    logs = new_subprocess(['git', 'log', '--date=iso'], cwd=proj_dir).stdout

    commits, commit = [], {}
    for out in new_subprocess(['grep', '-E', 'commit|Date:'], stdin=logs).stdout:
        if out:
            line = out.decode()
            if line.startswith('commit'):
                commit['commit'] = line.split(' ')[1].strip()
            elif line.startswith('Date'):
                commit['date'] = datetime.fromisoformat(line.split(':')[1].strip())
                commits.append(commit)
                commit = {}

    return commits
