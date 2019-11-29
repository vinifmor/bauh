import logging
import os
import re
import time
from math import ceil
from multiprocessing import Process
from pathlib import Path
from threading import Thread

import requests

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager
from bauh.gems.arch import pacman, disk, CUSTOM_MAKEPKG_PATH, CONFIG_DIR, should_optimize_compilation

URL_INDEX = 'https://aur.archlinux.org/packages.gz'
URL_INFO = 'https://aur.archlinux.org/rpc/?v=5&type=info&arg={}'

GLOBAL_MAKEPKG = '/etc/makepkg.conf'

RE_MAKE_FLAGS = re.compile(r'#?\s*MAKEFLAGS\s*=\s*.+\s*')
RE_COMPRESS_XZ = re.compile(r'#?\s*COMPRESSXZ\s*=\s*.+')


class AURIndexUpdater(Thread):

    def __init__(self, context: ApplicationContext, man: SoftwareManager):
        super(AURIndexUpdater, self).__init__(daemon=True)
        self.http_client = context.http_client
        self.logger = context.logger
        self.man = man
        self.enabled = bool(int(os.getenv('BAUH_ARCH_AUR_INDEX_UPDATER', 1)))

    def run(self):
        if self.enabled:
            while True:
                self.logger.info('Pre-indexing AUR packages in memory')
                try:
                    res = self.http_client.get(URL_INDEX)

                    if res and res.text:
                        self.man.names_index = {n.replace('-', '').replace('_', '').replace('.', ''): n for n in res.text.split('\n') if n and not n.startswith('#')}
                        self.logger.info('Pre-indexed {} AUR package names in memory'.format(len(self.man.names_index)))
                    else:
                        self.logger.warning('No data returned from: {}'.format(URL_INDEX))
                except requests.exceptions.ConnectionError:
                    self.logger.warning('No internet connection: could not pre-index packages')

                time.sleep(60 * 20)  # updates every 20 minutes
        else:
            self.logger.info("AUR index updater disabled")


class ArchDiskCacheUpdater(Thread if bool(os.getenv('BAUH_DEBUG', 0)) else Process):

    def __init__(self, logger: logging.Logger, disk_cache: bool):
        super(ArchDiskCacheUpdater, self).__init__(daemon=True)
        self.logger = logger
        self.disk_cache = disk_cache

    def run(self):
        if self.disk_cache:
            self.logger.info('Pre-caching installed AUR packages data to disk')
            installed = pacman.list_and_map_installed()

            saved = 0
            if installed and installed['not_signed']:
                saved = disk.save_several({app for app in installed['not_signed']}, 'aur', overwrite=False)

            self.logger.info('Pre-cached data of {} AUR packages to the disk'.format(saved))


class ArchCompilationOptimizer(Thread if bool(os.getenv('BAUH_DEBUG', 0)) else Process):

    def __init__(self, logger: logging.Logger):
        super(ArchCompilationOptimizer, self).__init__(daemon=True)
        self.logger = logger

    def run(self):

        if not should_optimize_compilation():
            self.logger.info("Arch packages compilation optimization is disabled")

            if os.path.exists(CUSTOM_MAKEPKG_PATH):
                self.logger.info("Removing custom 'makepkg.conf' -> '{}'".format(CUSTOM_MAKEPKG_PATH))
                os.remove(CUSTOM_MAKEPKG_PATH)

            self.logger.info('Finished')
        else:
            try:
                ncpus = os.cpu_count()
            except:
                self.logger.error('Could not determine the number of processors. Aborting...')
                ncpus = None

            if os.path.exists(GLOBAL_MAKEPKG):
                self.logger.info("Verifying if it is possible to optimize Arch packages compilation")

                with open(GLOBAL_MAKEPKG) as f:
                    global_makepkg = f.read()

                Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)

                custom_makepkg, optimizations = None, []

                if ncpus:
                    makeflags = RE_MAKE_FLAGS.findall(global_makepkg)

                    if makeflags:
                        not_commented = [f for f in makeflags if not f.startswith('#')]

                        if not not_commented:
                            custom_makepkg = RE_MAKE_FLAGS.sub('', global_makepkg)
                            optimizations.append('MAKEFLAGS="-j$(nproc)"')
                        else:
                            self.logger.warning("It seems '{}' compilation flags are already customized".format(GLOBAL_MAKEPKG))
                    else:
                        optimizations.append('MAKEFLAGS="-j$(nproc)"')

                compress_xz = RE_COMPRESS_XZ.findall(custom_makepkg if custom_makepkg else global_makepkg)

                if compress_xz:
                    not_eligible = [f for f in compress_xz if not f.startswith('#') and '--threads' in f]

                    if not not_eligible:
                        custom_makepkg = RE_COMPRESS_XZ.sub('', global_makepkg)
                        optimizations.append('COMPRESSXZ=(xz -c -z - --threads=0)')
                    else:
                        self.logger.warning("It seems '{}' COMPRESSXZ is already customized".format(GLOBAL_MAKEPKG))
                else:
                    optimizations.append('COMPRESSXZ=(xz -c -z - --threads=0)')

                if optimizations:
                    generated_by = '# <generated by bauh>\n'
                    custom_makepkg = generated_by + custom_makepkg + '\n' + generated_by + '\n'.join(optimizations) + '\n'

                    with open(CUSTOM_MAKEPKG_PATH, 'w+') as f:
                        f.write(custom_makepkg)

                    self.logger.info("A custom optimized 'makepkg.conf' was generated at '{}'".format(CUSTOM_MAKEPKG_PATH))
                else:
                    self.logger.info("No optimizations are necessary")

                    if os.path.exists(CUSTOM_MAKEPKG_PATH):
                        self.logger.info("Removing old optimized 'makepkg.conf' at '{}'".format(CUSTOM_MAKEPKG_PATH))
                        os.remove(CUSTOM_MAKEPKG_PATH)

                self.logger.info('Finished')
