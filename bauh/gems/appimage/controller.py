import os
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Set, Type, List

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SearchResult
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageHistory, PackageUpdate, PackageSuggestion
from bauh.api.constants import HOME_PATH
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, new_subprocess, ProcessHandler
from bauh.gems.appimage import query, INSTALLATION_PATH
from bauh.gems.appimage.model import AppImage

DB_PATH = '{}/{}'.format(HOME_PATH, '.cache/bauh/appimage/appimage.db')
DESKTOP_ENTRIES_PATH = '{}/.local/share/applications'.format(HOME_PATH)

RE_DESKTOP_EXEC = re.compile(r'Exec\s+=\s+.+\n')
RE_DESKTOP_ICON = re.compile(r'Icon\s+=\s+.+\n')
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

    def _get_db_connection(self) -> sqlite3.Connection:
        if os.path.exists(DB_PATH):
            return sqlite3.connect(DB_PATH)

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1) -> SearchResult:
        res = SearchResult([], [], 0)
        connection = self._get_db_connection()

        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute(query.SEARCH_BY_NAME_OR_DESCRIPTION.format(words, words))

                for l in cursor.fetchall():
                    app = AppImage(*l)
                    res.new.append(app)
            finally:
                connection.close()

        res.total = len(res.installed) + len(res.new)
        return res

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None) -> SearchResult:
        return SearchResult([], [], 0)

    def downgrade(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher) -> bool:
        pass

    def update(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher) -> SystemProcess:
        pass

    def uninstall(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher) -> bool:
        pass

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        return {AppImage}

    def clean_cache_for(self, pkg: AppImage):
        # TODO
        pass

    def get_info(self, pkg: AppImage) -> dict:
        # TODO
        pass

    def get_history(self, pkg: AppImage) -> PackageHistory:
        # TODO
        pass

    def _find_desktop_file(self, folder: str) -> str:
        for r, d, files in os.walk(folder):
            for f in files:
                if f.endswith('.desktop'):
                    return f

    def _find_icon_file(self, folder: str) -> str:
        for r, d, files in os.walk(folder):
            for f in files:
                if RE_ICON_ENDS_WITH.match(f):
                    return f

    def install(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher) -> bool:
        handler = ProcessHandler(watcher)
        out_dir = INSTALLATION_PATH + pkg.name.lower()
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        file_name = pkg.url_download.split('/')[-1]
        file_path = out_dir + '/' + file_name
        downloaded = self.file_downloader.download(file_url=pkg.url_download, watcher=watcher,
                                                   output_path=file_path, cwd=HOME_PATH)

        if downloaded:
            watcher.change_substatus(self.i18n['appimage.install.permission'].format(bold(file_name)))
            permission_given = handler.handle(SystemProcess(new_subprocess(['chmod', 'a+x', file_path])))

            if permission_given:
                watcher.change_substatus('Reading content from {}'.format(bold(file_name)))
                extracted = handler.handle(SystemProcess(new_subprocess([file_name, '--appimage-extract'], cwd=out_dir)))

                if extracted:
                    watcher.change_substatus('Generating desktop entry')
                    extracted_folder = '{}/{}'.format(out_dir, 'squashfs-root')

                    if os.path.exists(extracted_folder):
                        desktop_entry = self._find_desktop_file(extracted_folder)

                        if desktop_entry:
                            with open(desktop_entry) as f:
                                de_content = f.read()

                            de_content = RE_DESKTOP_EXEC.sub('Exec='.format(file_path), de_content)

                            extracted_icon = self._find_icon_file(extracted_folder)

                            if extracted_icon:
                                icon_path = out_dir + '/' + extracted_icon.split('/')[-1]
                                shutil.copy(icon_path, icon_path)
                                de_content = RE_DESKTOP_ICON.sub('Icon='.format(icon_path), de_content)

                            Path(DESKTOP_ENTRIES_PATH).mkdir(parents=True, exist_ok=True)

                            with open('{}/bauh_appimage_{}.desktop'.format(DESKTOP_ENTRIES_PATH, pkg.name.lower()), 'w+') as f:
                                f.write(de_content)

                            return True
                        else:
                            pass
                            # todo generate new
                    else:
                        watcher.show_message(title=self.i18n['error'],
                                             body='Could not find extracted the content from {}'.format(
                                                 bold(file_name)))
                else:
                    watcher.show_message(title=self.i18n['error'],
                                         body='Could not extract content from {}'.format(bold(file_name)))

        handler.handle(SystemProcess(new_subprocess(['rm', '-rf', out_dir])))
        return False

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> bool:
        # TODO check wget and sqlite
        return True

    def requires_root(self, action: str, pkg: AppImage):
        return False

    def prepare(self):
        # TODO
        pass

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        # TODO
        pass

    def list_warnings(self) -> List[str]:
        pass

    def list_suggestions(self, limit: int) -> List[PackageSuggestion]:
        # TODO
        pass

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: AppImage):
        # TODO
        pass
