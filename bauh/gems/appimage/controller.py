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
from typing import Set, Type, List, Tuple, Optional, Iterable, Generator

from colorama import Fore
from packaging.version import LegacyVersion
from packaging.version import parse as parse_version

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SearchResult, UpgradeRequirements, UpgradeRequirement, \
    TransactionResult, SoftwareAction, SettingsView, SettingsController
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import SoftwarePackage, PackageHistory, PackageUpdate, PackageSuggestion, \
    SuggestionPriority, CustomSoftwareAction
from bauh.api.abstract.view import MessageType, FormComponent, InputOption, SingleSelectComponent, \
    SelectViewType, TextInputComponent, PanelComponent, FileChooserComponent, ViewObserver
from bauh.api.paths import DESKTOP_ENTRIES_DIR
from bauh.commons import resource
from bauh.commons.boot import CreateConfigFile
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, new_subprocess, ProcessHandler, SimpleProcess
from bauh.gems.appimage import query, INSTALLATION_DIR, APPIMAGE_SHARED_DIR, ROOT_DIR, \
    APPIMAGE_CONFIG_DIR, UPDATES_IGNORED_FILE, util, get_default_manual_installation_file_dir, DATABASE_APPS_FILE, \
    DATABASE_RELEASES_FILE, APPIMAGE_CACHE_DIR, get_icon_path, DOWNLOAD_DIR
from bauh.gems.appimage.config import AppImageConfigManager
from bauh.gems.appimage.model import AppImage
from bauh.gems.appimage.util import replace_desktop_entry_exec_command
from bauh.gems.appimage.worker import DatabaseUpdater, SymlinksVerifier, AppImageSuggestionsDownloader

RE_DESKTOP_ICON = re.compile(r'Icon\s*=\s*.+\n')
RE_ICON_ENDS_WITH = re.compile(r'.+\.(png|svg)$')
RE_APPIMAGE_NAME = re.compile(r'(.+)\.appimage', flags=re.IGNORECASE)


class ManualInstallationFileObserver(ViewObserver):

    def __init__(self, name: Optional[TextInputComponent], version: TextInputComponent):
        self.name = name
        self.version = version

    def on_change(self, file_path: str):
        if file_path:
            name_found = RE_APPIMAGE_NAME.findall(file_path.split('/')[-1])

            if name_found:
                name_split = name_found[0].split('-')

                if self.name:
                    self.name.set_value(name_split[0].strip())

                if len(name_split) > 1:
                    self.version.set_value(name_split[1].strip())
        else:
            if self.name:
                self.name.set_value(None)

            self.version.set_value(None)


class AppImageManager(SoftwareManager, SettingsController):

    def __init__(self, context: ApplicationContext):
        super(AppImageManager, self).__init__(context=context)
        self.i18n = context.i18n
        self.api_cache = context.cache_factory.new()
        context.disk_loader_factory.map(AppImage, self.api_cache)
        self.enabled = True
        self.http_client = context.http_client
        self.logger = context.logger
        self.file_downloader = context.file_downloader
        self.configman = AppImageConfigManager()
        self._custom_actions: Optional[Iterable[CustomSoftwareAction]] = None
        self._action_self_install: Optional[CustomSoftwareAction] = None
        self._app_github: Optional[str] = None
        self._search_unfilled_attrs: Optional[Tuple[str, ...]] = None
        self._suggestions_downloader: Optional[AppImageSuggestionsDownloader] = None

    def install_file(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        max_width = 350
        file_chooser = FileChooserComponent(label=self.i18n['file'].capitalize(),
                                            allowed_extensions={'AppImage', '*'},
                                            search_path=get_default_manual_installation_file_dir(),
                                            max_width=max_width)
        input_name = TextInputComponent(label=self.i18n['name'].capitalize(), max_width=max_width)
        input_version = TextInputComponent(label=self.i18n['version'].capitalize(), max_width=max_width)
        file_chooser.observers.append(ManualInstallationFileObserver(input_name, input_version))

        input_description = TextInputComponent(label=self.i18n['description'].capitalize(), max_width=max_width)

        cat_ops = [InputOption(label=self.i18n['category.none'].capitalize(), value=0)]
        cat_ops.extend([InputOption(label=self.i18n.get(f'category.{c.lower()}', c.lower()).capitalize(), value=c) for c in self.context.default_categories])
        inp_cat = SingleSelectComponent(label=self.i18n['category'], type_=SelectViewType.COMBO, options=cat_ops,
                                        default_option=cat_ops[0], max_width=max_width)

        form = FormComponent(label='', components=[file_chooser, input_name, input_version, input_description, inp_cat],
                             spaces=False)

        while True:
            if watcher.request_confirmation(title=self.i18n['appimage.custom_action.install_file.details'], body=None,
                                            components=[form],
                                            confirmation_label=self.i18n['proceed'].capitalize(),
                                            deny_label=self.i18n['cancel'].capitalize(),
                                            min_height=100, max_width=max_width + 150):
                if not file_chooser.file_path or not os.path.isfile(file_chooser.file_path) or not file_chooser.file_path.lower().strip().endswith('.appimage'):
                    watcher.request_confirmation(title=self.i18n['error'].capitalize(),
                                                 body=self.i18n['appimage.custom_action.install_file.invalid_file'],
                                                 deny_button=False)
                elif not input_name.get_value() or not input_name.get_value().strip():
                    watcher.request_confirmation(title=self.i18n['error'].capitalize(),
                                                 body=self.i18n['appimage.custom_action.install_file.invalid_name'],
                                                 deny_button=False)
                else:
                    break
            else:
                return False

        appim = AppImage(i18n=self.i18n, imported=True)
        appim.name = input_name.get_value().strip()
        appim.local_file_path = file_chooser.file_path
        appim.version = input_version.get_value()
        appim.latest_version = input_version.get_value()
        appim.description = input_description.get_value()
        appim.categories = ['Imported']

        if inp_cat.get_selected() != cat_ops[0].value:
            appim.categories.append(inp_cat.get_selected())

        res = self.install(root_password=root_password, pkg=appim, disk_loader=None, watcher=watcher).success

        if res:
            appim.installed = True
            self.cache_to_disk(appim, None, False)

        return res

    def update_file(self, pkg: AppImage, root_password: Optional[str], watcher: ProcessWatcher):
        max_width = 350
        file_chooser = FileChooserComponent(label=self.i18n['file'].capitalize(),
                                            allowed_extensions={'AppImage', '*'},
                                            search_path=get_default_manual_installation_file_dir(),
                                            max_width=max_width)
        input_version = TextInputComponent(label=self.i18n['version'].capitalize(), max_width=max_width)
        file_chooser.observers.append(ManualInstallationFileObserver(None, input_version))

        while True:
            if watcher.request_confirmation(title=self.i18n['appimage.custom_action.manual_update.details'], body=None,
                                            components=[FormComponent(label='', components=[file_chooser, input_version], spaces=False)],
                                            confirmation_label=self.i18n['proceed'].capitalize(),
                                            deny_label=self.i18n['cancel'].capitalize(),
                                            min_height=100, max_width=max_width + 150):

                if not file_chooser.file_path or not os.path.isfile(file_chooser.file_path) or not file_chooser.file_path.lower().strip().endswith('.appimage'):
                    watcher.request_confirmation(title=self.i18n['error'].capitalize(),
                                                 body=self.i18n['appimage.custom_action.install_file.invalid_file'],
                                                 deny_button=False)
                else:
                    break
            else:
                return False

        pkg.local_file_path = file_chooser.file_path
        pkg.version = input_version.get_value()

        reqs = UpgradeRequirements(to_install=None, to_remove=None, to_upgrade=[UpgradeRequirement(pkg=pkg)], cannot_upgrade=None)
        return self.upgrade(reqs, root_password=root_password, watcher=watcher)

    def _get_db_connection(self, db_path: str) -> sqlite3.Connection:
        if os.path.exists(db_path):
            try:
                return sqlite3.connect(db_path)
            except:
                self.logger.error(f"Could not connect to database file '{db_path}'")
                traceback.print_exc()
        else:
            self.logger.warning(f"Could not get a connection for database '{db_path}'")

    def _gen_app_key(self, app: AppImage):
        return f"{app.name.lower()}{app.github.lower() if app.github else ''}"

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        if is_url:
            return SearchResult.empty()

        apps_conn = self._get_db_connection(DATABASE_APPS_FILE)

        if not apps_conn:
            return SearchResult.empty()

        not_installed, found_map = [], {}

        try:
            cursor = apps_conn.cursor()
            cursor.execute(query.SEARCH_APPS_BY_NAME_OR_DESCRIPTION.format(words, words))

            idx = 0
            for r in cursor.fetchall():
                app = AppImage(*r, i18n=self.i18n)
                not_installed.append(app)
                found_map[self._gen_app_key(app)] = {'app': app, 'idx': idx}
                idx += 1
        except:
            self.logger.error("An exception happened while querying the 'apps' database")
            traceback.print_exc()

        try:
            installed = self.read_installed(connection=apps_conn, disk_loader=disk_loader, limit=limit, only_apps=False, pkg_types=None, internet_available=True).installed
        except:
            installed = None

        installed_found = []

        if installed:
            lower_words = words.lower()
            for appim in installed:
                found = False

                if not_installed and found_map:
                    key = self._gen_app_key(appim)
                    new_found = found_map.get(key)

                    if new_found:
                        if not appim.imported:
                            for attr in self.search_unfilled_attrs:
                                if getattr(appim, attr) is None:
                                    setattr(appim, attr, getattr(new_found['app'], attr))

                        del not_installed[new_found['idx']]
                        installed_found.append(appim)
                        found = True

                if not found and (lower_words in appim.name.lower() or (appim.description and lower_words in appim.description.lower())):
                    installed_found.append(appim)
        try:
            apps_conn.close()
        except:
            self.logger.error(f"An exception happened when trying to close the connection to database file '{DATABASE_APPS_FILE}'")
            traceback.print_exc()

        return SearchResult(new=not_installed, installed=installed_found, total=len(not_installed) + len(installed_found))

    def read_installed(self, disk_loader: Optional[DiskCacheLoader], limit: int = -1, only_apps: bool = False,
                       pkg_types: Optional[Set[Type[SoftwarePackage]]] = None, internet_available: bool = None, connection: sqlite3.Connection = None) -> SearchResult:
        installed_apps = []
        res = SearchResult(installed_apps, [], 0)

        if os.path.exists(INSTALLATION_DIR):
            installed = glob.glob(f'{INSTALLATION_DIR}/*/data.json')

            if installed:
                names = set()
                for path in installed:
                    if path:
                        with open(path) as f:
                            app = AppImage(installed=True, i18n=self.i18n, **json.loads(f.read()))
                            app.icon_url = app.icon_path

                        installed_apps.append(app)
                        names.add(f"'{app.name.lower()}'")

                if installed_apps:
                    apps_con = self._get_db_connection(DATABASE_APPS_FILE) if not connection else connection

                    if apps_con:
                        try:
                            cursor = apps_con.cursor()
                            cursor.execute(query.FIND_APPS_BY_NAME.format(','.join(names)))

                            for tup in cursor.fetchall():
                                for app in installed_apps:
                                    if app.name.lower() == tup[0].lower() and (not app.github or app.github.lower() == tup[1].lower()):
                                        continuous_version = app.version == 'continuous'
                                        continuous_update = tup[2] == 'continuous'

                                        if tup[3]:
                                            if continuous_version and not continuous_update:
                                                app.update = True
                                            elif continuous_update and not continuous_version:
                                                app.update = False
                                            else:
                                                try:
                                                    app.update = parse_version(tup[2]) > parse_version(app.version) if tup[2] else False
                                                except:
                                                    app.update = False
                                                    traceback.print_exc()

                                        if app.update:
                                            app.latest_version = tup[2]
                                            app.url_download_latest_version = tup[3]

                                        break
                        except:
                            self.logger.error(f"An exception happened while querying the database file '{DATABASE_APPS_FILE}'")
                            traceback.print_exc()
                        finally:
                            if not connection:  # the connection can only be closed if it was opened within this method
                                apps_con.close()

                    ignored_updates = self._read_ignored_updates()

                    if ignored_updates:
                        for app in installed_apps:
                            if app.supports_ignored_updates() and app.name in ignored_updates:
                                app.updates_ignored = True

        res.total = len(res.installed)
        return res

    def downgrade(self, pkg: AppImage, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
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
            old_release = versions.history[versions.pkg_status_idx + 1]
            pkg.version = old_release['0_version']
            pkg.latest_version = pkg.version
            pkg.url_download = old_release['2_url_download']

            download_data = self._download(pkg=pkg, watcher=watcher)

            if not download_data:
                return False

            if self.uninstall(pkg, root_password, watcher).success:
                if self._install(pkg=pkg, watcher=watcher, pre_downloaded_file=download_data).success:
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

    def upgrade(self, requirements: UpgradeRequirements, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        not_upgraded = []

        for req in requirements.to_upgrade:
            watcher.change_status(f"{self.i18n['manage_window.status.upgrading']} {req.pkg.name} ({req.pkg.version})...")

            download_data = None

            if not req.pkg.imported:
                download_data = self._download(req.pkg, watcher)

                if not download_data:
                    not_upgraded.append(req.pkg)
                    watcher.change_substatus('')
                    continue

            if not self.uninstall(req.pkg, root_password, watcher).success:
                not_upgraded.append(req.pkg)
                watcher.change_substatus('')
                continue

            if not self._install(pkg=req.pkg, watcher=watcher, pre_downloaded_file=download_data).success:
                not_upgraded.append(req.pkg)
                watcher.change_substatus('')
                continue

            self.cache_to_disk(req.pkg, None, False)

        all_failed = len(not_upgraded) == len(requirements.to_upgrade)

        if not_upgraded:
            pkgs_str = ''.join((f'<li>{app.name}</li>' for app in not_upgraded))
            watcher.show_message(title=self.i18n['error' if all_failed else 'warning'].capitalize(),
                                 body=self.i18n['appimage.upgrade.failed'].format(apps=f'<ul>{pkgs_str}</ul>'),
                                 type_=MessageType.ERROR if all_failed else MessageType.WARNING)

        watcher.change_substatus('')
        return not all_failed

    def uninstall(self, pkg: AppImage, root_password: Optional[str], watcher: ProcessWatcher, disk_loader: DiskCacheLoader = None) -> TransactionResult:
        if os.path.exists(pkg.get_disk_cache_path()):
            handler = ProcessHandler(watcher)

            if not handler.handle(SystemProcess(new_subprocess(['rm', '-rf', pkg.get_disk_cache_path()]))):
                watcher.show_message(title=self.i18n['error'], body=self.i18n['appimage.uninstall.error.remove_folder'].format(bold(pkg.get_disk_cache_path())))
                return TransactionResult.fail()

            de_path = self._gen_desktop_entry_path(pkg)
            if os.path.exists(de_path):
                os.remove(de_path)

            self.revert_ignored_update(pkg)

        if pkg.symlink and os.path.islink(pkg.symlink):
            self.logger.info(f"Removing symlink '{pkg.symlink}'")

            try:
                os.remove(pkg.symlink)
                self.logger.info(f"symlink '{pkg.symlink}' successfully removed")
            except:
                msg = f"could not remove symlink '{pkg.symlink}'"
                self.logger.error(msg)

                if watcher:
                    watcher.print(f"[error] {msg}")

        self._add_self_latest_version(pkg)  # only for self installation
        return TransactionResult(success=True, installed=None, removed=[pkg])

    def _add_self_latest_version(self, app: AppImage):
        if app.name == self.context.app_name and app.github == self.app_github and not app.url_download_latest_version:
            history = self.get_history(app)

            if not history or not history.history:
                self.logger.warning(f"Could not retrieve '{app.name}' versions. "
                                    f"It will not be possible to determine the current latest version")
            else:
                app.version = history.history[0]['0_version']
                app.latest_version = app.version
                app.url_download = history.history[0]['2_url_download']
                app.url_download_latest_version = app.url_download

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        return {AppImage}

    def clean_cache_for(self, pkg: AppImage):
        pass

    def get_info(self, pkg: AppImage) -> dict:
        data = pkg.get_data_to_cache()

        if not pkg.installed:
            for key in ('install_dir', 'symlink', 'icon_path'):
                if key in data:
                    del data[key]

        if data.get('url_download'):
            size = self.http_client.get_content_length(data['url_download'])
            if size:
                data['size'] = size

        categories = data.get('categories')

        if categories:
            data['categories'] = [self.i18n.get(f'category.{c.lower()}', self.i18n.get(c, c)).capitalize() for c in data['categories']]

        if data.get('symlink') and not os.path.islink(data['symlink']):
            del data['symlink']

        return data

    def _sort_release(self, rel: tuple):
        return rel[0]

    def get_history(self, pkg: AppImage) -> PackageHistory:
        history = []
        res = PackageHistory(pkg, history, -1)

        app_con = self._get_db_connection(DATABASE_APPS_FILE)

        if not app_con:
            return res

        try:
            cursor = app_con.cursor()

            cursor.execute(query.FIND_APP_ID_BY_NAME_AND_GITHUB.format(pkg.name.lower(), pkg.github.lower() if pkg.github else ''))
            app_tuple = cursor.fetchone()

            if not app_tuple:
                self.logger.warning(f"Could not retrieve {pkg} from the database '{DATABASE_APPS_FILE}'")
                return res
        except:
            self.logger.error(f"An exception happened while querying the database file '{DATABASE_APPS_FILE}'")
            traceback.print_exc()
            app_con.close()
            return res

        app_con.close()

        releases_con = self._get_db_connection(DATABASE_RELEASES_FILE)

        if not releases_con:
            return res

        try:
            cursor = releases_con.cursor()

            releases = cursor.execute(query.FIND_RELEASES_BY_APP_ID.format(app_tuple[0]))

            if releases:
                treated_releases = [(LegacyVersion(r[0]), *r[1:]) for r in releases]
                treated_releases.sort(key=self._sort_release, reverse=True)

                for idx, tup in enumerate(treated_releases):
                    ver = str(tup[0])
                    history.append({'0_version': ver,
                                    '1_published_at': datetime.strptime(tup[2], '%Y-%m-%dT%H:%M:%SZ') if tup[
                                        2] else '', '2_url_download': tup[1]})

                    if res.pkg_status_idx == -1 and pkg.version == ver:
                        res.pkg_status_idx = idx

                return res
        except:
            self.logger.error(f"An exception happened while querying the database file '{DATABASE_RELEASES_FILE}'")
            traceback.print_exc()
        finally:
            releases_con.close()

    def _find_desktop_file(self, folder: str) -> Optional[str]:
        for r, d, files in os.walk(folder):
            for f in files:
                if f.endswith('.desktop'):
                    return f

    def _find_icon_file(self, folder: str) -> Optional[str]:
        for f in glob.glob(folder + ('/**' if not folder.endswith('/') else '**'), recursive=True):
            if RE_ICON_ENDS_WITH.match(f):
                return f

    def _download(self, pkg: AppImage, watcher: ProcessWatcher) -> Optional[Tuple[str, str]]:
        appimage_url = pkg.url_download_latest_version if pkg.update else pkg.url_download

        if not appimage_url:
            watcher.show_message(title=self.i18n['error'],
                                 body=self.i18n['appimage.download.no_url'].format(app=bold(pkg.name)),
                                 type_=MessageType.ERROR)
            return

        file_name = appimage_url.split('/')[-1]
        pkg.version = pkg.latest_version
        pkg.url_download = appimage_url

        try:
            Path(DOWNLOAD_DIR).mkdir(exist_ok=True, parents=True)
        except OSError:
            watcher.show_message(title=self.i18n['error'],
                                 body=self.i18n['error.mkdir'].format(dir=bold(DOWNLOAD_DIR)),
                                 type_=MessageType.ERROR)
            return

        file_path = f'{DOWNLOAD_DIR}/{file_name}'
        downloaded = self.file_downloader.download(file_url=pkg.url_download, watcher=watcher,
                                                   output_path=file_path, cwd=str(Path.home()))

        if not downloaded:
            watcher.show_message(title=self.i18n['error'],
                                 body=self.i18n['appimage.download.error'].format(bold(pkg.url_download)),
                                 type_=MessageType.ERROR)
            return

        return file_name, file_path

    def install(self, pkg: AppImage, root_password: Optional[str], disk_loader: Optional[DiskCacheLoader], watcher: ProcessWatcher) -> TransactionResult:
        return self._install(pkg=pkg, watcher=watcher)

    def _install(self, pkg: AppImage, watcher: ProcessWatcher, pre_downloaded_file: Optional[Tuple[str, str]] = None) \
            -> TransactionResult:

        handler = ProcessHandler(watcher)
        out_dir = f'{INSTALLATION_DIR}/{pkg.get_clean_name()}'
        counter = 0
        while True:
            if os.path.exists(out_dir):
                self.logger.info(f"Installation dir '{out_dir}' already exists. Generating a different one")
                out_dir += f'-{counter}'
                counter += 1
            else:
                break

        Path(out_dir).mkdir(parents=True, exist_ok=True)
        pkg.install_dir = out_dir

        if pkg.imported:

            downloaded, file_name = True, pkg.local_file_path.split('/')[-1]

            install_file_path = out_dir + '/' + file_name

            try:
                moved, output = handler.handle_simple(SimpleProcess(['mv', pkg.local_file_path, install_file_path]))
            except:
                output = ''
                self.logger.error(f"Could not rename file '{pkg.local_file_path}' as '{install_file_path}'")
                moved = False

            if not moved:
                watcher.show_message(title=self.i18n['error'].capitalize(),
                                     body=self.i18n['appimage.install.imported.rename_error'].format(bold(pkg.local_file_path.split('/')[-1]),
                                                                                                     bold(output)),
                                     type_=MessageType.ERROR)

                return TransactionResult.fail()

        else:
            download_data = pre_downloaded_file if pre_downloaded_file else self._download(pkg, watcher)

            if not download_data:
                return TransactionResult.fail()

            file_name, download_path = download_data[0], download_data[1]

            install_file_path = f'{out_dir}/{file_name}'

            try:
                shutil.move(download_path, install_file_path)
            except OSError:
                watcher.show_message(title=self.i18n['error'],
                                     body=self.i18n['error.mvfile'].formmat(src=bold(download_path),
                                                                            dest=bold(install_file_path)))
                return TransactionResult.fail()

        watcher.change_substatus(self.i18n['appimage.install.permission'].format(bold(file_name)))
        permission_given = handler.handle(SystemProcess(new_subprocess(['chmod', 'a+x', install_file_path])))

        if permission_given:

            watcher.change_substatus(self.i18n['appimage.install.extract'].format(bold(file_name)))

            try:
                res, output = handler.handle_simple(
                    SimpleProcess([install_file_path, '--appimage-extract'], cwd=out_dir))

                if 'Error: Failed to register AppImage in AppImageLauncherFS' in output:
                    watcher.show_message(title=self.i18n['error'],
                                         body=self.i18n['appimage.install.appimagelauncher.error'].format(
                                             appimgl=bold('AppImageLauncher'), app=bold(pkg.name)),
                                         type_=MessageType.ERROR)
                    handler.handle(SystemProcess(new_subprocess(['rm', '-rf', out_dir])))
                    return TransactionResult.fail()
            except:
                watcher.show_message(title=self.i18n['error'],
                                     body=traceback.format_exc(),
                                     type_=MessageType.ERROR)
                traceback.print_exc()
                handler.handle(SystemProcess(new_subprocess(['rm', '-rf', out_dir])))
                return TransactionResult.fail()

            watcher.change_substatus(self.i18n['appimage.install.desktop_entry'])
            extracted_folder = f'{out_dir}/squashfs-root'

            if os.path.exists(extracted_folder):
                desktop_entry = self._find_desktop_file(extracted_folder)

                with open(f'{extracted_folder}/{desktop_entry}') as f:
                    de_content = f.read()

                if de_content:
                    de_content = replace_desktop_entry_exec_command(desktop_entry=de_content,
                                                                    appname=pkg.name,
                                                                    file_path=install_file_path)
                extracted_icon = self._find_icon_file(extracted_folder)

                if extracted_icon:
                    icon_path = out_dir + '/logo.' + extracted_icon.split('/')[-1].split('.')[-1]
                    shutil.copy(extracted_icon, icon_path)

                    if de_content:
                        de_content = RE_DESKTOP_ICON.sub(f'Icon={icon_path}\n', de_content)

                    pkg.icon_path = icon_path

                if not de_content:
                    de_content = pkg.to_desktop_entry()

                Path(DESKTOP_ENTRIES_DIR).mkdir(parents=True, exist_ok=True)

                with open(self._gen_desktop_entry_path(pkg), 'w+') as f:
                    f.write(de_content)

                try:
                    shutil.rmtree(extracted_folder)
                except:
                    traceback.print_exc()

                SymlinksVerifier.create_symlink(app=pkg, file_path=install_file_path, logger=self.logger,
                                                watcher=watcher)
                return TransactionResult(success=True, installed=[pkg], removed=[])
            else:
                watcher.show_message(title=self.i18n['error'],
                                     body=f'Could extract content from {bold(file_name)}',
                                     type_=MessageType.ERROR)

        handler.handle(SystemProcess(new_subprocess(['rm', '-rf', out_dir])))
        return TransactionResult.fail()

    def _gen_desktop_entry_path(self, app: AppImage) -> str:
        return f'{DESKTOP_ENTRIES_DIR}/bauh_appimage_{app.get_clean_name()}.desktop'

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def _is_sqlite3_available(self) -> bool:
        return bool(shutil.which('sqlite3'))

    def can_work(self) -> Tuple[bool, Optional[str]]:
        if not self.context.is_system_x86_64():
            return False, self.i18n['message.requires_architecture'].format(arch=bold('x86_64'))

        if not self._is_sqlite3_available():
            return False, self.i18n['missing_dep'].format(dep=bold('sqlite3'))

        if not self.file_downloader.can_work():
            download_clients = ', '.join(self.file_downloader.get_supported_clients())
            return False, self.i18n['appimage.missing_downloader'].format(clients=download_clients)

        return True, None

    def requires_root(self, action: SoftwareAction, pkg: AppImage) -> bool:
        return False

    def prepare(self, task_manager: TaskManager, root_password: Optional[str], internet_available: bool):
        create_config = CreateConfigFile(taskman=task_manager, configman=self.configman, i18n=self.i18n,
                                         task_icon_path=get_icon_path(), logger=self.logger)
        create_config.start()

        symlink_check = SymlinksVerifier(taskman=task_manager, i18n=self.i18n, logger=self.logger)
        symlink_check.start()

        if internet_available:
            DatabaseUpdater(taskman=task_manager, i18n=self.context.i18n,
                            create_config=create_config, http_client=self.context.http_client,
                            logger=self.context.logger).start()

            if not self.suggestions_downloader.is_custom_local_file_mapped():
                self.suggestions_downloader.taskman = task_manager
                self.suggestions_downloader.create_config = create_config
                self.suggestions_downloader.register_task()
                self.suggestions_downloader.start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        res = self.read_installed(disk_loader=None, internet_available=internet_available)

        updates = []
        if res.installed:
            for app in res.installed:
                if app.update and not app.is_update_ignored():
                    updates.append(PackageUpdate(pkg_id=app.name, pkg_type='AppImage', version=app.latest_version, name=app.name))

        return updates

    def list_warnings(self, internet_available: bool) -> List[str]:
        dbfiles = glob.glob(f'{APPIMAGE_CACHE_DIR}/*.db')

        if not dbfiles or len({f for f in (DATABASE_APPS_FILE, DATABASE_RELEASES_FILE) if f in dbfiles}) != 2:
            return [self.i18n['appimage.warning.missing_db_files'].format(appimage=bold('AppImage'))]

    def list_suggestions(self, limit: int, filter_installed: bool) -> Optional[List[PackageSuggestion]]:
        if limit == 0:
            return

        connection = self._get_db_connection(DATABASE_APPS_FILE)

        if connection:
            self.suggestions_downloader.taskman = TaskManager()
            suggestions = tuple(self.suggestions_downloader.read())

            if not suggestions:
                self.logger.warning("Could not read AppImage suggestions")
                return
            else:
                self.logger.info("Mapping AppImage suggestions")
                try:
                    if filter_installed:
                        installed = {i.name.lower() for i in self.read_installed(disk_loader=None,
                                                                                 connection=connection).installed}
                    else:
                        installed = None

                    sugs_map = {}

                    for s in suggestions:
                        lsplit = s.split('=')

                        name = lsplit[1].strip()

                        if limit < 0 or len(sugs_map) < limit:
                            if not installed or not name.lower() in installed:
                                sugs_map[name] = SuggestionPriority(int(lsplit[0]))
                        else:
                            break

                    cursor = connection.cursor()
                    cursor.execute(query.FIND_APPS_BY_NAME_FULL.format(','.join([f"'{s}'" for s in sugs_map.keys()])))

                    res = []
                    for t in cursor.fetchall():
                        app = AppImage(*t, i18n=self.i18n)
                        res.append(PackageSuggestion(app, sugs_map[app.name.lower()]))

                    self.logger.info(f"Mapped {len(res)} AppImage suggestions")
                    return res
                except:
                    traceback.print_exc()
                finally:
                    connection.close()

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: AppImage):
        installation_dir = pkg.get_disk_cache_path()
        if os.path.exists(installation_dir):
            appimag_path = util.find_appimage_file(installation_dir)

            if appimag_path:
                subprocess.Popen(args=[appimag_path], shell=True, env={**os.environ},
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            else:
                self.logger.error(f"Could not find the AppImage file of '{pkg.name}' in '{installation_dir}'")

    def cache_to_disk(self, pkg: SoftwarePackage, icon_bytes: Optional[bytes], only_icon: bool):
        self.serialize_to_disk(pkg, icon_bytes, only_icon)

    def get_screenshots(self, pkg: AppImage) -> Generator[str, None, None]:
        if pkg.url_screenshot:
            yield pkg.url_screenshot

    def clear_data(self, logs: bool = True):
        for f in glob.glob(f'{APPIMAGE_SHARED_DIR}/*.db'):
            try:
                if logs:
                    print(f'[bauh][appimage] Deleting {f}')
                os.remove(f)

                if logs:
                    print(f'{Fore.YELLOW}[bauh][appimage] {f} deleted{Fore.RESET}')
            except:
                if logs:
                    print(f'{Fore.RED}[bauh][appimage] An exception has happened when deleting {f}{Fore.RESET}')
                    traceback.print_exc()

    def get_settings(self) -> Optional[Generator[SettingsView, None, None]]:
        config_ = self.configman.get_config()

        comps = [
            TextInputComponent(label=self.i18n['appimage.config.database.expiration'],
                               value=int(config_['database']['expiration']) if isinstance(
                                   config_['database']['expiration'], int) else '',
                               tooltip=self.i18n['appimage.config.database.expiration.tip'],
                               only_int=True,
                               id_='appim_db_exp'),
            TextInputComponent(label=self.i18n['appimage.config.suggestions.expiration'],
                               value=int(config_['suggestions']['expiration']) if isinstance(
                                   config_['suggestions']['expiration'], int) else '',
                               tooltip=self.i18n['appimage.config.suggestions.expiration.tip'],
                               only_int=True,
                               id_='appim_sugs_exp')
        ]

        yield SettingsView(self, PanelComponent([FormComponent(components=comps)]))

    def save_settings(self, component: PanelComponent) -> Tuple[bool, Optional[List[str]]]:
        config_ = self.configman.get_config()

        form = component.get_component_by_idx(0, FormComponent)
        config_['database']['expiration'] = form.get_component('appim_db_exp', TextInputComponent).get_int_value()
        config_['suggestions']['expiration'] = form.get_component('appim_sugs_exp', TextInputComponent).get_int_value()

        try:
            self.configman.save_config(config_)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def gen_custom_actions(self) -> Generator[CustomSoftwareAction, None, None]:
        if self._custom_actions is None:
            self._custom_actions = (CustomSoftwareAction(i18n_label_key='appimage.custom_action.install_file',
                                                         i18n_status_key='appimage.custom_action.install_file.status',
                                                         i18n_description_key='appimage.custom_action.install_file.desc',
                                                         manager=self,
                                                         manager_method='install_file',
                                                         icon_path=resource.get_path('img/appimage.svg', ROOT_DIR),
                                                         requires_root=False,
                                                         requires_confirmation=False),
                                    CustomSoftwareAction(i18n_label_key='appimage.custom_action.update_db',
                                                         i18n_status_key='appimage.custom_action.update_db.status',
                                                         i18n_description_key='appimage.custom_action.update_db.desc',
                                                         manager=self,
                                                         manager_method='update_database',
                                                         icon_path=resource.get_path('img/appimage.svg', ROOT_DIR),
                                                         requires_root=False,
                                                         requires_internet=True))

        if self._get_self_appimage_running() and not self._is_self_installed():
            yield self.action_self_install

        yield from self._custom_actions

    def get_upgrade_requirements(self, pkgs: List[AppImage], root_password: Optional[str], watcher: ProcessWatcher) -> UpgradeRequirements:
        to_update = []

        for pkg in pkgs:
            requirement = UpgradeRequirement(pkg)
            installed_size = self.http_client.get_content_length_in_bytes(pkg.url_download)
            upgrade_size = self.http_client.get_content_length_in_bytes(pkg.url_download_latest_version)
            requirement.required_size = upgrade_size

            if upgrade_size and installed_size:
                requirement.extra_size = upgrade_size - installed_size

            to_update.append(requirement)

        return UpgradeRequirements([], [], to_update, [])

    def _read_ignored_updates(self) -> Set[str]:
        ignored = set()
        if os.path.exists(UPDATES_IGNORED_FILE):
            with open(UPDATES_IGNORED_FILE) as f:
                ignored_txt = f.read()

            for l in ignored_txt.split('\n'):
                if l:
                    line_clean = l.strip()

                    if line_clean:
                        ignored.add(line_clean)

        return ignored

    def ignore_update(self, pkg: AppImage):
        current_ignored = self._read_ignored_updates()

        if pkg.name not in current_ignored:
            current_ignored.add(pkg.name)
            self._write_ignored_updates(current_ignored)

        pkg.updates_ignored = True

    def _write_ignored_updates(self, names: Set[str]):
        Path(APPIMAGE_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        ignored_list = [*names]
        ignored_list.sort()

        with open(UPDATES_IGNORED_FILE, 'w+') as f:
            if ignored_list:
                for ignored in ignored_list:
                    f.write(f'{ignored}\n')
            else:
                f.write('')

    def revert_ignored_update(self, pkg: AppImage):
        current_ignored = self._read_ignored_updates()

        if current_ignored and pkg.name in current_ignored:
            current_ignored.remove(pkg.name)

            self._write_ignored_updates(current_ignored)

        pkg.updates_ignored = False

    def update_database(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        db_updater = DatabaseUpdater(i18n=self.i18n, http_client=self.context.http_client,
                                     logger=self.context.logger, watcher=watcher, taskman=TaskManager())

        res = db_updater.download_databases()
        return res

    @property
    def search_unfilled_attrs(self) -> Tuple[str, ...]:
        if self._search_unfilled_attrs is None:
            self._search_unfilled_attrs = ('icon_url', 'url_download_latest_version', 'author', 'license', 'github',
                                           'source', 'url_screenshot')

        return self._search_unfilled_attrs

    def self_install(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        file_path = self._get_self_appimage_running()

        if not file_path:
            return False

        if self._is_self_installed():
            return False

        app = AppImage(name=self.context.app_name, version=self.context.app_version,
                       categories=['system'], author=self.context.app_name, github=self.app_github,
                       license='zlib/libpng')

        res = self._install(pkg=app, watcher=watcher,
                            pre_downloaded_file=(os.path.basename(file_path), file_path))
        if res.success:
            app.installed = True

            de_path = self._gen_desktop_entry_path(app)

            if de_path and os.path.exists(de_path):
                with open(de_path) as f:
                    bauh_entry = f.read()

                if bauh_entry:
                    comments = re.compile(r'Comment(\[\w+])?\s*=\s*(.+)').findall(bauh_entry)

                    if comments:
                        locale = f'{self.i18n.current_key}' if self.i18n.current_key != self.i18n.default_key else None

                        for key, desc in comments:
                            if desc:
                                if not key:
                                    app.description = desc  # default description

                                    if not locale:
                                        break

                                elif key == locale:
                                    app.description = desc  # localized description
                                    break
                    else:
                        self.context.logger.warning(f"Could not find the 'Comment' fields from {self.context.app_name}'s desktop entry")
                else:
                    self.context.logger.warning(f"{self.context.app_name} desktop entry is empty. Is is not possible to determine the 'description' field")

            else:
                self.context.logger.warning(f"{self.context.app_name} desktop file not found ({de_path}). It is not possible to determine the 'description' field")

            self.cache_to_disk(app, None, False)

        return res.success

    def _is_self_installed(self) -> bool:
        return os.path.exists(f'{INSTALLATION_DIR}/{self.context.app_name}/data.json')

    def _get_self_appimage_running(self) -> Optional[str]:
        file = os.getenv('APPIMAGE')

        if not file:
            return

        app_exec = os.getenv('APPRUN_STARTUP_EXEC_ARGS')

        if not app_exec:
            return

        if os.path.basename(app_exec).split(' ')[0] != self.context.app_name:
            return

        if not os.path.exists(file):
            return

        return file

    @property
    def action_self_install(self) -> CustomSoftwareAction:
        if self._action_self_install is None:
            self._action_self_install = CustomSoftwareAction(i18n_label_key='appimage.custom_action.self_install',
                                                             i18n_status_key='appimage.custom_action.self_install.status',
                                                             i18n_description_key='appimage.custom_action.self_install.desc',
                                                             manager=self,
                                                             manager_method='self_install',
                                                             icon_path=resource.get_path('img/appimage.svg', ROOT_DIR),
                                                             requires_root=False,
                                                             refresh=True,
                                                             requires_internet=False)

        return self._action_self_install

    @property
    def app_github(self) -> str:
        if self._app_github is None:
            self._app_github = f'vinifmor/{self.context.app_name}'

        return self._app_github

    @property
    def suggestions_downloader(self) -> AppImageSuggestionsDownloader:
        if not self._suggestions_downloader:
            file_url = self.context.get_suggestion_url(self.__module__)
            self._suggestions_downloader = AppImageSuggestionsDownloader(taskman=TaskManager(),
                                                                         i18n=self.context.i18n,
                                                                         http_client=self.context.http_client,
                                                                         logger=self.context.logger,
                                                                         file_url=file_url)

            if self._suggestions_downloader.is_custom_local_file_mapped():
                self.logger.info(f"Local AppImage suggestions file mapped: {file_url}")

        return self._suggestions_downloader
