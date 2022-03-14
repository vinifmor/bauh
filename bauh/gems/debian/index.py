import json
import os
import re
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from json import JSONDecodeError
from logging import Logger
from pathlib import Path
from typing import Optional, Set, Generator, Iterable

from bauh.commons import system
from bauh.gems.debian import APP_INDEX_FILE
from bauh.gems.debian.model import DebianApplication


class ApplicationIndexError(Exception):

    def __init__(self, cause: Optional[str] = None):
        self.cause = cause


class ApplicationIndexer:

    def __init__(self, logger: Logger, index_file_path: str = APP_INDEX_FILE):
        self._log = logger
        self._file_path = index_file_path
        self._file_timestamp_path = f'{self._file_path}.ts'

    def is_expired(self, deb_config: dict) -> bool:

        try:
            exp_minutes = int(deb_config.get('index_apps.exp', 0))
        except ValueError:
            self._log.error(f"Invalid value for Debian configuration property 'index_apps.exp': "
                            f"{deb_config['index_apps.exp']}")
            return True

        if exp_minutes <= 0:
            self._log.warning("Debian applications index will always be updated ('index_apps.exp' <= 0 )'")
            return True

        if not os.path.exists(self._file_path):
            self._log.info(f"Debian applications index not found. A new one must be generated ({self._file_path})")
            return True

        try:
            with open(self._file_timestamp_path) as f:
                timestamp_str = f.read().strip()
        except FileNotFoundError:
            self._log.info(f"Debian applications index timestamp not found ({self._file_timestamp_path})")
            return True

        try:
            timestamp = datetime.fromtimestamp(float(timestamp_str))
        except:
            self._log.error(f'Could not parse the Debian applications index timestamp: {timestamp_str} '
                            f'({self._file_timestamp_path})')
            traceback.print_exc()
            return True

        expired = timestamp + timedelta(minutes=exp_minutes) <= datetime.utcnow()

        if expired:
            self._log.info("Debian applications index has expired. A new one must be generated.")
        else:
            self._log.info("Debian applications index is up-to-date")

        return expired

    def read_index(self) -> Generator[DebianApplication, None, None]:
        try:
            with open(self._file_path) as f:
                idx_str = f.read().strip()

            if not idx_str:
                self._log.warning(f"Debian applications index is empty ({self._file_path})")
            else:
                try:
                    for name, data in json.loads(idx_str).items():
                        exe_path, icon_path = data.get('exe_path'), data.get('icon_path')

                        if not all((name, exe_path, icon_path)):
                            self._log.warning(f"Invalid entry in the Debian applications index ({self._file_path}): name={name}, exe_path={exe_path}, icon_path={icon_path}")
                        else:
                            categories = data.get('categories')
                            yield DebianApplication(name=name, exe_path=exe_path, icon_path=icon_path,
                                                    categories=tuple(categories) if categories else None)

                except JSONDecodeError:
                    self._log.error(f"The Debian applications index is corrupted ({self._file_path}). "
                                    f"Could not decode the JSON.")

        except FileNotFoundError:
            self._log.warning(f"Debian applications index not found ({self._file_path})")
        except OSError as e:
            self._log.error(f"Debian applications index could not be read ({self._file_path}). OSError: {e.errno}")

    def update_index(self, apps: Set[DebianApplication], update_timestamp: bool = True):
        idx_dir = os.path.dirname(self._file_path)

        try:
            Path(idx_dir).mkdir(exist_ok=True, parents=True)
        except OSError:
            self._log.error(f"Could not create directory '{idx_dir}'")
            raise ApplicationIndexError()

        idx = {}
        if apps:
            for app in apps:
                idx.update(app.to_index())

        try:
            with open(self._file_path, 'w+') as f:
                if idx:
                    f.write(json.dumps(idx, sort_keys=True, indent=4))
                else:
                    f.write('')

        except OSError:
            self._log.error(f"Could not write to the Debian applications index file: {self._file_path}")
            raise ApplicationIndexError()

        if update_timestamp:
            index_timestamp = datetime.utcnow().timestamp()
            try:
                with open(self._file_timestamp_path, 'w+') as f:
                    f.write(str(index_timestamp))

                self._log.info("Debian applications index timestamp updated")

            except OSError:
                self._log.error(f"Could not write to the Debian applications index timestamp file: "
                                f"{self._file_timestamp_path}")
                raise ApplicationIndexError()


class ApplicationsMapper:

    def __init__(self, logger: Logger, workers: int = 10):
        self._log = logger
        self._re_desktop_file = re.compile(r'(.+):\s+(/usr/share/applications/.+\.desktop)')
        self._re_desktop_file_fields = re.compile('(Exec|TryExec|Icon|Categories|NoDisplay|Terminal)\s*=\s*(.+)')
        self._workers = workers

    def _read_file(self, file_path: str) -> Optional[str]:
        try:
            with open(file_path) as file:
                return file.read()
        except (FileNotFoundError, OSError) as e:
            self._log.error(f"Error when checking desktop file '{file_path}' ({file_path}):"
                            f" {e.__class__.__name__}")

    def _add_if_application_desktop_file(self, pkg_name: str, desktop_files: Iterable[str], output: Set[DebianApplication]):
        for file_path in sorted(desktop_files):
            content = self._read_file(file_path)

            if content:
                data = {}

                gui_app = True

                for f, v in self._re_desktop_file_fields.findall(content):
                    if f in ('NoDisplay', 'Terminal') and v.strip().lower() == 'true':
                        gui_app = False
                        break

                    if f not in data:
                        data[f.strip()] = v.strip()

                if not gui_app:
                    continue

                exe = data.get('Exec')

                if not exe:
                    exe = data.get('TryExec')

                if not exe:
                    continue

                icon = data.get('Icon')

                if not icon:
                    continue

                categories = data.get('Categories')

                if categories:
                    categories = tuple(sorted({c.strip() for c in categories.split(';') if c}))

                output.add(DebianApplication(name=pkg_name, exe_path=exe, icon_path=icon, categories=categories))
                break

    def map_executable_applications(self) -> Optional[Set[DebianApplication]]:
        exitcode, output = system.execute('dpkg-query -S .desktop', shell=True)

        if exitcode == 0 and output:

            pkg_files = dict()

            for found in self._re_desktop_file.findall(output):
                pkg_name = found[0].strip()
                files = pkg_files.get(pkg_name)

                if files is None:
                    files = set()
                    pkg_files[pkg_name] = files

                files.add(found[1].strip())

            if pkg_files:
                apps_found, check_jobs = set(), []

                with ThreadPoolExecutor(self._workers) as pool:
                    for pkg_name, files in pkg_files.items():
                        check_jobs.append(pool.submit(self._add_if_application_desktop_file,
                                                      pkg_name, files, apps_found))

                for job in check_jobs:
                    job.done()

                return apps_found
