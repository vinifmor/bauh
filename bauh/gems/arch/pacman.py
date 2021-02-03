import logging
import os
import re
from threading import Thread
from typing import List, Set, Tuple, Dict, Iterable, Optional

from colorama import Fore

from bauh.commons import system
from bauh.commons.system import run_cmd, new_subprocess, new_root_subprocess, SystemProcess, SimpleProcess
from bauh.commons.util import size_to_byte
from bauh.gems.arch.exceptions import PackageNotFoundException, PackageInHoldException

RE_DEPS = re.compile(r'[\w\-_]+:[\s\w_\-\.]+\s+\[\w+\]')
RE_OPTDEPS = re.compile(r'[\w\._\-]+\s*:')
RE_DEP_NOTFOUND = re.compile(r'error:.+\'(.+)\'')
RE_DEP_OPERATORS = re.compile(r'[<>=]')
RE_INSTALLED_FIELDS = re.compile(r'(Name|Description|Version|Install Date|Validated By)\s*:\s*(.+)')
RE_INSTALLED_SIZE = re.compile(r'Installed Size\s*:\s*([0-9,\.]+)\s(\w+)\n?', re.IGNORECASE)
RE_DOWNLOAD_SIZE = re.compile(r'Download Size\s*:\s*([0-9,\.]+)\s(\w+)\n?', re.IGNORECASE)
RE_UPDATE_REQUIRED_FIELDS = re.compile(r'(\bProvides\b|\bInstalled Size\b|\bConflicts With\b)\s*:\s(.+)\n')
RE_REMOVE_TRANSITIVE_DEPS = re.compile(r'removing\s([\w\-_]+)\s.+required\sby\s([\w\-_]+)\n?')
RE_AVAILABLE_MIRRORS = re.compile(r'.+\s+OK\s+.+\s+(\d+:\d+)\s+.+(http.+)')
RE_PACMAN_SYNC_FIRST = re.compile(r'SyncFirst\s*=\s*(.+)')
RE_DESKTOP_FILES = re.compile(r'\n?([\w\-_]+)\s+(/usr/share/.+\.desktop)')


def is_available() -> bool:
    res = run_cmd('which pacman', print_error=False)
    return res and not res.strip().startswith('which ')


def get_repositories(pkgs: Iterable[str]) -> dict:
    pkgre = '|'.join(pkgs).replace('+', r'\+').replace('.', r'\.')

    searchres = new_subprocess(['pacman', '-Ss', pkgre]).stdout
    repositories = {}

    for line in new_subprocess(['grep', '-E', '.+/({}) '.format(pkgre)], stdin=searchres).stdout:
        if line:
            match = line.decode()
            for p in pkgs:
                if p in match:
                    repositories[p] = match.split('/')[0]

    not_found = {pkg for pkg in pkgs if pkg and pkg not in repositories}

    if not_found:  # if there are some packages not found, try to find via the single method:
        for dep in not_found:
            repo_data = guess_repository(dep)

            if repo_data:
                repositories[repo_data[0]] = repo_data[1]

    return repositories


def is_available_in_repositories(pkg_name: str) -> bool:
    return bool(run_cmd('pacman -Ss ' + pkg_name))


def get_info(pkg_name, remote: bool = False) -> str:
    return run_cmd('pacman -{}i {}'.format('Q' if not remote else 'S', pkg_name), print_error=False)


def get_info_list(pkg_name: str, remote: bool = False) -> List[tuple]:
    info = get_info(pkg_name, remote)
    if info:
        return re.findall(r'(\w+\s?\w+)\s*:\s*(.+(\n\s+.+)*)', info)


def get_info_dict(pkg_name: str, remote: bool = False) -> Optional[dict]:
    list_attrs = {'depends on', 'required by', 'conflicts with'}
    info_list = get_info_list(pkg_name, remote)

    if info_list:
        info_dict = {}
        for info_data in info_list:
            attr = info_data[0].lower().strip()
            info_dict[attr] = info_data[1]

            if info_dict[attr] == 'None':
                info_dict[attr] = None

            if attr == 'optional deps' and info_dict[attr]:
                info_dict[attr] = info_dict[attr].split('\n')
            elif attr in list_attrs and info_dict[attr]:
                info_dict[attr] = [d.strip() for d in info_dict[attr].split(' ') if d]

        return info_dict


def check_installed(pkg: str) -> bool:
    res = run_cmd('pacman -Qq ' + pkg, print_error=False)
    return bool(res)


def _fill_ignored(res: dict):
    res['pkgs'] = list_ignored_packages()


def map_installed(names: Iterable[str] = None) -> dict:  # returns a dict with with package names as keys and versions as values
    ignored = {}
    thread_ignored = Thread(target=_fill_ignored, args=(ignored,), daemon=True)
    thread_ignored.start()

    allinfo = run_cmd('pacman -Qi{}'.format(' ' + ' '.join(names) if names else ''), print_error=False)

    pkgs = {'signed': {}, 'not_signed': {}}
    current_pkg = {}

    if allinfo:
        for idx, field_tuple in enumerate(RE_INSTALLED_FIELDS.findall(allinfo)):
            if field_tuple[0].startswith('N'):
                current_pkg['name'] = field_tuple[1].strip()
            elif field_tuple[0].startswith('Ve'):
                current_pkg['version'] = field_tuple[1].strip()
            elif field_tuple[0].startswith('D'):
                current_pkg['description'] = field_tuple[1].strip()
            elif field_tuple[0].startswith('I'):
                current_pkg['install_date'] = field_tuple[1].strip()
            elif field_tuple[0].startswith('Va'):
                if field_tuple[1].strip().lower() == 'none':
                    pkgs['not_signed'][current_pkg['name']] = current_pkg
                    del current_pkg['name']
                else:
                    pkgs['signed'][current_pkg['name']] = current_pkg
                    del current_pkg['name']

                current_pkg = {}

    if pkgs['signed'] or pkgs['not_signed']:
        thread_ignored.join()

        if ignored['pkgs']:
            to_del = set()

            for key in ('signed', 'not_signed'):
                if pkgs.get(key):
                    for pkg in pkgs[key].keys():
                        if pkg in ignored['pkgs']:
                            to_del.add(pkg)

                for pkg in to_del:
                    del pkgs[key][pkg]
    return pkgs


def install_as_process(pkgpaths: Iterable[str], root_password: str, file: bool, pkgdir: str = '.',
                       overwrite_conflicting_files: bool = False, simulate: bool = False) -> SimpleProcess:
    cmd = ['pacman', '-U'] if file else ['pacman', '-S']
    cmd.extend(pkgpaths)

    if not simulate:
        cmd.append('--noconfirm')
        cmd.append('-dd')

    if overwrite_conflicting_files:
        cmd.append('--overwrite=*')

    return SimpleProcess(cmd=cmd,
                         root_password=root_password,
                         cwd=pkgdir,
                         error_phrases={"error: failed to prepare transaction", 'error: failed to commit transaction', 'error: target not found'},
                         shell=True)


def map_desktop_files(*pkgnames) -> Dict[str, List[str]]:
    res = {}

    if pkgnames:
        output = run_cmd('pacman -Ql {}'.format(' '.join(pkgnames)), print_error=False)

        if output:
            for match in RE_DESKTOP_FILES.findall(output):
                pkgfiles = res.get(match[0], [])
                res[match[0]] = pkgfiles
                pkgfiles.append(match[1])

    return res


def list_installed_files(pkgname: str) -> List[str]:
    installed_files = run_cmd('pacman -Qlq {}'.format(pkgname), print_error=False)

    paths = []

    if installed_files:
        for f in installed_files.split('\n'):
            if f:
                f_strip = f.strip()

                if f_strip and not f_strip.endswith('/'):
                    paths.append(f_strip)

    return paths


def verify_pgp_key(key: str) -> bool:
    list_key = new_subprocess(['pacman-key', '-l']).stdout

    for out in new_subprocess(['grep', " " + key], stdin=list_key).stdout:
        if out:
            line = out.decode().strip()
            if line and key in line:
                return True

    return False


def receive_key(key: str, root_password: str) -> SystemProcess:
    return SystemProcess(new_root_subprocess(['pacman-key', '-r', key], root_password=root_password), check_error_output=False)


def sign_key(key: str, root_password: str) -> SystemProcess:
    return SystemProcess(new_root_subprocess(['pacman-key', '--lsign-key', key], root_password=root_password), check_error_output=False)


def list_ignored_packages(config_path: str = '/etc/pacman.conf') -> Set[str]:
    pacman_conf = new_subprocess(['cat', config_path])

    ignored = set()
    grep = new_subprocess(['grep', '-Eo', r'\s*#*\s*ignorepkg\s*=\s*.+'], stdin=pacman_conf.stdout)
    for o in grep.stdout:
        if o:
            line = o.decode().strip()

            if not line.startswith('#'):
                ignored.add(line.split('=')[1].strip())

    pacman_conf.terminate()
    grep.terminate()
    return ignored


def check_missing(names: Set[str]) -> Set[str]:
    installed = new_subprocess(['pacman', '-Qq', *names])

    not_installed = set()

    for o in installed.stderr:
        if o:
            err_line = o.decode()

            if err_line:
                not_found = [n for n in RE_DEP_NOTFOUND.findall(err_line) if n]

                if not_found:
                    not_installed.update(not_found)

    return not_installed


def read_repository_from_info(name: str) -> str:
    info = new_subprocess(['pacman', '-Si', name])

    not_found = False
    for o in info.stderr:
        if o:
            err_line = o.decode()
            if RE_DEP_NOTFOUND.findall(err_line):
                not_found = True

    if not_found:
        return

    repository = None

    for o in new_subprocess(['grep', '-Po', "Repository\s+:\s+\K.+"], stdin=info.stdout).stdout:
        if o:
            line = o.decode().strip()

            if line:
                repository = line

    return repository


def guess_repository(name: str) -> Tuple[str, str]:
    if not name:
        raise Exception("'name' cannot be None or blank")

    only_name = RE_DEP_OPERATORS.split(name)[0]
    res = run_cmd('pacman -Ss {}'.format(only_name))

    if res:
        lines = res.split('\n')

        if lines:
            for line in lines:
                if line and not line.startswith(' '):
                    data = line.split('/')
                    line_name, line_repo = data[1].split(' ')[0], data[0]

                    provided = read_provides(line_name)

                    if provided:
                        found = {p for p in provided if only_name == RE_DEP_OPERATORS.split(p)[0]}

                        if found:
                            return line_name, line_repo


def read_provides(name: str) -> Set[str]:
    dep_info = new_subprocess(['pacman', '-Si', name])

    not_found = False

    for o in dep_info.stderr:
        if o:
            err_line = o.decode()

            if err_line:
                if RE_DEP_NOTFOUND.findall(err_line):
                    not_found = True

    if not_found:
        raise PackageNotFoundException(name)

    provides = None

    for out in new_subprocess(['grep', '-Po', 'Provides\s+:\s\K(.+)'], stdin=dep_info.stdout).stdout:
        if out:
            provided_names = [p.strip() for p in out.decode().strip().split(' ') if p]

            if provided_names[0].lower() == 'none':
                provides = {name}
            else:
                provides = {name, *provided_names}

    return provides


def read_dependencies(name: str) -> Set[str]:
    dep_info = new_subprocess(['pacman', '-Si', name])

    not_found = False

    for o in dep_info.stderr:
        if o:
            err_line = o.decode()

            if err_line:
                if RE_DEP_NOTFOUND.findall(err_line):
                    not_found = True

    if not_found:
        raise PackageNotFoundException(name)

    depends_on = set()
    for out in new_subprocess(['grep', '-Po', 'Depends\s+On\s+:\s\K(.+)'], stdin=dep_info.stdout).stdout:
        if out:
            line = out.decode().strip()

            if line:
                depends_on.update([d for d in line.split(' ') if d and d.lower() != 'none'])

    return depends_on


def sync_databases(root_password: str, force: bool = False) -> SimpleProcess:
    return SimpleProcess(cmd=['pacman', '-Sy{}'.format('y' if force else '')],
                         root_password=root_password)


def get_version_for_not_installed(pkgname: str) -> str:
    output = run_cmd('pacman -Ss {}'.format(pkgname), print_error=False)

    if output:
        return output.split('\n')[0].split(' ')[1].strip()


def map_repositories(pkgnames: Iterable[str] = None) -> Dict[str, str]:
    info = run_cmd('pacman -Si {}'.format(' '.join(pkgnames) if pkgnames else ''), print_error=False, ignore_return_code=True)
    if info:
        repos = re.findall(r'(Name|Repository)\s*:\s*(.+)', info)

        if repos:
            return {repos[idx+1][1].strip(): repo_data[1].strip() for idx, repo_data in enumerate(repos) if idx % 2 == 0}

    return {}


def list_repository_updates() -> Dict[str, str]:
    output = run_cmd('pacman -Qu')
    res = {}
    if output:
        for line in output.split('\n'):
            if line:
                line_split = line.split(' ')
                res[line_split[0]] = line_split[-1]
    return res


def map_sorting_data(pkgnames: List[str]) -> Dict[str, dict]:
    allinfo = new_subprocess(['pacman', '-Qi', *pkgnames]).stdout

    pkgs, current_pkg = {}, {}
    mapped_attrs = 0
    for out in new_subprocess(["grep", "-Po", "(Name|Provides|Depends On)\s*:\s*\K(.+)"], stdin=allinfo).stdout:
        if out:
            line = out.decode().strip()

            if line:
                if mapped_attrs == 0:
                    current_pkg['name'] = line
                elif mapped_attrs == 1:
                    provides = set() if line == 'None' else set(line.split(' '))
                    provides.add(current_pkg['name'])
                    current_pkg['provides'] = provides
                elif mapped_attrs == 2:
                    current_pkg['depends'] = line.split(':')[1].strip()
                    pkgs[current_pkg['name']] = current_pkg
                    del current_pkg['name']

                    mapped_attrs = 0
                    current_pkg = {}
    return pkgs


def get_build_date(pkgname: str) -> str:
    output = run_cmd('pacman -Qi {}'.format(pkgname))

    if output:
        bdate_line = [l for l in output.split('\n') if l.startswith('Build Date')]

        if bdate_line:
            return ':'.join(bdate_line[0].split(':')[1:]).strip()


def search(words: str) -> Dict[str, dict]:
    output = run_cmd('pacman -Ss ' + words, print_error=False)

    found = {}
    if output:
        current = {}
        for l in output.split('\n'):
            if l:
                if l.startswith(' '):
                    current['description'] = l.strip()
                    found[current['name']] = current
                    del current['name']
                    current = None
                else:
                    if current is None:
                        current = {}

                    repo_split = l.split('/')
                    current['repository'] = repo_split[0]

                    data_split = repo_split[1].split(' ')
                    current['name'] = data_split[0]

                    current['version'] = data_split[1]
    return found


def get_databases() -> Set[str]:
    with open('/etc/pacman.conf') as f:
        conf_str = f.read()

    return {db for db in re.findall(r'[\n|\s]+\[(\w+)\]', conf_str) if db != 'options'}


def can_refresh_mirrors() -> bool:
    output = run_cmd('which pacman-mirrors', print_error=False)
    return True if output else False


def refresh_mirrors(root_password: str) -> SimpleProcess:
    return SimpleProcess(cmd=['pacman-mirrors', '-g'], root_password=root_password)


def update_mirrors(root_password: str, countries: List[str]) -> SimpleProcess:
    return SimpleProcess(cmd=['pacman-mirrors', '-c', ','.join(countries)], root_password=root_password)


def sort_fastest_mirrors(root_password: str, limit: int) -> SimpleProcess:
    cmd = ['pacman-mirrors', '--fasttrack']

    if limit > 0:
        cmd.append(str(limit))

    return SimpleProcess(cmd=cmd, root_password=root_password)


def list_mirror_countries() -> List[str]:
    output = run_cmd('pacman-mirrors -l')

    if output:
        return [c for c in output.split('\n') if c]


def get_current_mirror_countries() -> List[str]:
    output = run_cmd('pacman-mirrors -lc').strip()
    return ['all'] if not output else [c for c in output.split('\n') if c]


def is_mirrors_available() -> bool:
    code, _ = system.execute(cmd='which pacman-mirrors', output=False)
    return code == 0


def map_update_sizes(pkgs: List[str]) -> Dict[str, int]:  # bytes:
    output = run_cmd('pacman -Si {}'.format(' '.join(pkgs)))

    if output:
        return {pkgs[idx]: size_to_byte(float(size[0]), size[1]) for idx, size in enumerate(RE_INSTALLED_SIZE.findall(output))}

    return {}


def map_download_sizes(pkgs: List[str]) -> Dict[str, int]:  # bytes:
    output = run_cmd('pacman -Si {}'.format(' '.join(pkgs)))

    if output:
        return {pkgs[idx]: size_to_byte(float(size[0]), size[1]) for idx, size in enumerate(RE_DOWNLOAD_SIZE.findall(output))}

    return {}


def get_installed_size(pkgs: List[str]) -> Dict[str, int]:  # bytes
    output = run_cmd('pacman -Qi {}'.format(' '.join(pkgs)))

    if output:
        return {pkgs[idx]: size_to_byte(float(size[0]), size[1]) for idx, size in enumerate(RE_INSTALLED_SIZE.findall(output))}

    return {}


def upgrade_system(root_password: str) -> SimpleProcess:
    return SimpleProcess(cmd=['pacman', '-Syyu', '--noconfirm'], root_password=root_password)


def fill_provided_map(key: str, val: str, output: dict):
    current_val = output.get(key)

    if current_val is None:
        output[key] = {val}
    else:
        current_val.add(val)


def map_provided(remote: bool = False, pkgs: Iterable[str] = None) -> Dict[str, Set[str]]:
    output = run_cmd('pacman -{}i {}'.format('S' if remote else 'Q', ' '.join(pkgs) if pkgs else ''))

    if output:
        provided_map = {}
        latest_name, latest_version, provided = None, None, False

        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()
                    val = line[field_sep_idx + 1:].strip()

                    if field == 'Name':
                        latest_name = val
                    elif field == 'Version':
                        latest_version = val.split('=')[0]
                    elif field == 'Provides':
                        fill_provided_map(latest_name, latest_name, provided_map)
                        fill_provided_map('{}={}'.format(latest_name, latest_version), latest_name, provided_map)

                        if val != 'None':
                            for w in val.split(' '):
                                if w:
                                    word = w.strip()
                                    fill_provided_map(word, latest_name, provided_map)

                                    word_split = word.split('=')

                                    if word_split[0] != word:
                                        fill_provided_map(word_split[0], latest_name, provided_map)
                        else:
                            provided = True

                    elif provided:
                        latest_name = None
                        latest_version = None
                        provided = False

                elif provided:
                    for w in l.split(' '):
                        if w:
                            word = w.strip()
                            fill_provided_map(word, latest_name, provided_map)

                            word_split = word.split('=')

                            if word_split[0] != word:
                                fill_provided_map(word_split[0], latest_name, provided_map)

        return provided_map


def list_download_data(pkgs: Iterable[str]) -> List[Dict[str, str]]:
    _, output = system.run(['pacman', '-Si', *pkgs])

    res = []
    if output:
        data = {'a': None, 'v': None, 'r': None, 'n': None}

        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()
                    val = line[field_sep_idx + 1:].strip()

                    if field == 'Repository':
                        data['r'] = val
                    elif field == 'Name':
                        data['n'] = val
                    elif field == 'Version':
                        data['v'] = val.split('=')[0]
                    elif field == 'Architecture':
                        data['a'] = val
                    elif data.get('a'):
                        res.append(data)
                        data = {'a': None, 'v': None, 'r': None, 'n': None}

    return res


def map_updates_data(pkgs: Iterable[str], files: bool = False) -> dict:
    if files:
        output = run_cmd('pacman -Qi -p {}'.format(' '.join(pkgs)))
    else:
        output = run_cmd('pacman -Si {}'.format(' '.join(pkgs)))

    res = {}
    if output:
        latest_name = None
        data = {'ds': None, 's': None, 'v': None, 'c': None, 'p': None, 'd': None, 'r': None}
        latest_field = None

        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()
                    val = line[field_sep_idx + 1:].strip()

                    if field == 'Repository':
                        data['r'] = val
                        latest_field = 'r'
                    elif field == 'Name':
                        latest_name = val
                        latest_field = 'n'
                    elif field == 'Version':
                        data['v'] = val.split('=')[0]
                        latest_field = 'v'
                    elif field == 'Provides':
                        latest_field = 'p'
                        data['p'] = {latest_name, '{}={}'.format(latest_name, data['v'])}
                        if val != 'None':
                            for w in val.split(' '):
                                if w:
                                    word = w.strip()
                                    data['p'].add(word)

                                    word_split = word.split('=')

                                    if word_split[0] != word:
                                        data['p'].add(word_split[0])
                    elif field == 'Depends On':
                        val = val.strip()

                        if val == 'None':
                            data['d'] = None
                        else:
                            data['d'] = {w.strip().split(':')[0].strip() for w in val.split(' ') if w}
                            latest_field = 'd'
                    elif field == 'Conflicts With':
                        if val == 'None':
                            data['c'] = None
                        else:
                            data['c'] = {w.strip() for w in val.split(' ') if w}

                        latest_field = 'c'
                    elif field == 'Download Size':
                        size = val.split(' ')
                        data['ds'] = size_to_byte(float(size[0]), size[1])
                        latest_field = 'ds'
                    elif field == 'Installed Size':
                        size = val.split(' ')
                        data['s'] = size_to_byte(float(size[0]), size[1])
                        latest_field = 's'
                    elif latest_name and latest_field == 's':
                        res[latest_name] = data
                        latest_name = None
                        latest_field = None
                        data = {'ds': None, 's': None, 'c': None, 'p': None, 'd': None, 'r': None,  'v': None}
                    else:
                        latest_field = None

                elif latest_field and latest_field in ('p', 'c', 'd'):
                    if latest_field == 'p':
                        for w in l.split(' '):
                            if w:
                                word = w.strip()
                                data['p'].add(word)

                                word_split = word.split('=')

                                if word_split[0] != word:
                                    data['p'].add(word_split[0])
                    else:
                        data[latest_field].update((w.strip() for w in l.split(' ') if w))

    return res


def upgrade_several(pkgnames: Iterable[str], root_password: str, overwrite_conflicting_files: bool = False, skip_dependency_checks: bool = False) -> SimpleProcess:
    cmd = ['pacman', '-S', *pkgnames, '--noconfirm']

    if overwrite_conflicting_files:
        cmd.append('--overwrite=*')

    if skip_dependency_checks:
        cmd.append('-d')

    return SimpleProcess(cmd=cmd,
                         root_password=root_password,
                         error_phrases={'error: failed to prepare transaction', 'error: failed to commit transaction', 'error: target not found'},
                         shell=True)


def download(root_password: str, *pkgnames: str) -> SimpleProcess:
    return SimpleProcess(cmd=['pacman', '-Swdd', *pkgnames, '--noconfirm'],
                         root_password=root_password,
                         error_phrases={'error: failed to prepare transaction', 'error: failed to commit transaction', 'error: target not found'},
                         shell=True)


def remove_several(pkgnames: Iterable[str], root_password: str, skip_checks: bool = False) -> SimpleProcess:
    cmd = ['pacman', '-R', *pkgnames, '--noconfirm']

    if skip_checks:
        cmd.append('-dd')

    return SimpleProcess(cmd=cmd, root_password=root_password, wrong_error_phrases={'warning:'}, shell=True)


def map_optional_deps(names: Iterable[str], remote: bool, not_installed: bool = False) -> Dict[str, Dict[str, str]]:
    output = run_cmd('pacman -{}i {}'.format('S' if remote else 'Q', ' '.join(names)))
    res = {}
    if output:
        latest_name, deps = None, None

        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()

                    if field == 'Name':
                        val = line[field_sep_idx + 1:].strip()
                        latest_name = val
                    elif field == 'Optional Deps':
                        val = line[field_sep_idx + 1:].strip()
                        deps = {}
                        if val != 'None':
                            if ':' in val:
                                dep_info = val.split(':')
                                desc = dep_info[1].strip()

                                if desc and not_installed and '[installed]' in desc:
                                    continue

                                deps[dep_info[0].strip()] = desc
                            else:
                                sev_deps = {dep.strip(): '' for dep in val.split(' ') if dep and (not not_installed or '[installed]' not in dep)}
                                deps.update(sev_deps)
                    elif latest_name and deps is not None:
                        res[latest_name] = deps
                        latest_name, deps = None, None

                elif latest_name and deps is not None:
                    if ':' in l:
                        dep_info = l.split(':')
                        desc = dep_info[1].strip()

                        if desc and not_installed and '[installed]' in desc:
                            continue

                        deps[dep_info[0].strip()] = desc
                    else:
                        sev_deps = {dep.strip(): '' for dep in l.split(' ') if dep and (not not_installed or '[installed]' not in dep)}
                        deps.update(sev_deps)

    return res


def map_all_deps(names: Iterable[str], only_installed: bool = False) -> Dict[str, Set[str]]:
    output = run_cmd('pacman -Qi {}'.format(' '.join(names)))

    if output:
        res = {}
        deps_fields = {'Depends On', 'Optional Deps'}
        latest_name, deps, latest_field = None, None, None

        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()

                    if field == 'Name':
                        latest_field = field
                        val = line[field_sep_idx + 1:].strip()
                        latest_name = val
                        deps = None
                    elif field in deps_fields:
                        latest_field = field
                        val = line[field_sep_idx + 1:].strip()
                        opt_deps = latest_field == 'Optional Deps'

                        if deps is None:
                            deps = set()

                        if val != 'None':
                            if ':' in val:
                                dep_info = val.split(':')
                                desc = dep_info[1].strip()

                                if desc and opt_deps and only_installed and '[installed]' not in desc:
                                    continue

                                deps.add(dep_info[0].strip())
                            else:
                                deps.update({dep.strip() for dep in val.split(' ') if dep})

                    elif latest_name and deps is not None:
                        res[latest_name] = deps
                        latest_name, deps, latest_field = None, None, None

                elif latest_name and deps is not None:
                    opt_deps = latest_field == 'Optional Deps'

                    if ':' in l:
                        dep_info = l.split(':')
                        desc = dep_info[1].strip()

                        if desc and opt_deps and only_installed and '[installed]' not in desc:
                            continue

                        deps.add(dep_info[0].strip())
                    else:
                        deps.update({dep.strip() for dep in l.split(' ') if dep})

        return res


def map_required_dependencies(*names: str) -> Dict[str, Set[str]]:
    output = run_cmd('pacman -Qi {}'.format(' '.join(names) if names else ''))

    if output:
        res = {}
        latest_name, deps, latest_field = None, None, None

        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()

                    if field == 'Name':
                        val = line[field_sep_idx + 1:].strip()
                        latest_name = val
                        deps = None
                    elif field == 'Depends On':
                        val = line[field_sep_idx + 1:].strip()

                        if deps is None:
                            deps = set()

                        if val != 'None':
                            if ':' in val:
                                dep_info = val.split(':')
                                deps.add(dep_info[0].strip())
                            else:
                                deps.update({dep.strip() for dep in val.split(' ') if dep})

                    elif latest_name and deps is not None:
                        res[latest_name] = deps
                        latest_name, deps, latest_field = None, None, None

                elif latest_name and deps is not None:
                    if ':' in l:
                        dep_info = l.split(':')
                        deps.add(dep_info[0].strip())
                    else:
                        deps.update({dep.strip() for dep in l.split(' ') if dep})

        return res


def get_cache_dir() -> str:
    dir_pattern = re.compile(r'.*CacheDir\s*=\s*.+')

    if os.path.exists('/etc/pacman.conf'):
        with open('/etc/pacman.conf') as f:
            config_str = f.read()

        cache_dirs = []

        for string in dir_pattern.findall(config_str):
            if not string.strip().startswith('#'):
                cache_dirs.append(string.split('=')[1].strip())

        if cache_dirs:
            if cache_dirs[-1][-1] == '/':
                return cache_dirs[-1][0:-1]
            else:
                return cache_dirs[-1]
        else:
            return '/var/cache/pacman/pkg'


def map_required_by(names: Iterable[str] = None, remote: bool = False) -> Dict[str, Set[str]]:
    output = run_cmd('pacman -{} {}'.format('Sii' if remote else 'Qi', ' '.join(names) if names else ''), print_error=False)

    if output:
        latest_name, required = None, None
        res = {}
        
        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()

                    if field == 'Name':
                        val = line[field_sep_idx + 1:].strip()
                        latest_name = val
                    elif field == 'Required By':
                        val = line[field_sep_idx + 1:].strip()
                        required = set()
                        if val != 'None':
                            required.update((d for d in val.split(' ') if d))

                    elif latest_name and required is not None:
                        res[latest_name] = required
                        latest_name, required = None, None

                elif latest_name and required is not None:
                    required.update(required.update((d for d in l.strip().split(' ') if d)))
        return res
    elif names:
        return {n: set() for n in names}
    else:
        return {}


def map_conflicts_with(names: Iterable[str], remote: bool) -> Dict[str, Dict[str, Set[str]]]:
    output = run_cmd('pacman -{}i {}'.format('S' if remote else 'Q', ' '.join(names)))

    if output:
        res = {}
        latest_name, conflicts, replaces, field = None, None, None, None

        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()

                    if field == 'Name':
                        field = 'n'
                        val = line[field_sep_idx + 1:].strip()
                        latest_name = val
                    elif field == 'Conflicts With':
                        field = 'c'
                        val = line[field_sep_idx + 1:].strip()
                        conflicts = set()
                        if val != 'None':
                            conflicts.update((d for d in val.split(' ') if d))
                    elif field == 'Replaces':
                        field = 'r'
                        val = line[field_sep_idx + 1:].strip()
                        replaces = set()
                        if val != 'None':
                            replaces.update((d for d in val.split(' ') if d))

                    elif latest_name and conflicts is not None and replaces is not None:
                        field = None
                        res[latest_name] = {'c': conflicts, 'r': replaces}
                        latest_name, conflicts, replaces = None, None, None

                elif latest_name and field:
                    if field == 'c':
                        conflicts.update((d for d in l.strip().split(' ') if d))
                    elif field == 'r':
                        replaces.update((d for d in l.strip().split(' ') if d))

        return res


def map_replaces(names: Iterable[str], remote: bool = False) -> Dict[str, Set[str]]:
    output = run_cmd('pacman -{}i {}'.format('S' if remote else 'Q', ' '.join(names)))

    if output:
        res = {}
        latest_name, replaces = None, None

        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()

                    if field == 'Name':
                        val = line[field_sep_idx + 1:].strip()
                        latest_name = val
                    elif field == 'Replaces':
                        val = line[field_sep_idx + 1:].strip()
                        replaces = set()
                        if val != 'None':
                            replaces.update((d for d in val.split(' ') if d))

                    elif latest_name and replaces is not None:
                        res[latest_name] = replaces
                        latest_name, replaces = None, None

                elif latest_name and replaces is not None:
                    replaces.update((d for d in l.strip().split(' ') if d))

        return res


def _list_unnecessary_deps(pkgs: Iterable[str], already_checked: Set[str], all_provided: Dict[str, Set[str]], recursive: bool = False) -> Set[str]:
    output = run_cmd('pacman -Qi {}'.format(' '.join(pkgs)))

    if output:
        res = set()
        deps_field = False

        for l in output.split('\n'):
            if l:
                if l[0] != ' ':
                    line = l.strip()
                    field_sep_idx = line.index(':')
                    field = line[0:field_sep_idx].strip()

                    if field == 'Depends On':
                        deps_field = True
                        val = line[field_sep_idx + 1:].strip()

                        if val != 'None':
                            if ':' in val:
                                dep_info = val.split(':')

                                real_deps = all_provided.get(dep_info[0].strip())

                                if real_deps:
                                    res.update(real_deps)
                            else:
                                for dep in val.split(' '):
                                    if dep:
                                        real_deps = all_provided.get(dep.strip())

                                        if real_deps:
                                            res.update(real_deps)

                    elif deps_field:
                        latest_field = False

                elif deps_field:
                    if ':' in l:
                        dep_info = l.split(':')

                        real_deps = all_provided.get(dep_info[0].strip())

                        if real_deps:
                            res.update(real_deps)
                    else:
                        for dep in l.split(' '):
                            if dep:
                                real_deps = all_provided.get(dep.strip())

                                if real_deps:
                                    res.update(real_deps)

        if res:
            res = {dep for dep in res if dep not in already_checked}
            already_checked.update(res)

            if recursive and res:
                subdeps = _list_unnecessary_deps(res, already_checked, all_provided)

                if subdeps:
                    res.update(subdeps)

        return res


def list_unnecessary_deps(pkgs: Iterable[str], all_provided: Dict[str, Set[str]] = None) -> Set[str]:
    all_checked = set(pkgs)
    all_deps = _list_unnecessary_deps(pkgs, all_checked, map_provided(remote=False) if not all_provided else all_provided, recursive=True)

    unnecessary = set(pkgs)
    if all_deps:
        requirements_map = map_required_by(all_deps)

        to_clean = set()
        for dep, required_by in requirements_map.items():
            if not required_by or not required_by.difference(unnecessary):
                unnecessary.add(dep)
                to_clean.add(dep)
            elif required_by.difference(all_checked):  # checking if there are requirements outside the context
                to_clean.add(dep)

        if to_clean:
            for dep in to_clean:
                del requirements_map[dep]

        if requirements_map:
            while True:
                to_clean = set()
                for dep, required_by in requirements_map.items():
                    if not required_by.difference(unnecessary):
                        unnecessary.add(dep)
                        to_clean.add(dep)

                if to_clean:
                    for dep in to_clean:
                        del requirements_map[dep]
                else:
                    break

            if requirements_map:  # if it reaches this points it is possible to exist mutual dependent packages
                for dep, required_by in requirements_map.items():
                    if not required_by.difference({*requirements_map.keys(), *unnecessary}):
                        unnecessary.add(dep)

    return unnecessary.difference(pkgs)


def list_installed_names() -> Set[str]:
    output = run_cmd('pacman -Qq', print_error=False)
    return {name.strip() for name in output.split('\n') if name} if output else set()


def list_available_mirrors() -> List[str]:
    _, output = system.run(['pacman-mirrors', '--status', '--no-color'])

    if output:
        mirrors = RE_AVAILABLE_MIRRORS.findall(output)

        if mirrors:
            mirrors.sort(key=lambda o: o[0])
            return [m[1] for m in mirrors]


def get_mirrors_branch() -> str:
    _, output = system.run(['pacman-mirrors', '-G'])
    return output.strip()


def get_packages_to_sync_first() -> Set[str]:
    if os.path.exists('/etc/pacman.conf'):
        with open('/etc/pacman.conf') as f:
            to_sync_first = RE_PACMAN_SYNC_FIRST.findall(f.read())

            if to_sync_first:
                return {s.strip() for s in to_sync_first[0].split(' ') if s and s.strip()}

    return set()


def is_snapd_installed() -> bool:
    return bool(run_cmd('pacman -Qq snapd', print_error=False))


def list_hard_requirements(name: str, logger: Optional[logging.Logger] = None) -> Optional[Set[str]]:
    code, output = system.execute('pacman -Rc {} --print-format=%n'.format(name), shell=True)

    if code != 0:
        if 'HoldPkg' in output:
            raise PackageInHoldException()
        elif 'target not found' in output:
            raise PackageNotFoundException(name)
        elif logger:
            logger.error("Unexpected error while listing hard requirements of: {}".format(name))
            print('{}{}{}'.format(Fore.RED, output, Fore.RESET))
    elif output:
        reqs = set()

        for line in output.split('\n'):
            if line:
                line_strip = line.strip()

                if line_strip and line_strip != name:
                    reqs.add(line_strip)

        return reqs


def list_post_uninstall_unneeded_packages(names: Set[str]) -> Set[str]:
    output = run_cmd('pacman -Rss {} --print-format=%n'.format(' '.join(names)), print_error=False)

    reqs = set()
    if output:
        for line in output.split('\n'):
            if line:
                line_strip = line.strip()

                if line_strip and line_strip not in names:
                    reqs.add(line_strip)

    return reqs


def find_one_match(name: str) -> Optional[str]:
    output = run_cmd('pacman -Ssq {}'.format(name), print_error=False)

    if output:
        matches = [l.strip() for l in output.split('\n') if l.strip()]

        if matches and len(matches) == 1:
            return matches[0]
