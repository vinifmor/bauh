import os
from pathlib import Path
from typing import Set

from bauh.commons import system
from bauh.gems.arch import IGNORED_REBUILD_CHECK_FILE


def is_installed() -> bool:
    return system.execute(cmd='which checkrebuild', output=False)[0] == 0


def list_required_rebuild() -> Set[str]:
    code, output = system.execute(cmd='checkrebuild', shell=True, stdin=False)

    required = set()
    if code == 0 and output:
        for line in output.split('\n'):
            line_strip = line.strip()

            if line_strip:
                line_split = line_strip.split('\t')

                if len(line_split) > 1:
                    required.add(line_split[1])

    return required


def list_ignored() -> Set[str]:
    if os.path.isfile(IGNORED_REBUILD_CHECK_FILE):
        with open(IGNORED_REBUILD_CHECK_FILE) as f:
            ignored_str = f.read()

        return {p.strip() for p in ignored_str.split('\n') if p}
    else:
        return set()


def add_as_ignored(pkgname: str):
    ignored = list_ignored()
    ignored.add(pkgname)

    Path(os.path.dirname(IGNORED_REBUILD_CHECK_FILE)).mkdir(parents=True, exist_ok=True)

    with open(IGNORED_REBUILD_CHECK_FILE, 'w+') as f:
        for p in ignored:
            f.write('{}\n'.format(p))


def remove_from_ignored(pkgname: str):
    ignored = list_ignored()

    if ignored is None or pkgname not in ignored:
        return

    ignored.remove(pkgname)

    Path(os.path.dirname(IGNORED_REBUILD_CHECK_FILE)).mkdir(parents=True, exist_ok=True)

    if ignored:
        with open(IGNORED_REBUILD_CHECK_FILE, 'w+') as f:
            for p in ignored:
                f.write('{}\n'.format(p))
    else:
        os.remove(IGNORED_REBUILD_CHECK_FILE)
