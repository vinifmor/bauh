import logging
import sys

from bauh.api.abstract.cache import MemoryCacheFactory
from bauh.api.abstract.disk import DiskCacheLoaderFactory
from bauh.api.abstract.download import FileDownloader
from bauh.api.http import HttpClient
from bauh.commons.internet import InternetChecker
from bauh.view.util.translation import I18n


class ApplicationContext:

    def __init__(self, download_icons: bool, http_client: HttpClient, app_root_dir: str, i18n: I18n,
                 cache_factory: MemoryCacheFactory, disk_loader_factory: DiskCacheLoaderFactory,
                 logger: logging.Logger, file_downloader: FileDownloader, distro: str, app_name: str,
                 internet_checker: InternetChecker):
        """
        :param download_icons: if packages icons should be downloaded
        :param http_client: a shared instance of http client
        :param app_root_dir: GUI root dir
        :param i18n: the translation keys
        :param cache_factory:
        :param disk_loader_factory:
        :param logger: a logger instance
        :param file_downloader
        :param distro
        :param app_name
        :param internet_checker
        """
        self.download_icons = download_icons
        self.http_client = http_client
        self.app_root_dir = app_root_dir
        self.i18n = i18n
        self.cache_factory = cache_factory
        self.disk_loader_factory = disk_loader_factory
        self.logger = logger
        self.file_downloader = file_downloader
        self.arch_x86_64 = sys.maxsize > 2**32
        self.distro = distro
        self.default_categories = ('AudioVideo', 'Audio', 'Video', 'Development', 'Education', 'Game',
                                   'Graphics', 'Network', 'Office', 'Science', 'Settings', 'System', 'Utility')
        self.app_name = app_name
        self.root_password = None
        self.internet_checker = internet_checker

    def is_system_x86_64(self):
        return self.arch_x86_64

    def get_view_path(self):
        return self.app_root_dir + '/view'

    def is_internet_available(self) -> bool:
        return self.internet_checker.is_available()
