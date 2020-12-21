from datetime import datetime
from typing import List, Tuple, Optional

from bauh.commons import system
from bauh.commons.system import new_subprocess, SimpleProcess


def is_installed() -> bool:
    code, _ = system.execute(cmd='which git', output=False)
    return code == 0


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


def get_current_commit(repo_path: str) -> Optional[str]:
    code, output = system.execute(cmd='git log -1 --format=%H', shell=True, cwd=repo_path)

    if code == 0:
        for line in output.strip().split('\n'):
            line_strip = line.strip()

            if line_strip:
                return line_strip


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


def clone_as_process(url: str, cwd: Optional[str], depth: int = -1) -> SimpleProcess:
    cmd = ['git', 'clone', url]

    if depth > 0:
        cmd.append('--depth={}'.format(depth))

    return SimpleProcess(cmd=cmd, cwd=cwd)
