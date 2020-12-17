from datetime import datetime
from typing import List, Tuple, Optional

from bauh.commons import system
from bauh.commons.system import new_subprocess


def is_installed() -> bool:
    try:
        new_subprocess(['git', '--version'])
        return True
    except FileNotFoundError:
        return False


def list_commits(proj_dir: str) -> List[dict]:
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


def log_shas_and_timestamps(repo_path: str) -> Optional[List[Tuple[str, int]]]:
    code, output = system.execute(cmd='git log --format="%H %at"', shell=True, cwd=repo_path)

    if code == 0:
        logs = []
        for line in output.strip().split('\n'):
            line_strip = line.strip()

            if line_strip:
                line_split = line_strip.split(' ')
                logs.append((line_split[0].strip(), int(line_split[1].strip())))

        return logs
