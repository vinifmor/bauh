import re
from threading import Thread
from typing import List, Set, Tuple, Dict, Iterable

from bauh.commons.system import run_cmd, new_subprocess, new_root_subprocess, SystemProcess, SimpleProcess
from bauh.gems.arch.exceptions import PackageNotFoundException

RE_DEPS = re.compile(r'[\w\-_]+:[\s\w_\-\.]+\s+\[\w+\]')
RE_OPTDEPS = re.compile(r'[\w\._\-]+\s*:')
RE_DEP_NOTFOUND = re.compile(r'error:.+\'(.+)\'')
RE_DEP_OPERATORS = re.compile(r'[<>=]')
RE_INSTALLED_FIELDS = re.compile(r'(Name|Description|Version|Validated By)\s*:\s*(.+)')
RE_INSTALLED_SIZE = re.compile(r'Installed Size\s*:\s*([0-9,\.]+)\s(\w+)\n?', re.IGNORECASE)


def is_available() -> bool:
    res = run_cmd('which pacman', print_error=False)
    return res and not res.strip().startswith('which ')


def get_repositories(pkgs: Set[str]) -> dict:
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
    return run_cmd('pacman -{}i {}'.format('Q' if not remote else 'S', pkg_name))


def get_info_list(pkg_name: str, remote: bool = False) -> List[tuple]:
    info = get_info(pkg_name, remote)
    if info:
        return re.findall(r'(\w+\s?\w+)\s*:\s*(.+(\n\s+.+)*)', info)


def get_info_dict(pkg_name: str, remote: bool = False) -> dict:
    list_attrs = {'depends on', 'required by'}
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


def list_installed() -> Set[str]:
    return {out.decode().strip() for out in new_subprocess(['pacman', '-Qq']).stdout if out}


def check_installed(pkg: str) -> bool:
    res = run_cmd('pacman -Qq ' + pkg, print_error=False)
    return bool(res)


def _fill_ignored(res: dict):
    res['pkgs'] = list_ignored_packages()


def map_installed(repositories: bool = True, aur: bool = True) -> dict:  # returns a dict with with package names as keys and versions as values
    ignored = {}
    thread_ignored = Thread(target=_fill_ignored, args=(ignored,), daemon=True)
    thread_ignored.start()

    allinfo = run_cmd('pacman -Qi')

    pkgs = {'signed': {}, 'not_signed': {}}
    current_pkg = {}
    for idx, field_tuple in enumerate(RE_INSTALLED_FIELDS.findall(allinfo)):
        if field_tuple[0].startswith('N'):
            current_pkg['name'] = field_tuple[1].strip()
        elif field_tuple[0].startswith('Ve'):
            current_pkg['version'] = field_tuple[1].split(':')[-1].strip()
        elif field_tuple[0].startswith('D'):
            current_pkg['description'] = field_tuple[1].strip()
        elif field_tuple[0].startswith('Va'):
            if field_tuple[1].strip().lower() == 'none' and aur:
                pkgs['not_signed'][current_pkg['name']] = current_pkg
                del current_pkg['name']
            elif repositories:
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


def install_as_process(pkgpath: str, root_password: str, file: bool, pkgdir: str = '.') -> SystemProcess:
    if file:
        cmd = ['pacman', '-U', pkgpath, '--noconfirm']  # pkgpath = install file path
    else:
        cmd = ['pacman', '-S', pkgpath, '--noconfirm']  # pkgpath = pkgname

    return SystemProcess(new_root_subprocess(cmd, root_password, cwd=pkgdir), wrong_error_phrase='warning:')


def list_desktop_entries(pkgnames: Set[str]) -> List[str]:
    if pkgnames:
        installed_files = new_subprocess(['pacman', '-Qlq', *pkgnames])

        desktop_files = []
        for out in new_subprocess(['grep', '-E', ".desktop$"], stdin=installed_files.stdout).stdout:
            if out:
                desktop_files.append(out.decode().strip())

        return desktop_files


def list_icon_paths(pkgnames: Set[str]) -> List[str]:
    installed_files = new_subprocess(['pacman', '-Qlq', *pkgnames])

    icon_files = []
    for out in new_subprocess(['grep', '-E', '.(png|svg|xpm)$'], stdin=installed_files.stdout).stdout:
        if out:
            line = out.decode().strip()
            if line:
                icon_files.append(line)

    return icon_files


def list_bin_paths(pkgnames: Set[str]) -> List[str]:
    installed_files = new_subprocess(['pacman', '-Qlq', *pkgnames])

    bin_paths = []
    for out in new_subprocess(['grep', '-E', '^/usr/bin/.+'], stdin=installed_files.stdout).stdout:
        if out:
            line = out.decode().strip()
            if line:
                bin_paths.append(line)

    return bin_paths


def list_installed_files(pkgname: str) -> List[str]:
    installed_files = new_subprocess(['pacman', '-Qlq', pkgname])

    f_paths = []

    for out in new_subprocess(['grep', '-E', '/.+\..+[^/]$'], stdin=installed_files.stdout).stdout:
        if out:
            line = out.decode().strip()
            if line:
                f_paths.append(line)

    return f_paths


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


def map_repositories(pkgnames: Iterable[str]) -> Dict[str, str]:
    info = run_cmd('pacman -Si {}'.format(' '.join(pkgnames)), print_error=False, ignore_return_code=True)
    if info:
        repos = re.findall(r'(Name|Repository)\s*:\s*(\w+)', info)

        if repos:
            return {repos[idx+1][1]: repo_data[1] for idx, repo_data in enumerate(repos) if idx % 2 == 0}

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
    output = run_cmd('pacman -Ss ' + words)

    if output:
        found, current = {}, {}
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

                    version = data_split[1].split(':')
                    current['version'] = version[0] if len(version) == 1 else version[1]
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
    res = run_cmd('which pacman-mirrors', print_error=False)
    return res and not res.strip().startswith('which ')


def size_to_byte(size: float, unit: str) -> int:
    lower_unit = unit.lower()

    if lower_unit[0] == 'b':
        final_size = size
    elif lower_unit[0] == 'k':
        final_size = size * 1000
    elif lower_unit[0] == 'm':
        final_size = size * 1000000
    elif lower_unit[0] == 't':
        final_size = size * 1000000000000
    else:
        final_size = size * 1000000000000000

    return int(final_size)


def get_installation_size(pkgs: List[str]) -> Dict[str, int]:  # bytes:
    output = run_cmd('pacman -Si {}'.format(' '.join(pkgs)))

    if output:
        return {pkgs[idx]: size_to_byte(float(size[0]), size[1]) for idx, size in enumerate(RE_INSTALLED_SIZE.findall(output))}
