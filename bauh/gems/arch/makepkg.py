import os
import re
from typing import Tuple, Optional, Set

from bauh.commons.system import SimpleProcess, ProcessHandler, run_cmd
from bauh.gems.arch import CUSTOM_MAKEPKG_FILE

RE_DEPS_PATTERN = re.compile(r'\n?\s+->\s(.+)\n')
RE_UNKNOWN_GPG_KEY = re.compile(r'\(unknown public key (\w+)\)')


def gen_srcinfo(build_dir: str, custom_pkgbuild_path: Optional[str] = None) -> str:
    return run_cmd('makepkg --printsrcinfo{}'.format(' -p {}'.format(custom_pkgbuild_path) if custom_pkgbuild_path else ''),
                   cwd=build_dir)


def check(pkgdir: str, optimize: bool, missing_deps: bool, handler: ProcessHandler, custom_pkgbuild: Optional[str] = None) -> dict:
    res = {}

    cmd = ['makepkg', '-ALcfm', '--check', '--noarchive', '--nobuild', '--noprepare']

    if not missing_deps:
        cmd.append('--nodeps')

    if custom_pkgbuild:
        cmd.append('-p')
        cmd.append(custom_pkgbuild)

    if optimize:
        if os.path.exists(CUSTOM_MAKEPKG_FILE):
            handler.watcher.print('Using custom makepkg.conf -> {}'.format(CUSTOM_MAKEPKG_FILE))
            cmd.append('--config={}'.format(CUSTOM_MAKEPKG_FILE))
        else:
            handler.watcher.print('Custom optimized makepkg.conf ( {} ) not found'.format(CUSTOM_MAKEPKG_FILE))

    success, output = handler.handle_simple(SimpleProcess(cmd, cwd=pkgdir, shell=True))

    if missing_deps and 'Missing dependencies' in output:
        res['missing_deps'] = RE_DEPS_PATTERN.findall(output)

    gpg_keys = RE_UNKNOWN_GPG_KEY.findall(output)

    if gpg_keys:
        res['gpg_key'] = gpg_keys[0]

    if 'One or more files did not pass the validity check' in output:
        res['validity_check'] = True

    return res


def make(pkgdir: str, optimize: bool, handler: ProcessHandler, custom_pkgbuild: Optional[str] = None) -> Tuple[bool, str]:
    cmd = ['makepkg', '-ALcsmf', '--skipchecksums']

    if custom_pkgbuild:
        cmd.append('-p')
        cmd.append(custom_pkgbuild)

    if optimize:
        if os.path.exists(CUSTOM_MAKEPKG_FILE):
            handler.watcher.print('Using custom makepkg.conf -> {}'.format(CUSTOM_MAKEPKG_FILE))
            cmd.append('--config={}'.format(CUSTOM_MAKEPKG_FILE))
        else:
            handler.watcher.print('Custom optimized makepkg.conf ( {} ) not found'.format(CUSTOM_MAKEPKG_FILE))

    return handler.handle_simple(SimpleProcess(cmd, cwd=pkgdir, shell=True))


def update_srcinfo(project_dir: str) -> bool:
    updated_src = run_cmd('makepkg --printsrcinfo', cwd=project_dir)

    if updated_src:
        with open('{}/.SRCINFO'.format(project_dir), 'w+') as f:
            f.write(updated_src)
        return True

    return False


def list_output_files(project_dir: str, custom_pkgbuild_path: Optional[str] = None) -> Set[str]:
    output = run_cmd(cmd='makepkg --packagelist{}'.format(' -p {}'.format(custom_pkgbuild_path) if custom_pkgbuild_path else ''),
                     print_error=False,
                     cwd=project_dir)

    if output:
        return {p.strip() for p in output.split('\n') if p}

    return set()
