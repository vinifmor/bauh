import os
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

    def install(self, pkg: AppImage, root_password: str, watcher: ProcessWatcher) -> bool:
        out_dir = INSTALLATION_PATH + pkg.name.lower()
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        file_name = pkg.url_download.split('/')[-1]
        file_path = out_dir + '/' + file_name
        downloaded = self.file_downloader.download(pkg.url_download, watcher=watcher, output_path=file_path, cwd=HOME_PATH)

        if downloaded:
            handler = ProcessHandler(watcher)
            watcher.change_substatus(self.i18n['appimage.install.permission'].format(bold(file_name)))
            return handler.handle(SystemProcess(new_subprocess(['chmod', 'a+x', file_path])))

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
