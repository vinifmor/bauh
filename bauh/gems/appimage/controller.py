import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import traceback
from datetime import datetime
from math import floor
from pathlib import Path
from typing import Set, Type, List, Tuple, Optional

from colorama import Fore
from packaging.version import parse as parse_version

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SearchResult, UpgradeRequirements, UpgradeRequirement, \
    TransactionResult, SoftwareAction
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import SoftwarePackage, PackageHistory, PackageUpdate, PackageSuggestion, \
    SuggestionPriority, CustomSoftwareAction
from bauh.api.abstract.view import MessageType, ViewComponent, FormComponent, InputOption, SingleSelectComponent, \
    SelectViewType, TextInputComponent, PanelComponent, FileChooserComponent, ViewObserver
from bauh.commons import resource
from bauh.commons.boot import CreateConfigFile
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, new_subprocess, ProcessHandler, run_cmd, SimpleProcess
from bauh.gems.appimage import query, INSTALLATION_PATH, LOCAL_PATH, ROOT_DIR, \
    CONFIG_DIR, UPDATES_IGNORED_FILE, util, get_default_manual_installation_file_dir, DATABASE_APPS_FILE, \
    DATABASE_RELEASES_FILE, DESKTOP_ENTRIES_PATH, APPIMAGE_CACHE_PATH, get_icon_path
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


class AppImageManager(SoftwareManager):

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
        self.custom_actions = [CustomSoftwareAction(i18n_label_key='appimage.custom_action.install_file',
                                                    i18n_status_key='appimage.custom_action.install_file.status',
                                                    manager=self,
                                                    manager_method='install_file',
                                                    icon_path=resource.get_path('img/appimage.svg', ROOT_DIR),
                                                    requires_root=False),
                               CustomSoftwareAction(i18n_label_key='appimage.custom_action.update_db',
                                                    i18n_status_key='appimage.custom_action.update_db.status',
                                                    manager=self,
                                                    manager_method='update_database',
                                                    icon_path=resource.get_path('img/appimage.svg', ROOT_DIR),
                                                    requires_root=False,
                                                    requires_internet=True)]
        self.custom_app_actions = [CustomSoftwareAction(i18n_label_key='appimage.custom_action.manual_update',
                                                        i18n_status_key='appimage.custom_action.manual_update.status',
                                                        manager_method='update_file',
                                                        requires_root=False,
                                                        icon_path=resource.get_path('img/upgrade.svg', ROOT_DIR))]

    def install_file(self, root_password: str, watcher: ProcessWatcher) -> bool:
        file_chooser = FileChooserComponent(label=self.i18n['file'].capitalize(),
                                            allowed_extensions={'AppImage'},
                                            search_path=get_default_manual_installation_file_dir())
        input_name = TextInputComponent(label=self.i18n['name'].capitalize())
        input_version = TextInputComponent(label=self.i18n['version'].capitalize())
        file_chooser.observers.append(ManualInstallationFileObserver(input_name, input_version))

        input_description = TextInputComponent(label=self.i18n['description'].capitalize())

        cat_ops = [InputOption(label=self.i18n['category.none'].capitalize(), value=0)]
        cat_ops.extend([InputOption(label=self.i18n.get('category.{}'.format(c.lower()), c.lower()).capitalize(), value=c) for c in self.context.default_categories])
        inp_cat = SingleSelectComponent(label=self.i18n['category'], type_=SelectViewType.COMBO, options=cat_ops,
                                        default_option=cat_ops[0])

        form = FormComponent(label='', components=[file_chooser, input_name, input_version, input_description, inp_cat], spaces=False)

        while True:
            if watcher.request_confirmation(title=self.i18n['appimage.custom_action.install_file.details'], body=None,
                                            components=[form],
                                            confirmation_label=self.i18n['proceed'].capitalize(),
                                            deny_label=self.i18n['cancel'].capitalize()):
                if not file_chooser.file_path or not os.path.isfile(file_chooser.file_path):
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

        appim = AppImage(i18n=self.i18n, imported=True, custom_actions=self.custom_app_actions)
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

    def update_file(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher):
        file_chooser = FileChooserComponent(label=self.i18n['file'].capitalize(),
                                            allowed_extensions={'AppImage'},
                                            search_path=get_default_manual_installation_file_dir())
        input_version = TextInputComponent(label=self.i18n['version'].capitalize())
        file_chooser.observers.append(ManualInstallationFileObserver(None, input_version))

        while True:
            if watcher.request_confirmation(title=self.i18n['appimage.custom_action.manual_update.details'], body=None,
                                            components=[FormComponent(label='', components=[file_chooser, input_version], spaces=False)],
                                            confirmation_label=self.i18n['proceed'].capitalize(),
                                            deny_label=self.i18n['cancel'].capitalize()):
                if not file_chooser.file_path or not os.path.isfile(file_chooser.file_path):
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
                self.logger.error("Could not connect to database file '{}'".format(db_path))
                traceback.print_exc()
        else:
            self.logger.warning("Could not get a connection for database '{}'".format(db_path))

    def _gen_app_key(self, app: AppImage):
        return '{}{}'.format(app.name.lower(), app.github.lower() if app.github else '')

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
                app = AppImage(*r, i18n=self.i18n, custom_actions=self.custom_app_actions)
                not_installed.append(app)
                found_map[self._gen_app_key(app)] = {'app': app, 'idx': idx}
                idx += 1
        except:
            self.logger.error("An exception happened while querying the 'apps' database")
            traceback.print_exc()
            apps_conn.close()
            return SearchResult.empty()

        installed_found = []

        if not_installed:
            installed = self.read_installed(disk_loader=disk_loader, limit=limit,
                                            only_apps=False,
                                            pkg_types=None,
                                            connection=apps_conn,
                                            internet_available=True).installed
            if installed:
                for appim in installed:
                    key = self._gen_app_key(appim)

                    new_found = found_map.get(key)

                    if new_found:
                        del not_installed[new_found['idx']]
                        installed_found.append(appim)

        try:
            apps_conn.close()
        except:
            self.logger.error("An exception happened when trying to close the connection to database file '{}'".format(DATABASE_APPS_FILE))
            traceback.print_exc()

        return SearchResult(new=not_installed, installed=installed_found, total=len(not_installed) + len(installed_found))

    def read_installed(self, disk_loader: Optional[DiskCacheLoader], limit: int = -1, only_apps: bool = False,
                       pkg_types: Optional[Set[Type[SoftwarePackage]]] = None, internet_available: bool = None, connection: sqlite3.Connection = None) -> SearchResult:
        installed_apps = []
        res = SearchResult(installed_apps, [], 0)

        if os.path.exists(INSTALLATION_PATH):
            installed = run_cmd('ls {}*/data.json'.format(INSTALLATION_PATH), print_error=False)

            if installed:
                names = set()
                for path in installed.split('\n'):
                    if path:
                        with open(path) as f:
                            app = AppImage(installed=True, i18n=self.i18n, custom_actions=self.custom_app_actions, **json.loads(f.read()))
                            app.icon_url = app.icon_path

                        installed_apps.append(app)
                        names.add("'{}'".format(app.name.lower()))

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
                            self.logger.error("An exception happened while querying the database file {}".format(apps_con))
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
            if self.uninstall(pkg, root_password, watcher).success:
                old_release = versions.history[versions.pkg_status_idx + 1]
                pkg.version = old_release['0_version']
                pkg.latest_version = pkg.version
                pkg.url_download = old_release['2_url_download']
                if self.install(pkg, root_password, None, watcher).success:
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

    def upgrade(self, requirements: UpgradeRequirements, root_password: str, watcher: ProcessWatcher) -> bool:
        for req in requirements.to_upgrade:
            watcher.change_status("{} {} ({})...".format(self.i18n['manage_window.status.upgrading'], req.pkg.name, req.pkg.version))

            if not self.uninstall(req.pkg, root_password, watcher).success:
                watcher.show_message(title=self.i18n['error'],
                                     body=self.i18n['appimage.error.uninstall_current_version'],
                                     type_=MessageType.ERROR)
                watcher.change_substatus('')
                return False

            if not self.install(req.pkg, root_password, None, watcher).success:
                watcher.change_substatus('')
                return False

            self.cache_to_disk(req.pkg, None, False)

        watcher.change_substatus('')
        return True

    def uninstall(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher, disk_loader: DiskCacheLoader = None) -> TransactionResult:
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
            self.logger.info("Removing symlink '{}'".format(pkg.symlink))

            try:
                os.remove(pkg.symlink)
                self.logger.info("symlink '{}' successfully removed".format(pkg.symlink))
            except:
                msg = "could not remove symlink '{}'".format(pkg.symlink)
                self.logger.error(msg)

                if watcher:
                    watcher.print("[error] {}".format(msg))

        return TransactionResult(success=True, installed=None, removed=[pkg])

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

        categories = data.get('categories')

        if categories:
            data['categories'] = [self.i18n.get('category.{}'.format(c.lower()), self.i18n.get(c, c)).capitalize() for c in data['categories']]

        if data.get('symlink') and not os.path.islink(data['symlink']):
            del data['symlink']

        return data

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
                self.logger.warning("Could not retrieve {} from the database {}".format(pkg, DATABASE_APPS_FILE))
                return res
        except:
            self.logger.error("An exception happened while querying the database file '{}'".format(DATABASE_APPS_FILE))
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
                for idx, tup in enumerate(releases):
                    history.append({'0_version': tup[0],
                                    '1_published_at': datetime.strptime(tup[2], '%Y-%m-%dT%H:%M:%SZ') if tup[
                                        2] else '', '2_url_download': tup[1]})

                    if res.pkg_status_idx == -1 and pkg.version == tup[0]:
                        res.pkg_status_idx = idx

                return res
        except:
            self.logger.error("An exception happened while querying the database file '{}'".format(DATABASE_RELEASES_FILE))
            traceback.print_exc()
        finally:
            releases_con.close()

    def _find_desktop_file(self, folder: str) -> str:
        for r, d, files in os.walk(folder):
            for f in files:
                if f.endswith('.desktop'):
                    return f

    def _find_icon_file(self, folder: str) -> str:
        for f in glob.glob(folder + ('/**' if not folder.endswith('/') else '**'), recursive=True):
            if RE_ICON_ENDS_WITH.match(f):
                return f

    def install(self, pkg: AppImage, root_password: str, disk_loader: Optional[DiskCacheLoader], watcher: ProcessWatcher) -> TransactionResult:
        handler = ProcessHandler(watcher)

        out_dir = INSTALLATION_PATH + pkg.get_clean_name()
        counter = 0
        while True:
            if os.path.exists(out_dir):
                self.logger.info("Installation dir '{}' already exists. Generating a different one".format(out_dir))
                out_dir += '-{}'.format(counter)
                counter += 1
            else:
                break

        Path(out_dir).mkdir(parents=True, exist_ok=True)
        pkg.install_dir = out_dir

        if pkg.imported:

            downloaded, file_name = True, pkg.local_file_path.split('/')[-1]

            file_path = out_dir + '/' + file_name

            try:
                moved, output = handler.handle_simple(SimpleProcess(['mv', pkg.local_file_path, file_path]))
            except:
                self.logger.error("Could not rename file '' as '{}'".format(pkg.local_file_path, file_path))
                moved = False

            if not moved:
                watcher.show_message(title=self.i18n['error'].capitalize(),
                                     body=self.i18n['appimage.install.imported.rename_error'].format(bold(pkg.local_file_path.split('/')[-1]), bold(output)),
                                     type_=MessageType.ERROR)

                return TransactionResult.fail()

        else:
            appimage_url = pkg.url_download_latest_version if pkg.update else pkg.url_download
            file_name = appimage_url.split('/')[-1]
            pkg.version = pkg.latest_version
            pkg.url_download = appimage_url

            file_path = out_dir + '/' + file_name
            downloaded = self.file_downloader.download(file_url=pkg.url_download, watcher=watcher,
                                                       output_path=file_path, cwd=str(Path.home()))

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
                        return TransactionResult.fail()
                except:
                    watcher.show_message(title=self.i18n['error'],
                                         body=traceback.format_exc(),
                                         type_=MessageType.ERROR)
                    traceback.print_exc()
                    handler.handle(SystemProcess(new_subprocess(['rm', '-rf', out_dir])))
                    return TransactionResult.fail()

                watcher.change_substatus(self.i18n['appimage.install.desktop_entry'])
                extracted_folder = '{}/{}'.format(out_dir, 'squashfs-root')

                if os.path.exists(extracted_folder):
                    desktop_entry = self._find_desktop_file(extracted_folder)

                    with open('{}/{}'.format(extracted_folder, desktop_entry)) as f:
                        de_content = f.read()

                    de_content = replace_desktop_entry_exec_command(desktop_entry=de_content,
                                                                    appname=pkg.name,
                                                                    file_path=file_path)

                    extracted_icon = self._find_icon_file(extracted_folder)

                    if extracted_icon:
                        icon_path = out_dir + '/logo.' + extracted_icon.split('/')[-1].split('.')[-1]
                        shutil.copy(extracted_icon, icon_path)
                        de_content = RE_DESKTOP_ICON.sub('Icon={}\n'.format(icon_path), de_content)
                        pkg.icon_path = icon_path

                    Path(DESKTOP_ENTRIES_PATH).mkdir(parents=True, exist_ok=True)

                    with open(self._gen_desktop_entry_path(pkg), 'w+') as f:
                        f.write(de_content)

                    try:
                        shutil.rmtree(extracted_folder)
                    except:
                        traceback.print_exc()

                    SymlinksVerifier.create_symlink(app=pkg, file_path=file_path, logger=self.logger, watcher=watcher)
                    return TransactionResult(success=True, installed=[pkg], removed=[])
                else:
                    watcher.show_message(title=self.i18n['error'],
                                         body='Could extract content from {}'.format(bold(file_name)),
                                         type_=MessageType.ERROR)
        else:
            watcher.show_message(title=self.i18n['error'],
                                 body=self.i18n['appimage.install.download.error'].format(bold(pkg.url_download)),
                                 type_=MessageType.ERROR)

        handler.handle(SystemProcess(new_subprocess(['rm', '-rf', out_dir])))
        return TransactionResult.fail()

    def _gen_desktop_entry_path(self, app: AppImage) -> str:
        return '{}/bauh_appimage_{}.desktop'.format(DESKTOP_ENTRIES_PATH, app.get_clean_name())

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def _is_sqlite3_available(self):
        res = run_cmd('which sqlite3')
        return res and not res.strip().startswith('which ')

    def can_work(self) -> bool:
        return self._is_sqlite3_available() and self.file_downloader.can_work()

    def requires_root(self, action: SoftwareAction, pkg: AppImage) -> bool:
        return False

    def prepare(self, task_manager: TaskManager, root_password: str, internet_available: bool):
        create_config = CreateConfigFile(taskman=task_manager, configman=self.configman, i18n=self.i18n,
                                         task_icon_path=get_icon_path(), logger=self.logger)
        create_config.start()

        symlink_check = SymlinksVerifier(taskman=task_manager, i18n=self.i18n, logger=self.logger)
        symlink_check.start()

        if internet_available:
            DatabaseUpdater(taskman=task_manager, i18n=self.context.i18n,
                            create_config=create_config, http_client=self.context.http_client,
                            logger=self.context.logger).start()

            AppImageSuggestionsDownloader(taskman=task_manager, i18n=self.context.i18n,
                                          http_client=self.context.http_client, logger=self.context.logger,
                                          create_config=create_config).start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        res = self.read_installed(disk_loader=None, internet_available=internet_available)

        updates = []
        if res.installed:
            for app in res.installed:
                if app.update and not app.is_update_ignored():
                    updates.append(PackageUpdate(pkg_id=app.name, pkg_type='AppImage', version=app.latest_version, name=app.name))

        return updates

    def list_warnings(self, internet_available: bool) -> List[str]:
        dbfiles = glob.glob('{}/*.db'.format(APPIMAGE_CACHE_PATH))

        if not dbfiles or len({f for f in (DATABASE_APPS_FILE, DATABASE_RELEASES_FILE) if f in dbfiles}) != 2:
            return [self.i18n['appimage.warning.missing_db_files'].format(appimage=bold('AppImage'))]

    def list_suggestions(self, limit: int, filter_installed: bool) -> List[PackageSuggestion]:
        res = []

        connection = self._get_db_connection(DATABASE_APPS_FILE)

        if connection:
            suggestions = AppImageSuggestionsDownloader(appimage_config=self.configman.get_config(), logger=self.logger,
                                                        i18n=self.i18n, http_client=self.http_client,
                                                        taskman=TaskManager()).read()

            if not suggestions:
                self.logger.warning("Could not read suggestions")
                return res
            else:
                self.logger.info("Mapping suggestions")
                try:
                    if filter_installed:
                        installed = {i.name.lower() for i in self.read_installed(disk_loader=None, connection=connection).installed}
                    else:
                        installed = None

                    sugs_map = {}

                    for s in suggestions:
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
                        app = AppImage(*t, i18n=self.i18n, custom_actions=self.custom_app_actions)
                        res.append(PackageSuggestion(app, sugs_map[app.name.lower()]))
                    self.logger.info("Mapped {} suggestions".format(len(res)))
                except:
                    traceback.print_exc()
                finally:
                    connection.close()

        return res

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: AppImage):
        installation_dir = pkg.get_disk_cache_path()
        if os.path.exists(installation_dir):
            appimag_path = util.find_appimage_file(installation_dir)

            if appimag_path:
                subprocess.Popen(args=[appimag_path], shell=True, env={**os.environ})
            else:
                self.logger.error("Could not find the AppImage file of '{}' in '{}'".format(pkg.name, installation_dir))

    def cache_to_disk(self, pkg: SoftwarePackage, icon_bytes: Optional[bytes], only_icon: bool):
        self.serialize_to_disk(pkg, icon_bytes, only_icon)

    def get_screenshots(self, pkg: AppImage) -> List[str]:
        if pkg.has_screenshots():
            return [pkg.url_screenshot]

        return []

    def clear_data(self, logs: bool = True):
        for f in glob.glob('{}/*.db'.format(LOCAL_PATH)):
            try:
                if logs:
                    print('[bauh][appimage] Deleting {}'.format(f))
                os.remove(f)

                if logs:
                    print('{}[bauh][appimage] {} deleted{}'.format(Fore.YELLOW, f, Fore.RESET))
            except:
                if logs:
                    print('{}[bauh][appimage] An exception has happened when deleting {}{}'.format(Fore.RED, f, Fore.RESET))
                    traceback.print_exc()

    def get_settings(self, screen_width: int, screen_height: int) -> ViewComponent:
        appimage_config = self.configman.get_config()
        max_width = floor(screen_width * 0.15)

        comps = [
            TextInputComponent(label=self.i18n['appimage.config.database.expiration'],
                               value=int(appimage_config['database']['expiration']) if isinstance(
                                   appimage_config['database']['expiration'], int) else '',
                               tooltip=self.i18n['appimage.config.database.expiration.tip'],
                               only_int=True,
                               max_width=max_width,
                               id_='appim_db_exp'),
            TextInputComponent(label=self.i18n['appimage.config.suggestions.expiration'],
                               value=int(appimage_config['suggestions']['expiration']) if isinstance(
                                   appimage_config['suggestions']['expiration'], int) else '',
                               tooltip=self.i18n['appimage.config.suggestions.expiration.tip'],
                               only_int=True,
                               max_width=max_width,
                               id_='appim_sugs_exp')
        ]

        return PanelComponent([FormComponent(components=comps, id_='form')])

    def save_settings(self, component: PanelComponent) -> Tuple[bool, Optional[List[str]]]:
        appimage_config = self.configman.get_config()

        form = component.get_form_component('form')
        appimage_config['database']['expiration'] = form.get_text_input('appim_db_exp').get_int_value()
        appimage_config['suggestions']['expiration'] = form.get_text_input('appim_sugs_exp').get_int_value()

        try:
            self.configman.save_config(appimage_config)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def get_custom_actions(self) -> List[CustomSoftwareAction]:
        return self.custom_actions

    def get_upgrade_requirements(self, pkgs: List[AppImage], root_password: str, watcher: ProcessWatcher) -> UpgradeRequirements:
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
        Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        ignored_list = [*names]
        ignored_list.sort()

        with open(UPDATES_IGNORED_FILE, 'w+') as f:
            if ignored_list:
                for ignored in ignored_list:
                    f.write('{}\n'.format(ignored))
            else:
                f.write('')

    def revert_ignored_update(self, pkg: AppImage):
        current_ignored = self._read_ignored_updates()

        if current_ignored and pkg.name in current_ignored:
            current_ignored.remove(pkg.name)

            self._write_ignored_updates(current_ignored)

        pkg.updates_ignored = False

    def update_database(self, root_password: str, watcher: ProcessWatcher) -> bool:
        db_updater = DatabaseUpdater(i18n=self.i18n, http_client=self.context.http_client,
                                     logger=self.context.logger, watcher=watcher, taskman=TaskManager())

        res = db_updater.download_databases()
        return res
