import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Set, Type, List

from colorama import Fore

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SearchResult
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageHistory, PackageUpdate, PackageSuggestion, \
    SuggestionPriority
from bauh.api.abstract.view import MessageType
from bauh.api.constants import HOME_PATH
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, new_subprocess, ProcessHandler, run_cmd, SimpleProcess
from bauh.gems.appimage import query, INSTALLATION_PATH, LOCAL_PATH, SUGGESTIONS_FILE
from bauh.gems.appimage.config import read_config
from bauh.gems.appimage.model import AppImage
from bauh.gems.appimage.query import FIND_APPS_BY_NAME, FIND_APPS_BY_NAME_ONLY_NAME
from bauh.gems.appimage.worker import DatabaseUpdater

DB_APPS_PATH = '{}/{}'.format(HOME_PATH, '.local/share/bauh/appimage/apps.db')
DB_RELEASES_PATH = '{}/{}'.format(HOME_PATH, '.local/share/bauh/appimage/releases.db')

DESKTOP_ENTRIES_PATH = '{}/.local/share/applications'.format(HOME_PATH)

RE_DESKTOP_EXEC = re.compile(r'Exec\s*=\s*.+\n')
RE_DESKTOP_ICON = re.compile(r'Icon\s*=\s*.+\n')
RE_ICON_ENDS_WITH = re.compile(r'.+\.(png|svg)$')


class AppImageManager(SoftwareManager):

    def __init__(self, context: ApplicationContext):
        super(AppImageManager, self).__init__(context=context)
        self.i18n = context.i18n
        self.api_cache = context.cache_factory.new()
        context.disk_loader_factory.map(AppImageManager, self.api_cache)
        self.enabled = True
        self.http_client = context.http_client
        self.logger = context.logger
        self.file_downloader = context.file_downloader
        self.db_locks = {DB_APPS_PATH: Lock(), DB_RELEASES_PATH: Lock()}

    def _get_db_connection(self, db_path: str) -> sqlite3.Connection:
        if os.path.exists(db_path):
            self.db_locks[db_path].acquire()
            return sqlite3.connect(db_path)
        else:
            self.logger.warning("Could not get a database connection. File '{}' not found".format(db_path))

    def _close_connection(self, db_path: str, con: sqlite3.Connection):
        con.close()
        self.db_locks[db_path].release()

    def _gen_app_key(self, app: AppImage):
        return '{}{}'.format(app.name.lower(), app.github.lower() if app.github else '')

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        if is_url:
            return SearchResult([], [], 0)

        res = SearchResult([], [], 0)
        connection = self._get_db_connection(DB_APPS_PATH)

        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute(query.SEARCH_APPS_BY_NAME_OR_DESCRIPTION.format(words, words))

                found_map = {}
                idx = 0
                for l in cursor.fetchall():
                    app = AppImage(*l)
                    res.new.append(app)
                    found_map[self._gen_app_key(app)] = {'app': app, 'idx': idx}
                    idx += 1

            finally:
                self._close_connection(DB_APPS_PATH, connection)

            if res.new:
                installed = self.read_installed(disk_loader, limit, only_apps=False, pkg_types=None, internet_available=True).installed

                if installed:
                    for iapp in installed:
                        key = self._gen_app_key(iapp)

                        new_found = found_map.get(key)

                        if new_found:
                            del res.new[new_found['idx']]
                            res.installed.append(iapp)

        res.total = len(res.installed) + len(res.new)
        return res

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False,
                       pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None, connection: sqlite3.Connection = None) -> SearchResult:
        res = SearchResult([], [], 0)

        if os.path.exists(INSTALLATION_PATH):
            installed = run_cmd('ls {}*/data.json'.format(INSTALLATION_PATH), print_error=False)

            if installed:
                names = set()
                for path in installed.split('\n'):
                    if path:
                        with open(path) as f:
                            app = AppImage(installed=True, **json.loads(f.read()))
                            app.icon_url = app.icon_path

                        res.installed.append(app)
                        names.add("'{}'".format(app.name.lower()))

                if res.installed:
                    con = self._get_db_connection(DB_APPS_PATH) if not connection else connection

                    if con:
                        try:
                            cursor = con.cursor()
                            cursor.execute(query.FIND_APPS_BY_NAME.format(','.join(names)))

                            for tup in cursor.fetchall():
                                for app in res.installed:
                                    if app.name.lower() == tup[0].lower() and (not app.github or app.github.lower() == tup[1].lower()):
                                        app.update = tup[2] > app.version

                                        if app.update:
                                            app.latest_version = tup[2]
                                            app.url_download_latest_version = tup[3]

                                        break
                        except:
                            traceback.print_exc()
                        finally:
                            if not connection:
                                self._close_connection(DB_APPS_PATH, con)

        res.total = len(res.installed)
        return res

    def downgrade(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher) -> bool:
        versions = self.get_history(pkg)

        if len(versions.history) == 1:
            watcher.show_message(title=self.i18n['appimage.downgrade.impossible.title'],
                                 body=self.i18n['appimage.downgrade.impossible.body'].format(bold(pkg.name)),
                                 type_=MessageType.ERROR)
            return False
        elif versions.pkg_status_idx == -1:
            watcher.show_message(title=self.i18n['appimage.downgrade.impossible.title'],
                                 body=self.i18n['appimage.downgrade.unknown_version.body'].format(bold(pkg.name)),
                                 type_=MessageType.ERROR)
            return False
        elif versions.pkg_status_idx == len(versions.history) - 1:
            watcher.show_message(title=self.i18n['appimage.downgrade.impossible.title'],
                                 body=self.i18n['appimage.downgrade.first_version'].format(bold(pkg.name)),
                                 type_=MessageType.ERROR)
            return False
        else:
            if self.uninstall(pkg, root_password, watcher):
                old_release = versions.history[versions.pkg_status_idx + 1]
                pkg.version = old_release['0_version']
                pkg.latest_version = pkg.version
                pkg.url_download = old_release['2_url_download']
                if self.install(pkg, root_password, watcher):
                    self.cache_to_disk(pkg, None, False)
                    return True
                else:
                    watcher.show_message(title=self.i18n['error'],
                                         body=self.i18n['appimage.downgrade.install_version'].format(bold(pkg.version), bold(pkg.url_download)),
                                         type_=MessageType.ERROR)
            else:
                watcher.show_message(title=self.i18n['error'],
                                     body=self.i18n['appimage.error.uninstall_current_version'].format(bold(pkg.name)),
                                     type_=MessageType.ERROR)

            return False

    def update(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher) -> bool:
        if not self.uninstall(pkg, root_password, watcher):
            watcher.show_message(title=self.i18n['error'],
                                 body=self.i18n['appimage.error.uninstall_current_version'],
                                 type_=MessageType.ERROR)
            return False

        if self.install(pkg, root_password, watcher):
            self.cache_to_disk(pkg, None, False)
            return True

        return False

    def uninstall(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher) -> bool:
        if os.path.exists(pkg.get_disk_cache_path()):
            handler = ProcessHandler(watcher)

            if not handler.handle(SystemProcess(new_subprocess(['rm', '-rf', pkg.get_disk_cache_path()]))):
                watcher.show_message(title=self.i18n['error'], body=self.i18n['appimage.uninstall.error.remove_folder'].format(bold(pkg.get_disk_cache_path())))
                return False

            de_path = self._gen_desktop_entry_path(pkg)
            if os.path.exists(de_path):
                os.remove(de_path)

        return True

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        return {AppImage}

    def clean_cache_for(self, pkg: AppImage):
        pass

    def get_info(self, pkg: AppImage) -> dict:
        data = pkg.get_data_to_cache()

        if data.get('url_download'):
            size = self.http_client.get_content_length(data['url_download'])
            if size:
                data['size'] = size

        return data

    def get_history(self, pkg: AppImage) -> PackageHistory:
        history = []
        res = PackageHistory(pkg, history, -1)

        connection = self._get_db_connection(DB_APPS_PATH)

        if connection:
            try:
                cursor = connection.cursor()

                cursor.execute(query.FIND_APP_ID_BY_NAME_AND_GITHUB.format(pkg.name.lower(), pkg.github.lower() if pkg.github else ''))
                app_tuple = cursor.fetchone()

                if not app_tuple:
                    raise Exception("Could not retrieve {} from the database {}".format(pkg, DB_APPS_PATH))
            finally:
                self._close_connection(DB_APPS_PATH, connection)

            connection = self._get_db_connection(DB_RELEASES_PATH)

            if connection:
                try:
                    cursor = connection.cursor()

                    releases = cursor.execute(query.FIND_RELEASES_BY_APP_ID.format(app_tuple[0]))

                    if releases:
                        for idx, tup in enumerate(releases):
                            history.append({'0_version': tup[0], '1_published_at': datetime.strptime(tup[2], '%Y-%m-%dT%H:%M:%SZ') if tup[2] else '', '2_url_download': tup[1]})

                            if res.pkg_status_idx == -1 and pkg.version == tup[0]:
                                res.pkg_status_idx = idx

                finally:
                    self._close_connection(DB_RELEASES_PATH, connection)

        return res

    def _find_desktop_file(self, folder: str) -> str:
        for r, d, files in os.walk(folder):
            for f in files:
                if f.endswith('.desktop'):
                    return f

    def _find_appimage_file(self, folder: str) -> str:
        for r, d, files in os.walk(folder):
            for f in files:
                if f.lower().endswith('.appimage'):
                    return '{}/{}'.format(folder, f)

    def _find_icon_file(self, folder: str) -> str:
        for r, d, files in os.walk(folder):
            for f in files:
                if RE_ICON_ENDS_WITH.match(f):
                    return f

    def install(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher) -> bool:
        handler = ProcessHandler(watcher)
        out_dir = INSTALLATION_PATH + pkg.name.lower()
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        appimage_url = pkg.url_download_latest_version if pkg.update else pkg.url_download
        file_name = appimage_url.split('/')[-1]
        pkg.version = pkg.latest_version
        pkg.url_download = appimage_url

        file_path = out_dir + '/' + file_name
        downloaded = self.file_downloader.download(file_url=pkg.url_download, watcher=watcher,
                                                   output_path=file_path, cwd=HOME_PATH)

        if downloaded:
            watcher.change_substatus(self.i18n['appimage.install.permission'].format(bold(file_name)))
            permission_given = handler.handle(SystemProcess(new_subprocess(['chmod', 'a+x', file_path])))

            if permission_given:

                watcher.change_substatus(self.i18n['appimage.install.extract'].format(bold(file_name)))

                try:
                    res, output = handler.handle_simple(SimpleProcess([file_path, '--appimage-extract'], cwd=out_dir))

                    if 'Error: Failed to register AppImage in AppImageLauncherFS' in output:
                        watcher.show_message(title=self.i18n['error'],
                                             body=self.i18n['appimage.install.appimagelauncher.error'].format(appimgl=bold('AppImageLauncher'), app=bold(pkg.name)),
                                             type_=MessageType.ERROR)
                        handler.handle(SystemProcess(new_subprocess(['rm', '-rf', out_dir])))
                        return False
                except:
                    watcher.show_message(title=self.i18n['error'],
                                         body=traceback.format_exc(),
                                         type_=MessageType.ERROR)
                    traceback.print_exc()
                    handler.handle(SystemProcess(new_subprocess(['rm', '-rf', out_dir])))
                    return False

                watcher.change_substatus(self.i18n['appimage.install.desktop_entry'])
                extracted_folder = '{}/{}'.format(out_dir, 'squashfs-root')

                if os.path.exists(extracted_folder):
                    desktop_entry = self._find_desktop_file(extracted_folder)

                    with open('{}/{}'.format(extracted_folder, desktop_entry)) as f:
                        de_content = f.read()

                    de_content = RE_DESKTOP_EXEC.sub('Exec={}\n'.format(file_path), de_content)

                    extracted_icon = self._find_icon_file(extracted_folder)

                    if extracted_icon:
                        icon_path = out_dir + '/logo.' + extracted_icon.split('.')[-1]
                        shutil.copy('{}/{}'.format(extracted_folder, extracted_icon), icon_path)
                        de_content = RE_DESKTOP_ICON.sub('Icon={}\n'.format(icon_path), de_content)
                        pkg.icon_path = icon_path

                    Path(DESKTOP_ENTRIES_PATH).mkdir(parents=True, exist_ok=True)

                    with open(self._gen_desktop_entry_path(pkg), 'w+') as f:
                        f.write(de_content)

                    shutil.rmtree(extracted_folder)
                    return True
                else:
                    watcher.show_message(title=self.i18n['error'],
                                         body='Could extract content from {}'.format(bold(file_name)),
                                         type_=MessageType.ERROR)
        else:
            watcher.show_message(title=self.i18n['error'],
                                 body=self.i18n['appimage.install.download.error'].format(bold(pkg.url_download)),
                                 type_=MessageType.ERROR)

        handler.handle(SystemProcess(new_subprocess(['rm', '-rf', out_dir])))
        return False

    def _gen_desktop_entry_path(self, app: AppImage) -> str:
        return '{}/bauh_appimage_{}.desktop'.format(DESKTOP_ENTRIES_PATH, app.name.lower())

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def _is_sqlite3_available(self):
        res = run_cmd('which sqlite3')
        return res and not res.strip().startswith('which ')

    def _is_wget_available(self):
        res = run_cmd('which wget')
        return res and not res.strip().startswith('which ')

    def _is_aria2_available(self):
        res = run_cmd('which aria2c')
        return res and not res.strip().startswith('which ')

    def can_work(self) -> bool:
        return self._is_sqlite3_available() and (self._is_wget_available() or self._is_aria2_available())

    def requires_root(self, action: str, pkg: AppImage):
        return False

    def _start_updater(self):
        local_config = read_config(update_file=True)
        interval = local_config['db_updater']['interval'] or 20 * 60

        updater = DatabaseUpdater(http_client=self.context.http_client, logger=self.context.logger,
                                  db_locks=self.db_locks, interval=interval)
        if local_config['db_updater']['enabled']:
            updater.start()
        else:
            updater.download_databases()  # only once

    def prepare(self):
        Thread(target=self._start_updater, daemon=True).start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        res = self.read_installed(disk_loader=None, internet_available=internet_available)

        updates = []
        if res.installed:
            for app in res.installed:
                if app.update:
                    updates.append(PackageUpdate(pkg_id=app.name, pkg_type='appimage', version=app.latest_version))

        return updates

    def list_warnings(self, internet_available: bool) -> List[str]:
        pass

    def list_suggestions(self, limit: int, filter_installed: bool) -> List[PackageSuggestion]:
        res = []

        connection = self._get_db_connection(DB_APPS_PATH)

        if connection:
            file = self.http_client.get(SUGGESTIONS_FILE)

            if not file or not file.text:
                self.logger.warning("No suggestion found in {}".format(SUGGESTIONS_FILE))
                return res
            else:
                self.logger.info("Mapping suggestions")
                try:
                    sugs = [l for l in file.text.split('\n') if l]

                    if filter_installed:
                        installed = {i.name.lower() for i in self.read_installed(disk_loader=None, connection=connection).installed}
                    else:
                        installed = None

                    sugs_map = {}

                    for s in sugs:
                        lsplit = s.split('=')

                        name = lsplit[1].strip()

                        if limit <= 0 or len(sugs_map) < limit:
                            if not installed or not name.lower() in installed:
                                sugs_map[name] = SuggestionPriority(int(lsplit[0]))
                        else:
                            break

                    cursor = connection.cursor()
                    cursor.execute(query.FIND_APPS_BY_NAME_FULL.format(','.join(["'{}'".format(s) for s in sugs_map.keys()])))

                    for t in cursor.fetchall():
                        app = AppImage(*t)
                        res.append(PackageSuggestion(app, sugs_map[app.name.lower()]))
                    self.logger.info("Mapped {} suggestions".format(len(res)))
                except:
                    traceback.print_exc()
                finally:
                    self._close_connection(DB_APPS_PATH, connection)

        return res

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: AppImage):
        installation_dir = pkg.get_disk_cache_path()
        if os.path.exists(installation_dir):
            appimag_path = self._find_appimage_file(installation_dir)

            if appimag_path:
                subprocess.Popen([appimag_path])
            else:
                self.logger.error("Could not find the AppImage file of '{}' in '{}'".format(pkg.name, installation_dir))

    def cache_to_disk(self, pkg: SoftwarePackage, icon_bytes: bytes, only_icon: bool):
        self.serialize_to_disk(pkg, icon_bytes, only_icon)

    def get_screenshots(self, pkg: AppImage) -> List[str]:
        if pkg.has_screenshots():
            return [pkg.url_screenshot]

        return []

    def clear_data(self):
        for f in glob.glob('{}/*.db'.format(LOCAL_PATH)):
            try:
                print('[bauh][appimage] Deleting {}'.format(f))
                os.remove(f)
                print('{}[bauh][appimage] {} deleted{}'.format(Fore.YELLOW, f, Fore.RESET))
            except:
                print('{}[bauh][appimage] An exception has happened when deleting {}{}'.format(Fore.RED, Fore.RESET))
                traceback.print_exc()
