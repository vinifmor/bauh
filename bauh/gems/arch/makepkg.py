import os
import re
from typing import Optional, Set, Tuple

from bauh.commons import system
from bauh.commons.system import ProcessHandler, SimpleProcess
from bauh.gems.arch import CUSTOM_MAKEPKG_FILE
from bauh.gems.arch.proc_util import write_as_user

RE_UNKNOWN_GPG_KEY = re.compile(r'\(unknown public key (\w+)\)')
RE_DEPS_PATTERN = re.compile(r'\n?\s+->\s(.+)\n')


def gen_srcinfo(build_dir: str, custom_pkgbuild_path: Optional[str] = None, custom_user: Optional[str] = None) -> str:
    cmd = f"makepkg --printsrcinfo{' -p {}'.format(custom_pkgbuild_path) if custom_pkgbuild_path else ''}"
    return system.run_cmd(cmd, cwd=build_dir, custom_user=custom_user)


def update_srcinfo(project_dir: str, custom_user: Optional[str] = None) -> bool:
    updated_src = system.run_cmd('makepkg --printsrcinfo', cwd=project_dir, custom_user=custom_user)

    if updated_src:
        return write_as_user(content=updated_src, file_path=f"{project_dir}/.SRCINFO", user=custom_user)

    return False


def list_output_files(project_dir: str, custom_pkgbuild_path: Optional[str] = None,
                      custom_user: Optional[str] = None) -> Set[str]:
    cmd = f"makepkg --packagelist{' -p {}'.format(custom_pkgbuild_path) if custom_pkgbuild_path else ''}"
    output = system.run_cmd(cmd=cmd, print_error=False, cwd=project_dir, custom_user=custom_user)

    if output:
        return {p.strip() for p in output.split('\n') if p}

    return set()


def build(pkgdir: str, optimize: bool, handler: ProcessHandler, custom_pkgbuild: Optional[str] = None,
          custom_user: Optional[str] = None) -> Tuple[bool, str]:
    cmd = ['makepkg', '-ALcsmf', '--skipchecksums', '--nodeps']

    if custom_pkgbuild:
        cmd.append('-p')
        cmd.append(custom_pkgbuild)

    if optimize:
        if os.path.exists(CUSTOM_MAKEPKG_FILE):
            handler.watcher.print(f'Using custom makepkg.conf -> {CUSTOM_MAKEPKG_FILE}')
            cmd.append(f'--config={CUSTOM_MAKEPKG_FILE}')
        else:
            handler.watcher.print(f'Custom optimized makepkg.conf ({CUSTOM_MAKEPKG_FILE}) not found')

    return handler.handle_simple(SimpleProcess(cmd, cwd=pkgdir, shell=True, custom_user=custom_user))


def check(project_dir: str, optimize: bool, missing_deps: bool, handler: ProcessHandler,
          custom_pkgbuild: Optional[str] = None, custom_user: Optional[str] = None) -> dict:
    res = {}

    cmd = ['makepkg', '-ALcfm', '--check', '--noarchive', '--nobuild', '--noprepare']

    if not missing_deps:
        cmd.append('--nodeps')

    if custom_pkgbuild:
        cmd.append('-p')
        cmd.append(custom_pkgbuild)

    if optimize:
        if os.path.exists(CUSTOM_MAKEPKG_FILE):
            handler.watcher.print(f'Using custom makepkg.conf -> {CUSTOM_MAKEPKG_FILE}')
            cmd.append(f'--config={CUSTOM_MAKEPKG_FILE}')
        else:
            handler.watcher.print(f'Custom optimized makepkg.conf ({CUSTOM_MAKEPKG_FILE}) not found')

    success, output = handler.handle_simple(SimpleProcess(cmd, cwd=project_dir, shell=True, custom_user=custom_user))

    if missing_deps and 'Missing dependencies' in output:
        res['missing_deps'] = RE_DEPS_PATTERN.findall(output)

    gpg_keys = RE_UNKNOWN_GPG_KEY.findall(output)

    if gpg_keys:
        res['gpg_key'] = gpg_keys[0]

    if 'One or more files did not pass the validity check' in output:
        res['validity_check'] = True

    return res
