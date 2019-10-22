import logging
import os
import re
import time
import traceback
from math import ceil
from multiprocessing import Process
from pathlib import Path
from threading import Thread
from typing import Dict, List

import requests

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.constants import HOME_PATH, CACHE_PATH
from bauh.api.http import HttpClient
from bauh.gems.arch import pacman, disk, ARCH_CACHE_PATH

URL_INDEX = 'https://aur.archlinux.org/packages.gz'
URL_INFO = 'https://aur.archlinux.org/rpc/?v=5&type=info&arg={}'

GLOBAL_MAKEPKG = '/etc/makepkg.conf'
USER_MAKEPKG = '{}/.makepkg.conf'.format(HOME_PATH)

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
        self.compilation_optimizations = bool(int(os.getenv('BAUH_ARCH_OPTIMIZE', 1)))

    def run(self):

        if not self.compilation_optimizations:
            self.logger.info("Arch packages compilation optimization is disabled. Aborting...")
        else:
            try:
                ncpus = ceil(os.cpu_count() * 1.5)
            except:
                self.logger.error('Could not determine the number of processors. Aborting...')
                ncpus = None

            if os.path.exists(GLOBAL_MAKEPKG) and not os.path.exists(USER_MAKEPKG):
                self.logger.info("Verifying if it is possible to optimize Arch packages compilation")

                with open(GLOBAL_MAKEPKG) as f:
                    global_makepkg = f.read()

                user_makepkg, optimizations = None, []

                if ncpus:
                    makeflags = RE_MAKE_FLAGS.findall(global_makepkg)

                    if makeflags:
                        not_commented = [f for f in makeflags if not f.startswith('#')]

                        if not not_commented:
                            user_makepkg = RE_MAKE_FLAGS.sub('', global_makepkg)
                            optimizations.append('MAKEFLAGS="-j$(nproc)"')
                        else:
                            self.logger.warning("It seems '{}' compilation flags are already customized".format(GLOBAL_MAKEPKG))
                    else:
                        optimizations.append('MAKEFLAGS="-j$(nproc)"')

                compress_xz = RE_COMPRESS_XZ.findall(user_makepkg if user_makepkg else global_makepkg)

                if compress_xz:
                    not_eligible = [f for f in compress_xz if not f.startswith('#') and '--threads' in f]

                    if not not_eligible:
                        user_makepkg = RE_COMPRESS_XZ.sub('', global_makepkg)
                        optimizations.append('COMPRESSXZ=(xz -c -z - --threads=0)')
                    else:
                        self.logger.warning("It seems '{}' COMPRESSXZ is already customized".format(GLOBAL_MAKEPKG))
                else:
                    optimizations.append('COMPRESSXZ=(xz -c -z - --threads=0)')

                if optimizations:
                    generated_by = '# <generated by bauh>\n'
                    user_makepkg = generated_by + user_makepkg + '\n' + generated_by + '\n'.join(optimizations) + '\n'

                    with open(USER_MAKEPKG, 'w+') as f:
                        f.write(user_makepkg)

                    self.logger.info("A custom optimized 'makepkg.conf' was generated at '{}'".format(HOME_PATH))
            else:
                self.logger.warning("A custom 'makepkg.conf' is already defined at '{}'".format(HOME_PATH))


class AURCategoriesMapper(Thread):

    URL_CATEGORIES_FILE = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/aur/categories.txt'
    CATEGORIES_CACHE_DIR = ARCH_CACHE_PATH + '/categories'
    CATEGORIES_FILE_PATH = CATEGORIES_CACHE_DIR + '/aur.txt'

    def __init__(self, http_client: HttpClient, logger: logging.Logger, manager: SoftwareManager, disk_cache: bool):
        super(AURCategoriesMapper, self).__init__(daemon=True)
        self.http_client = http_client
        self.logger = logger
        self.manager = manager
        self.disk_cache = disk_cache

    def _read_categories_from_disk(self) -> dict:
        if self.disk_cache and os.path.exists(self.CATEGORIES_FILE_PATH):
            self.logger.info("Reading cached categories from the disk")

            with open(self.CATEGORIES_FILE_PATH) as f:
                categories = f.read()

            return self._map_categories(categories)

        return {}

    def _map_categories(self, categories: str) -> dict:
        categories_map = {}
        for l in categories.split('\n'):
            if l:
                data = l.split('=')
                categories_map[data[0]] = [c.strip() for c in data[1].split(',') if c]
        return categories_map

    def _cache_categories_to_disk(self, categories: str):
        self.logger.info('Caching AUR categories to the disk')

        try:
            Path(self.CATEGORIES_CACHE_DIR).mkdir(parents=True, exist_ok=True)

            with open(self.CATEGORIES_FILE_PATH, 'w+') as f:
                f.write(categories)

            self.logger.info("AUR categories cached to the disk as '{}'".format(self.CATEGORIES_FILE_PATH))
        except:
            self.logger.error("Could not cache AUR categories to the disk as '{}'".format(self.CATEGORIES_FILE_PATH))
            traceback.print_exc()

    def get_categories(self) -> Dict[str, List[str]]:
        self.logger.info('Downloading AUR category definitions from {}'.format(self.URL_CATEGORIES_FILE))

        try:
            res = self.http_client.get(self.URL_CATEGORIES_FILE)

            if res:
                try:
                    categories_map = self._map_categories(res.text)
                    self.logger.info('Loaded categories for {} AUR packages'.format(len(categories_map)))

                    if self.disk_cache and categories_map:
                        t = Thread(target=self._cache_categories_to_disk, args=(res.text,), daemon=True)
                        t.start()

                    return categories_map
                except:
                    self.logger.error("Could not parse AUR categories definitions")
                    traceback.print_exc()
            else:
                self.logger.info('Could not download {}'.format(self.URL_CATEGORIES_FILE))

        except requests.exceptions.ConnectionError:
            self.logger.warning('The internet connection seems to be off.')

        return self._read_categories_from_disk()

    def run(self):
        categories = self.get_categories()

        if categories:
            self.logger.info("Settings categories to {}".format(self.manager.__class__.__name__))
            self.manager.categories_map = categories
            self.logger.info('Finished')
