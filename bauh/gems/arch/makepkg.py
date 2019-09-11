import re
from typing import List

from bauh.api.abstract.handler import ProcessWatcher
from bauh.commons.system import new_subprocess

RE_DEPS_PATTERN = re.compile(r'\n?\s+->\s(.+)\n')


def check_missing_deps(pkgdir: str, watcher: ProcessWatcher) -> List[str]:
    depcheck = new_subprocess(['makepkg', '--check'], cwd=pkgdir)

    for o in depcheck.stdout:
        if o:
            watcher.print(o.decode())

    error_lines = []
    for s in depcheck.stderr:
        if s:
            line = s.decode()
            print(line)
            error_lines.append(line)

    if error_lines:
        error_str = ''.join(error_lines)

        if 'Missing dependencies' in error_str:
            return RE_DEPS_PATTERN.findall(error_str)
