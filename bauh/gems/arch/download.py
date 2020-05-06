import logging
import os
from pathlib import Path
from typing import Tuple, List, Iterable, Dict

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MessageType
from bauh.api.http import HttpClient
from bauh.commons.html import bold
from bauh.commons.system import ProcessHandler, SimpleProcess
from bauh.gems.arch import PACKAGE_CACHE_DIR, pacman
from bauh.view.util.translation import I18n


class CacheDirCreationException(Exception):
    pass


class AddPackageToCacheException(Exception):
    pass


class UnexpectedDownloadException(Exception):
    pass


class MultiThreadedDownloader:

    def __init__(self, file_downloader: FileDownloader, http_client: HttpClient, mirrors_available: Iterable[str], mirrors_branch: str, cache_dir: str):
        self.downloader = file_downloader
        self.http_client = http_client
        self.mirrors = mirrors_available
        self.branch = mirrors_branch
        self.extensions = ['.tar.zst', '.tar.xz']
        self.cache_dir = cache_dir

    def download_package(self, pkg: Dict[str, str], output_dir: str, watcher: ProcessWatcher) -> Tuple[bool, str]:
        if self.mirrors and self.branch:
            arch = pkg['a'] if pkg.get('a') and pkg['a'] != 'any' else 'x86_64'
            pkgname = '{}-{}{}.pkg'.format(pkg['n'], pkg['v'], ('-{}'.format(pkg['a']) if pkg['a'] else ''))
            url_base = '{}/{}/{}/{}'.format(self.branch, pkg['r'], arch, pkgname)
            base_output_path = '{}/{}'.format(output_dir, pkgname)
            for mirror in self.mirrors:
                for ext in self.extensions:
                    url = '{}{}{}'.format(mirror, url_base, ext)
                    output_path = base_output_path + ext

                    if self.http_client.exists(url, timeout=1):
                        watcher.print("Downloading '{}' from mirror '{}'".format(pkgname, mirror))
                        downloaded = self.downloader.download(file_url=url, watcher=None, output_path=base_output_path, cwd='.')
                        if not downloaded:
                            watcher.print("Could not download '{}' from mirror '{}'".format(pkgname, mirror))
                            break
                        else:
                            return True, output_path.split('/')[-1]

        return False, ''

    def download_and_cache_package(self, pkg: Dict[str, str], root_password: str, handler: ProcessHandler, download_dir: str = PACKAGE_CACHE_DIR) -> bool:
        Path(PACKAGE_CACHE_DIR).mkdir(exist_ok=True, parents=True)

        # TODO check if the file is not already downloaded
        downloaded, file_path = self.download_package(pkg, output_dir=download_dir, watcher=handler.watcher)

        if not downloaded:
            return downloaded

        if not os.path.isdir(self.cache_dir):
            success, _ = handler.handle_simple(SimpleProcess(['mkdir', '-p', self.cache_dir], root_password=root_password))

            if not success:
                raise CacheDirCreationException()

        moved, _ = handler.handle_simple(SimpleProcess(['mv', file_path, '']))

        if not moved:
            raise AddPackageToCacheException()

        return True


class MultithreadedDownloadService:

    def __init__(self, file_downloader: FileDownloader, http_client: HttpClient, logger: logging.Logger, i18n: I18n):
        self.file_downloader = file_downloader
        self.http_client = http_client
        self.logger = logger
        self.i18n = i18n

    def download_packages(self, pkgs: List[str], handler: ProcessHandler, root_password: str) -> int:
        watcher = handler.watcher
        mirrors = pacman.list_available_mirrors()

        if not mirrors:
            self.logger.warning('repository mirrors seem to be not reachable')
            watcher.print('[warning] repository mirrors seem to be not reachable')
            watcher.print('[warning] multi-threaded download cancelled')
            return 0

        branch = pacman.get_mirrors_branch()

        if not branch:
            self.logger.warning('no default repository branch found')
            watcher.print('[warning] no default repository branch found')
            watcher.print('[warning] multi-threaded download cancelled')
            return 0

        cache_dir = pacman.get_cache_dir()

        downloader = MultiThreadedDownloader(file_downloader=self.file_downloader,
                                             mirrors_available=mirrors,
                                             mirrors_branch=branch,
                                             http_client=self.http_client,
                                             cache_dir=cache_dir)

        downloaded = 0
        exception = False

        pkgs_data = pacman.list_download_data(pkgs)

        for pkg in pkgs_data:
            self.logger.info('Preparing to download package: {} ({})'.format(pkg['n'], pkg['v']))
            try:
                perc = '({0:.2f}%)'.format((downloaded / (2 * len(pkgs))) * 100)
                watcher.change_substatus('{} [{}/{}] {} {}'.format(perc, downloaded, len(pkgs), self.i18n['downloading'].capitalize(), pkg.name))

                if downloader.download_and_cache_package(pkg=pkg, root_password=root_password, handler=handler):
                    downloaded += 1
                    self.logger.info("Package '{}' successfully downloaded".format(pkg['n']))
                else:
                    self.logger.warning("Package '{}' download failed".format(pkg['n']))
            except CacheDirCreationException:
                msg = "could not create cache dir '{}'".format(cache_dir)
                self.logger.warning(msg)
                watcher.print("[warning] {}".format(cache_dir))
                watcher.show_message(title=self.i18n['warning'].capitalize(),
                                     body=self.i18n['arch.mthread_downloaded.error.cache_dir'].format(bold(cache_dir)),
                                     type_=MessageType.WARNING)
                exception = True
            except AddPackageToCacheException:
                msg = "could downloaded package '{}' to cache dir '{}'".format(pkg['n'], cache_dir)
                self.logger.warning(msg)
                watcher.print("[warning] {}".format(cache_dir))
                watcher.show_message(title=self.i18n['warning'].capitalize(),
                                     body=self.i18n['arch.mthread_downloaded.error.pkg2cache'].format(bold(pkg['n']), bold(cache_dir)),
                                     type_=MessageType.WARNING)
                exception = True

        if exception:
            watcher.show_message(title=self.i18n['error'].capitalize(),
                                 body=self.i18n['arch.mthread_downloaded.error.cancelled'],
                                 type_=MessageType.ERROR)
            raise UnexpectedDownloadException()

        return downloaded

# TODO remove
# if __name__ == '__main__':
#     from unittest.mock import Mock
#     from bauh.view.core.downloader import AdaptableFileDownloader
#
#     logger = Mock()
#     client = HttpClient(logger=logger)
#     i18n = I18n(current_key='en', current_locale={}, default_key='en', default_locale={})
#     fd = AdaptableFileDownloader(logger=logger, http_client=client, i18n=i18n, multithread_enabled=True)
#
#     mirrors_available = pacman.list_available_mirrors()
#     mirrors_branch = pacman.get_mirrors_branch()
#     md = MultiThreadedDownloader(file_downloader=fd, http_client=client, mirrors_available=mirrors_available, mirrors_branch=mirrors_branch)
#     pkg = ArchPackage(name='kodi', arch='x86_64', latest_version='18.6-1', repository='community')
#     ti = time.time()
#     res = md.download_package(pkg, str(Path.home()), Mock())
#     tf = time.time()
#     print('{} -> {}s'.format(res, tf - ti))
