import re
from typing import List, Set

from bauh.commons.system import run_cmd, new_subprocess, new_root_subprocess, SystemProcess


def is_enabled() -> bool:
    try:
        new_subprocess(['pacman', '--version'])
        return True
    except FileNotFoundError:
        return False


def get_mirrors(pkgs: Set[str]) -> dict:
    pkgre = '|'.join(pkgs)

    searchres = new_subprocess(['pacman', '-Ss', pkgre]).stdout
    mirrors = {}

    for line in new_subprocess(['grep', '-E', '.+/({}) '.format(pkgre)], stdin=searchres).stdout:
        if line:
            match = line.decode()
            for p in pkgs:
                if p in match:
                    mirrors[p] = match.split('/')[0]

    return mirrors


def is_available_from_mirrors(pkg_name: str) -> bool:
    return bool(run_cmd('pacman -Ss ' + pkg_name))


def get_info(pkg_name) -> str:
    return run_cmd('pacman -Qi ' + pkg_name)


def get_info_list(pkg_name: str) -> List[tuple]:
    info = get_info(pkg_name)
    if info:
        return re.findall(r'(\w+\s?\w+)\s+:\s+(.+(\n\s+.+)*)', info)


def get_info_dict(pkg_name: str) -> dict:
    info_list = get_info_list(pkg_name)

    if info_list:
        info_dict = {}
        for info_data in info_list:
            attr = info_data[0].lower()
            info_dict[attr] = info_data[1] if '\n' not in info_data[1] else ' '.join([l.strip() for l in info_data[1].split('\n')])

            if info_dict[attr] == 'None':
                info_dict[attr] = None

        return info_dict


def list_installed() -> Set[str]:
    return {out.decode().strip() for out in new_subprocess(['pacman', '-Qq']).stdout if out}


def list_and_map_installed() -> dict:  # returns a dict with with package names as keys and versions as values
    installed = new_subprocess(['pacman', '-Qq']).stdout  # retrieving all installed package names
    allinfo = new_subprocess(['pacman', '-Qi'], stdin=installed).stdout  # retrieving all installed packages info

    pkgs, current_pkg = {'mirrors': {}, 'not_signed': {}}, {}
    for out in new_subprocess(['grep', '-E', '(Name|Description|Version|Validated By)'], stdin=allinfo).stdout:  # filtering only the Name and Validated By fields:
        if out:
            line = out.decode()

            if line.startswith('Name'):
                current_pkg['name'] = line.split(':')[1].strip()
            elif line.startswith('Version'):
                version = line.split(':')
                current_pkg['version'] = version[len(version) - 1].strip()
            elif line.startswith('Description'):
                current_pkg['description'] = line.split(':')[1].strip()
            elif line.startswith('Validated'):

                if line.split(':')[1].strip().lower() == 'none':
                    pkgs['not_signed'][current_pkg['name']] = {'version': current_pkg['version'], 'description': current_pkg['description']}

                current_pkg = {}

    return pkgs


def install_as_process(pkgpath: str, root_password: str, aur: bool, pkgdir: str = '.') -> SystemProcess:

    if aur:
        cmd = ['pacman', '-U', pkgpath, '--noconfirm']  # pkgpath = install file path
    else:
        cmd = ['pacman', '-S', pkgpath, '--noconfirm']  # pkgpath = pkgname

    return SystemProcess(new_root_subprocess(cmd, root_password, cwd=pkgdir))


def list_desktop_entries(pkgnames: Set[str]) -> List[str]:
    if pkgnames:
        installed_files = new_subprocess(['pacman', '-Qlq', *pkgnames]).stdout

        desktop_files = []
        for out in new_subprocess(['grep', '-E', '.desktop'], stdin=installed_files).stdout:
            if out:
                desktop_files.append(out.decode().strip())

        return desktop_files


def list_icon_paths(pkgnames: Set[str]) -> List[str]:
    installed_files = new_subprocess(['pacman', '-Qlq', *pkgnames]).stdout

    icon_files = []
    for out in new_subprocess(['grep', '-E', '.(png|svg|jpeg)'], stdin=installed_files).stdout:
        if out:
            icon_files.append(out.decode().strip())

    return icon_files


def list_bin_paths(pkgnames: Set[str]) -> List[str]:
    installed_files = new_subprocess(['pacman', '-Qlq', *pkgnames]).stdout

    bin_paths = []
    for out in new_subprocess(['grep', '-E', '^/usr/bin/.+'], stdin=installed_files).stdout:
        if out:
            bin_paths.append(out.decode().strip())

    return bin_paths
