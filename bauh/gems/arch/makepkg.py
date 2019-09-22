import re

from bauh.api.abstract.handler import ProcessWatcher
from bauh.commons.system import new_subprocess

RE_DEPS_PATTERN = re.compile(r'\n?\s+->\s(.+)\n')
RE_UNKNOWN_GPG_KEY = re.compile(r'\(unknown public key (\w+)\)')


def check(pkgdir: str, watcher: ProcessWatcher) -> dict:
    depcheck = new_subprocess(['makepkg', '-ALcf', '--check', '--noarchive'], cwd=pkgdir)
    res = {}

    output_lines = []

    for o in depcheck.stdout:
        if o:
            line = o.decode().strip()

            if line:
                output_lines.append(line)
                watcher.print(line)

    for s in depcheck.stderr:
        if s:
            line = s.decode()
            if line:
                output_lines.append(line)

                line_strip = line.strip()

                if line_strip:
                    watcher.print(line_strip)

    if output_lines:
        error_str = ''.join(output_lines)

        if 'Missing dependencies' in error_str:
            res['missing_deps'] = RE_DEPS_PATTERN.findall(error_str)

        gpg_keys = RE_UNKNOWN_GPG_KEY.findall(error_str)

        if gpg_keys:
            res['gpg_key'] = gpg_keys[0]

    return res
