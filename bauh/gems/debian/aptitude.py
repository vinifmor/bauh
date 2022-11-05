import re
import time
from contextlib import contextmanager
from enum import Enum
from logging import Logger
from math import ceil
from queue import Queue
from threading import Thread
from typing import Iterable, Optional, Pattern, Dict, Set, Tuple, Generator, Collection

from bauh.api.abstract.handler import ProcessWatcher
from bauh.commons import system
from bauh.commons.html import bold
from bauh.commons.system import SimpleProcess
from bauh.commons.util import size_to_byte
from bauh.gems.debian.common import strip_maintainer_email, strip_section
from bauh.gems.debian.model import DebianPackage, DebianTransaction
from bauh.view.util.translation import I18n


def map_package_name(string: str):
    name_split = string.split(':')

    if len(name_split) > 2:
        return ':'.join(name_split[0:-1])

    return name_split[0]


class AptitudeAction(Enum):
    INSTALL = 0
    UPGRADE = 1
    REMOVE = 3


class Aptitude:

    def __init__(self, logger: Logger):
        self._log = logger
        self._re_show_attr: Optional[Pattern] = None
        self._env: Optional[Dict[str, str]] = None
        self._list_attrs: Optional[Set[str]] = None
        self._re_to_install: Optional[Pattern] = None
        self._re_transaction_pkg: Optional[Pattern] = None
        self._size_attrs: Optional[Tuple[str]] = None
        self._default_lang = ''
        self._ignored_fields: Optional[Set[str]] = None
        self._re_none: Optional[Pattern] = None
        self._vars_fixes: Optional[Dict[str, str]] = None
        self._preserve_env = {'DEBIAN_FRONTEND'}

    def show(self, pkgs: Iterable[str], attrs: Optional[Collection[str]] = None, verbose: bool = False) \
            -> Optional[Dict[str, Dict[str, object]]]:

        if pkgs:
            force_verbose = verbose if verbose else ('compressed size' in attrs if attrs else False)
            code, output = system.execute(f"aptitude show -q {' '.join(pkgs)}{' -v' if force_verbose else ''}",
                                          shell=True, custom_env=self.env)

            if code == 0 and output:
                info, pkg = dict(), None
                for field, val in self.re_show_attr.findall('\n' + output):
                    final_field, final_val = field.strip().lower(), val.strip()

                    if final_field == 'package':
                        pkg = {}
                        info[final_val] = pkg
                    elif final_field not in self.ignored_fields and (not attrs or final_field in attrs):
                        if final_val:
                            if final_field in self.list_attrs:
                                final_val = tuple((v.strip() for v in final_val.split(',') if v))
                            elif final_field in self.size_attrs:
                                size_split = final_val.split(' ')

                                if len(size_split) >= 1:
                                    unit = size_split[1].upper() if len(size_split) >= 2 else 'B'
                                    final_val = size_to_byte(size_split[0], unit, self._log)
                                else:
                                    self._log.warning(f"Unhandled value ({val}) for attribute '{field}'")
                                    final_val = None

                        pkg[final_field] = final_val

                return info

    def simulate_removal(self, packages: Iterable[str], purge: bool = False) -> Optional[DebianTransaction]:
        code, output = system.execute(self.gen_remove_cmd(packages, purge, simulate=True), shell=True,
                                      custom_env=self.env)

        if code == 0 and output:
            return self.map_transaction_output(output)

    def map_transaction_output(self, output: str) -> DebianTransaction:
        to_install, to_upgrade, to_remove = None, None, None
        current_collection = None

        for line in output.split('\n'):
            if line.startswith('The following NEW packages will be installed:'):
                to_install = set()
                current_collection = to_install
            elif line.startswith('The following packages will be upgraded:'):
                to_upgrade = set()
                current_collection = to_upgrade
            elif line.startswith('The following packages will be REMOVED:'):
                to_remove = set()
                current_collection = to_remove
            elif line.startswith('Would download/install/remove packages'):
                break
            elif current_collection is not None and line.startswith(' '):
                for n, _, v, __, lv, ___, size in self.re_transaction_pkg.findall(line):
                    pkg = DebianPackage(name=n, version=v, latest_version=lv if lv else v, transaction_size=0)

                    if size:
                        size_split = size.strip().split(' ')
                        unit = size_split[1][0].upper() if len(size_split) >= 2 else 'B'
                        pkg.transaction_size = size_to_byte(size_split[0], unit, self._log)

                    current_collection.add(pkg)

        return DebianTransaction(to_install=tuple(to_install) if to_install else tuple(),
                                 to_remove=tuple(to_remove) if to_remove else tuple(),
                                 to_upgrade=tuple(to_upgrade) if to_upgrade else tuple())

    def simulate_upgrade(self, packages: Iterable[str]) -> DebianTransaction:
        code, output = system.execute(self.gen_transaction_cmd('upgrade', packages, simulate=True),
                                      shell=True, custom_env=self.env)

        if code == 0 and output:
            return self.map_transaction_output(output)

    def upgrade(self, packages: Iterable[str], root_password: Optional[str]) -> SimpleProcess:
        cmd = self.gen_transaction_cmd('upgrade', packages).split(' ')
        return SimpleProcess(cmd=cmd, shell=True, root_password=root_password, extra_env=self.vars_fixes,
                             preserve_env=self._preserve_env)

    def update(self, root_password: Optional[str]) -> SimpleProcess:
        return SimpleProcess(('aptitude', 'update'), root_password=root_password, shell=True)

    def simulate_installation(self, packages: Iterable[str]) -> Optional[DebianTransaction]:
        code, output = system.execute(self.gen_transaction_cmd('install', packages, simulate=True),
                                      shell=True, custom_env=self.env)

        if code == 0 and output:
            return self.map_transaction_output(output)

    def install(self, packages: Iterable[str], root_password: Optional[str]) -> SimpleProcess:
        cmd = self.gen_transaction_cmd('install', packages).split(' ')
        return SimpleProcess(cmd=cmd, root_password=root_password, extra_env=self.vars_fixes,
                             preserve_env=self._preserve_env)

    def read_installed(self) -> Generator[DebianPackage, None, None]:
        yield from self.search(query='~i')

    def read_updates(self) -> Generator[Tuple[str, str], None, None]:
        _, output = system.execute(f"aptitude search ~U -q -F '%p^%V' --disable-columns --no-gui",
                                   shell=True,
                                   custom_env=self.env)

        if output:
            for line in output.split('\n'):
                line_split = line.strip().split('^')

                if len(line_split) == 2 and line_split[1] != '<none>':
                    yield line_split[0], line_split[1]

    def search(self, query: str, fill_size: bool = False) -> Generator[DebianPackage, None, None]:
        attrs = f"%p^%v^%V^%m^%s^{'%I^' if fill_size else ''}%d"
        _, output = system.execute(f"aptitude search {query} -q -F '{attrs}' --disable-columns", shell=True)

        if output:
            no_attrs = 7 if fill_size else 6

            for line in output.split('\n'):
                line_split = line.strip().split('^', maxsplit=no_attrs - 1)

                if len(line_split) == no_attrs:
                    latest_version = line_split[2] if not self.re_none.match(line_split[2]) else None

                    size = None

                    if fill_size:
                        size_split = line_split[no_attrs - 2].split(' ')
                        unit = size_split[1][0].upper() if len(size_split) >= 2 else 'B'
                        size = size_to_byte(size_split[0], unit, self._log)

                    if latest_version is not None:
                        installed_version = line_split[1] if not self.re_none.match(line_split[1]) else None
                        section = strip_section(line_split[4])

                        yield DebianPackage(name=line_split[0],
                                            version=installed_version if installed_version else latest_version,
                                            latest_version=latest_version,
                                            installed=bool(installed_version),
                                            update=installed_version is not None and installed_version != latest_version,
                                            maintainer=strip_maintainer_email(line_split[3]),
                                            categories=(section,) if section else None,
                                            uncompressed_size=size,
                                            description=line_split[no_attrs - 1])

    def search_by_name(self, names: Iterable[str], fill_size: bool = False) -> Generator[DebianPackage, None, None]:
        query = f"'({'|'.join(f'?exact-name({n})' for n in names)})'"
        yield from self.search(query=query, fill_size=fill_size)

    def remove(self, packages: Iterable[str], root_password: Optional[str],  purge: bool = False) -> SimpleProcess:
        return SimpleProcess(cmd=self.gen_remove_cmd(packages, purge).split(' '), shell=True,
                             root_password=root_password, extra_env=self.vars_fixes, preserve_env=self._preserve_env)

    def read_installed_names(self) -> Generator[str, None, None]:
        code, output = system.execute("aptitude search ~i -q -F '%p' --disable-columns",
                                      shell=True,
                                      custom_env=self.env)

        if output:
            for line in output.split('\n'):
                if line:
                    yield line

    @property
    def re_show_attr(self) -> Pattern:
        if self._re_show_attr is None:
            self._re_show_attr = re.compile(r'(\n\w+[a-zA-Z0-9\-\s]*):\s+(.+)')

        return self._re_show_attr

    @property
    def env(self) -> Dict[str, str]:
        if self._env is None:
            self._env = system.gen_env(global_interpreter=system.USE_GLOBAL_INTERPRETER)
            self._env['LC_NUMERIC'] = ''

        return self._env

    @property
    def list_attrs(self) -> Set[str]:
        if self._list_attrs is None:
            self._list_attrs = {'depends', 'provides', 'replaces', 'recommends', 'suggests', 'conflicts',
                                'state', 'predepends', 'breaks'}

        return self._list_attrs

    @property
    def re_transaction_pkg(self) -> Pattern:
        if self._re_transaction_pkg is None:
            self._re_transaction_pkg = re.compile(r'([a-zA-Z0-9\-_@~.+:]+)({\w+})?\s*\[([a-zA-Z0-9\-_@~.+:]+)'
                                                  r'(\s+->\s+([a-zA-Z0-9\-_@~.+:]+))?](\s*<([\-+]?[0-9.,]+\s+\w+)>)?')

        return self._re_transaction_pkg

    @property
    def size_attrs(self) -> Tuple[str]:
        if self._size_attrs is None:
            self._size_attrs = {'compressed size', 'uncompressed size'}

        return self._size_attrs

    @property
    def ignored_fields(self) -> Set[str]:
        if self._ignored_fields is None:
            self._ignored_fields = {'sha1', 'sha256', 'sha512', 'checksum-filesize'}

        return self._ignored_fields

    @classmethod
    def gen_remove_cmd(cls, packages: Iterable[str], purge: bool, simulate: bool = False) -> str:
        return cls.gen_transaction_cmd(type_='purge' if purge else 'remove', packages=packages,
                                       simulate=simulate)

    @staticmethod
    def gen_transaction_cmd(type_: str, packages: Iterable[str], simulate: bool = False,
                            delete_unused: bool = False) -> str:
        return f"aptitude {type_} -q -y --no-gui --full-resolver {' '.join(packages)}" \
               f" -o Aptitude::ProblemResolver::RemoveScore=9999999" \
               f" -o Aptitude::ProblemResolver::EssentialRemoveScore=9999999" \
               f" -o Aptitude::Delete-Unused={str(delete_unused).lower()}" \
               f"{' -V -s -Z' if simulate else ''}"

    @property
    def re_none(self) -> Pattern:
        if self._re_none is None:
            self._re_none = re.compile(r'^<\w+>$')

        return self._re_none

    @property
    def vars_fixes(self) -> Dict[str, str]:
        if self._vars_fixes is None:
            self._vars_fixes = {'LC_NUMERIC': '', 'DEBIAN_FRONTEND': 'noninteractive'}

        return self._vars_fixes


class AptitudeOutputHandler(Thread):

    def __init__(self, i18n: I18n, targets: Iterable[str], re_download: Pattern, watcher: ProcessWatcher,
                 action: AptitudeAction):
        super(AptitudeOutputHandler, self).__init__()
        self._i18n = i18n
        self._re_download = re_download
        self._watcher = watcher
        self._targets = set(targets) if targets is not None else None
        self._unpacking = 0
        self._removing = 0
        self._downloading = 0
        self._to_process = Queue()
        self._work = True
        self._action = action

    def stop_working(self):
        self._work = False

    def handle(self, string: str):
        self._to_process.put(string)

    @property
    def total_targets(self) -> int:
        return len(self._targets) if self._targets else 0

    @property
    def processed(self) -> int:
        return self._removing if self._action == AptitudeAction.REMOVE else self._unpacking

    def _get_progress(self, current: int) -> str:
        if self.total_targets > 0:
            if self._action == AptitudeAction.REMOVE:
                total = self._removing
            else:
                if self.total_targets == self._unpacking:
                    total = self.total_targets
                else:
                    total = ceil((self._unpacking + self._downloading) / 2)

            return f'({total / self.total_targets * 100:.2f}%) [{current}/{self.total_targets}] '

        return ''

    def run(self):
        while self._work:
            time.sleep(0.001)

            if self._to_process.empty():
                continue

            string = self._to_process.get()

            if self.total_targets > 0 and self.total_targets == self._unpacking:
                self._watcher.change_substatus(self._i18n['debian.output.finishing'])
                continue

            if string:
                if self._action != AptitudeAction.REMOVE and string.startswith('Unpacking '):
                    unpacking = string.split(' ')

                    if len(unpacking) >= 2 and unpacking[1]:
                        pkg = map_package_name(unpacking[1].strip())

                        if self._targets and pkg in self._targets:
                            self._unpacking += 1

                        msg = f"{self._get_progress(self._unpacking)}" \
                              f"{self._i18n['debian.output.unpacking'].format(pkg=bold(pkg))}"

                        self._watcher.change_substatus(msg)

                        continue

                if self._action == AptitudeAction.REMOVE and string.startswith('Removing '):
                    unpacking = string.split(' ')

                    if len(unpacking) >= 2 and unpacking[1]:
                        pkg = unpacking[1].strip()

                        if self._targets and pkg in self._targets:
                            self._removing += 1

                        msg = f"{self._get_progress(self._removing)}" \
                              f"{self._i18n['debian.output.removing'].format(pkg=bold(pkg))}"

                        self._watcher.change_substatus(msg)

                        continue

                download = self._re_download.findall(string)

                if download:
                    data = download[0].split(' ')

                    if len(data) >= 4:
                        pkg = data[3].strip()

                        if self._targets and pkg in self._targets:
                            self._downloading += 1

                        msg = f"{self._get_progress(self._downloading)}" \
                              f"{self._i18n['debian.output.downloading'].format(pkg=bold(pkg))}"

                        self._watcher.change_substatus(msg)

                        continue

                _processed = self.processed
                if self._targets and _processed > 0:
                    self._watcher.change_substatus(self._get_progress(_processed).strip())
                    continue

            self._watcher.change_substatus(' ')


class AptitudeOutputHandlerFactory:

    def __init__(self, i18n: I18n):
        self._i18n = i18n
        self._re_download: Optional[Pattern] = None

    @property
    def re_download(self) -> Pattern:
        if self._re_download is None:
            self._re_download = re.compile(r'Get:\s+\d+\s+https?://(.+)')

        return self._re_download

    @contextmanager
    def start(self, watcher: ProcessWatcher, targets: Iterable[str], action: AptitudeAction):
        handler = AptitudeOutputHandler(i18n=self._i18n, re_download=self.re_download,
                                        watcher=watcher, targets=targets, action=action)
        handler.start()

        yield handler.handle

        handler.stop_working()
        handler.join()
