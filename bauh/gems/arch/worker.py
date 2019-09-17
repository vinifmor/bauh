import logging
import os
import time
from multiprocessing import Process
from threading import Thread

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager

from bauh.gems.arch import pacman, disk

URL_INDEX = 'https://aur.archlinux.org/packages.gz'
URL_INFO = 'https://aur.archlinux.org/rpc/?v=5&type=info&arg={}'


class AURIndexUpdater(Thread):

    def __init__(self, context: ApplicationContext, man: SoftwareManager):
        super(AURIndexUpdater, self).__init__(daemon=True)
        self.http_client = context.http_client
        self.logger = context.logger
        self.man = man

    def run(self):
        while True:
            self.logger.info('Pre-indexing AUR packages in memory')
            res = self.http_client.get(URL_INDEX)

            if res and res.text:
                self.man.names_index = {n.replace('-', '').replace('_', '').replace('.', ''): n for n in res.text.split('\n') if n and not n.startswith('#')}
                self.logger.info('Pre-indexed {} AUR package names in memory'.format(len(self.man.names_index)))
            else:
                self.logger.warning('No data returned from: {}'.format(URL_INDEX))

            time.sleep(5 * 60)  # updates every 5 minutes


class ArchDiskCacheUpdater(Thread if bool(os.getenv('BAUH_DEBUG', 0)) else Process):

    def __init__(self, logger: logging.Logger):
        super(ArchDiskCacheUpdater, self).__init__(daemon=True)
        self.logger = logger

    def run(self):
        self.logger.info('Pre-caching installed AUR packages data to disk')
        installed = pacman.list_and_map_installed()

        saved = 0
        if installed and installed['not_signed']:
            saved = disk.save_several({app for app in installed['not_signed']}, 'aur', overwrite=False)

        self.logger.info('Pre-cached data of {} AUR packages to the disk'.format(saved))
