import glob
import logging
import os
import time
import traceback
from threading import Lock, Thread
from typing import List, Iterable, Dict

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
        self.async_downloads = []
        self.async_downloads_lock = Lock()

    def download_package_signature(self, pkg: dict, file_url: str, output_path: str, root_password: str, watcher: ProcessWatcher):
        try:
            self.logger.info("Downloading package '{}' signature".format(pkg['n']))

            sig_downloaded = self.downloader.download(file_url=file_url + '.sig', watcher=None,
                                                      output_path=output_path + '.sig',
                                                      cwd='.', root_password=root_password,
                                                      display_file_size=False,
                                                      max_threads=1)

            if not sig_downloaded:
                msg = "Could not download package '{}' signature".format(pkg['n'])
                self.logger.warning(msg)
                watcher.print('[warning] {}'.format(msg))
            else:
                msg = "Package '{}' signature successfully downloaded".format(pkg['n'])
                self.logger.info(msg)
                watcher.print(msg)
        except:
            self.logger.warning("An error occurred while download package '{}' signature".format(pkg['n']))
            traceback.print_exc()

    def download_package(self, pkg: Dict[str, str], root_password: str, substatus_prefix: str, watcher: ProcessWatcher, size: int) -> bool:
        if self.mirrors and self.branch:
            pkgname = '{}-{}{}.pkg'.format(pkg['n'], pkg['v'], ('-{}'.format(pkg['a']) if pkg['a'] else ''))

            if {f for f in glob.glob(self.cache_dir + '/*') if f.split('/')[-1].startswith(pkgname)}:
                watcher.print("{} ({}) file found o cache dir {}. Skipping download.".format(pkg['n'], pkg['v'], self.cache_dir))
                return True

            arch = pkg['a'] if pkg.get('a') and pkg['a'] != 'any' else 'x86_64'

            url_base = '{}/{}/{}/{}'.format(self.branch, pkg['r'], arch, pkgname)
            base_output_path = '{}/{}'.format(self.cache_dir, pkgname)

            for mirror in self.mirrors:
                for ext in self.extensions:
                    url = '{}{}{}'.format(mirror, url_base, ext)
                    output_path = base_output_path + ext

                    watcher.print("Downloading '{}' from mirror '{}'".format(pkgname, mirror))

                    pkg_downloaded = self.downloader.download(file_url=url, watcher=watcher, output_path=output_path,
                                                              cwd='.', root_password=root_password, display_file_size=True,
                                                              substatus_prefix=substatus_prefix,
                                                              known_size=size)
                    if not pkg_downloaded:
                        watcher.print("Could not download '{}' from mirror '{}'".format(pkgname, mirror))
                    else:
                        self.logger.info("Package '{}' successfully downloaded".format(pkg['n']))
                        t = Thread(target=self.download_package_signature, args=(pkg, url, output_path, root_password, watcher), daemon=True)
                        t.start()
                        self.async_downloads_lock.acquire()
                        self.async_downloads.append(t)
                        self.async_downloads_lock.release()
                        return True
        return False

    def wait_for_async_downloads(self):
        self.async_downloads_lock.acquire()

        try:
            if self.async_downloads:
                for t in self.async_downloads:
                    t.join()

            self.async_downloads.clear()
        finally:
            self.async_downloads_lock.release()


class MultithreadedDownloadService:

    def __init__(self, file_downloader: FileDownloader, http_client: HttpClient, logger: logging.Logger, i18n: I18n):
        self.file_downloader = file_downloader
        self.http_client = http_client
        self.logger = logger
        self.i18n = i18n

    def download_packages(self, pkgs: List[str], handler: ProcessHandler, root_password: str, sizes: Dict[str, int] = None) -> int:
        ti = time.time()
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
                                             logger=self.logger,
                                             cache_dir=cache_dir)

        downloaded = 0
        pkgs_data = pacman.list_download_data(pkgs)

        if not pkgs_data:
            error_msg = "Could not retrieve download data of the following packages: {}".format(', '.join(pkgs))
            watcher.print(error_msg)
            self.logger.error(error_msg)
            return 0

        for pkg in pkgs_data:
            self.logger.info('Preparing to download package: {} ({})'.format(pkg['n'], pkg['v']))
            try:
                perc = '({0:.2f}%)'.format((downloaded / (2 * len(pkgs))) * 100)
                status_prefix = '{} [{}/{}]'.format(perc, downloaded + 1, len(pkgs))

                if downloader.download_package(pkg=pkg,
                                               root_password=root_password,
                                               watcher=handler.watcher,
                                               substatus_prefix=status_prefix,
                                               size=sizes.get(pkg['n']) if sizes else None):
                    downloaded += 1
            except:
                traceback.print_exc()
                watcher.show_message(title=self.i18n['error'].capitalize(),
                                     body=self.i18n['arch.mthread_downloaded.error.cancelled'],
                                     type_=MessageType.ERROR)
                raise ArchDownloadException()

        self.logger.info("Waiting for signature downloads to complete")
        downloader.wait_for_async_downloads()
        self.logger.info("Signature downloads finished")
        tf = time.time()
        self.logger.info("Download time: {0:.2f} seconds".format(tf - ti))
        return downloaded
