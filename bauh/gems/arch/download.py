import glob
import logging
import os
import traceback
from typing import Tuple, List, Iterable, Dict

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MessageType
from bauh.api.http import HttpClient
from bauh.commons.html import bold
from bauh.commons.system import ProcessHandler, SimpleProcess
from bauh.gems.arch import pacman
from bauh.view.util.translation import I18n


class ArchDownloadException(Exception):
    pass


class CacheDirCreationException(ArchDownloadException):
    pass


class MultiThreadedDownloader:

    def __init__(self, file_downloader: FileDownloader, http_client: HttpClient, mirrors_available: Iterable[str],
                 mirrors_branch: str, cache_dir: str, logger: logging.Logger):
        self.downloader = file_downloader
        self.http_client = http_client
        self.mirrors = mirrors_available
        self.branch = mirrors_branch
        self.extensions = ['.tar.zst', '.tar.xz']
        self.cache_dir = cache_dir
        self.logger = logger

    def download_package(self, pkg: Dict[str, str], root_password: str, substatus_prefix: str, watcher: ProcessWatcher) -> Tuple[bool, str]:
        if self.mirrors and self.branch:
            pkgname = '{}-{}{}.pkg'.format(pkg['n'], pkg['v'], ('-{}'.format(pkg['a']) if pkg['a'] else ''))

            filepath = [f for f in glob.glob(self.cache_dir + '/*') if f.split('/')[-1].startswith(pkgname)]

            if filepath:
                watcher.print("{} ({}) file found o cache dir {}. Skipping download.".format(pkg['n'], pkg['v'], self.cache_dir))
                return True, filepath[0]

            arch = pkg['a'] if pkg.get('a') and pkg['a'] != 'any' else 'x86_64'

            url_base = '{}/{}/{}/{}'.format(self.branch, pkg['r'], arch, pkgname)
            base_output_path = '{}/{}'.format(self.cache_dir, pkgname)
            for mirror in self.mirrors:
                for ext in self.extensions:
                    url = '{}{}{}'.format(mirror, url_base, ext)
                    output_path = base_output_path + ext

                    if self.http_client.exists(url, timeout=1):  # TODO test speed
                        watcher.print("Downloading '{}' from mirror '{}'".format(pkgname, mirror))
                        downloaded = self.downloader.download(file_url=url, watcher=watcher, output_path=base_output_path,
                                                              cwd='.', root_password=root_password, display_file_size=False,
                                                              substatus_prefix=substatus_prefix)
                        if not downloaded:
                            watcher.print("Could not download '{}' from mirror '{}'".format(pkgname, mirror))
                            self.logger.warning("Package '{}' download failed".format(pkg['n']))
                            break
                        else:
                            self.logger.info("Package '{}' successfully downloaded".format(pkg['n']))
                            return True, output_path.split('/')[-1]

        return False, ''


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

        if not os.path.exists(cache_dir):
            success, _ = handler.handle_simple(SimpleProcess(['mkdir', '-p', cache_dir], root_password=root_password))

            if not success:
                msg = "could not create cache dir '{}'".format(cache_dir)
                self.logger.warning(msg)
                watcher.print("[warning] {}".format(cache_dir))
                watcher.show_message(title=self.i18n['warning'].capitalize(),
                                     body=self.i18n['arch.mthread_downloaded.error.cache_dir'].format(bold(cache_dir)),
                                     type_=MessageType.WARNING)
                raise CacheDirCreationException()

        downloader = MultiThreadedDownloader(file_downloader=self.file_downloader,
                                             mirrors_available=mirrors,
                                             mirrors_branch=branch,
                                             http_client=self.http_client,
                                             cache_dir=cache_dir)

        downloaded = 0
        pkgs_data = pacman.list_download_data(pkgs)

        for pkg in pkgs_data:
            self.logger.info('Preparing to download package: {} ({})'.format(pkg['n'], pkg['v']))
            try:
                perc = '({0:.2f}%)'.format((downloaded / (2 * len(pkgs))) * 100)
                status_prefix = '{} [{}/{}] {} {}'.format(perc, downloaded, len(pkgs), self.i18n['downloading'].capitalize(), pkg['n'])

                if downloader.download_package(pkg=pkg, root_password=root_password, watcher=handler.watcher, substatus_prefix=status_prefix):
                    downloaded += 1
            except:
                traceback.print_exc()
                watcher.show_message(title=self.i18n['error'].capitalize(),
                                     body=self.i18n['arch.mthread_downloaded.error.cancelled'],
                                     type_=MessageType.ERROR)
                raise ArchDownloadException()

        return downloaded
