import time

from bauh.api.abstract.download import FileDownloader
from bauh.api.http import HttpClient
from bauh.gems.arch import pacman
from bauh.gems.arch.model import ArchPackage


class MultiThreadedDownloader:

    def __init__(self, file_downloader: FileDownloader, http_client: HttpClient):
        self.downloader = file_downloader
        self.http_client = http_client
        self.mirrors = pacman.list_available_mirrors()  # TODO sort by the fastest
        self.branch = pacman.get_mirrors_branch()
        self.extensions = ['.tar.zst', '.tar.xz']

    def download_package(self, pkg: ArchPackage, output_dir: str) -> bool:
        arch = pkg.arch if pkg.arch and pkg.arch != 'any' else 'x86_64'
        pkgname = '{}-{}{}.pkg'.format(pkg.name, pkg.latest_version, ('-{}'.format(pkg.arch) if pkg.arch else ''))
        url_base = '{}/{}/{}/{}'.format(self.branch, pkg.repository, arch, pkgname)
        for mirror in self.mirrors:
            for ext in self.extensions:
                url = '{}{}{}'.format(mirror, url_base, ext)

                if self.http_client.exists(url, timeout=1):
                    # TODO download
                    return True

        return False


if __name__ == '__main__':
    from unittest.mock import Mock
    from bauh.view.core.downloader import AdaptableFileDownloader

    logger = Mock()
    client = HttpClient(logger=logger)
    i18n = {}
    fd = AdaptableFileDownloader(logger=logger, http_client=client, i18n=i18n, multithread_enabled=True)
    md = MultiThreadedDownloader(file_downloader=fd, http_client=client)
    pkg = ArchPackage(name='kodi', arch='x86_64', latest_version='18.6-1', repository='community')
    ti = time.time()
    res = md.download_package(pkg, '/tmp')
    tf = time.time()
    print('{} -> {}s'.format(res, tf - ti))
