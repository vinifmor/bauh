import logging
import os
import re
import time
from multiprocessing import Process
from pathlib import Path
from threading import Thread

import requests

from bauh.api.abstract.context import ApplicationContext
from bauh.commons.system import run_cmd
from bauh.gems.arch import pacman, disk, CUSTOM_MAKEPKG_FILE, CONFIG_DIR, BUILD_DIR, \
    AUR_INDEX_FILE, config

URL_INDEX = 'https://aur.archlinux.org/packages.gz'
URL_INFO = 'https://aur.archlinux.org/rpc/?v=5&type=info&arg={}'

GLOBAL_MAKEPKG = '/etc/makepkg.conf'

RE_MAKE_FLAGS = re.compile(r'#?\s*MAKEFLAGS\s*=\s*.+\s*')
RE_CLEAR_REPLACE = re.compile(r'[\-_.]')


class AURIndexUpdater(Thread):

    def __init__(self, context: ApplicationContext):
        super(AURIndexUpdater, self).__init__(daemon=True)
        self.http_client = context.http_client
        self.logger = context.logger

    def run(self):
        self.logger.info('Pre-indexing AUR packages')
        try:
            res = self.http_client.get(URL_INDEX)

            if res and res.text:
                indexed = 0
                Path(BUILD_DIR).mkdir(parents=True, exist_ok=True)

                with open(AUR_INDEX_FILE, 'w+') as f:
                    for n in res.text.split('\n'):
                        if n and not n.startswith('#'):
                            f.write('{}={}\n'.format(RE_CLEAR_REPLACE.sub('', n), n))
                            indexed += 1

                self.logger.info('Pre-indexed {} AUR package names at {}'.format(indexed, AUR_INDEX_FILE))
            else:
                self.logger.warning('No data returned from: {}'.format(URL_INDEX))
        except requests.exceptions.ConnectionError:
            self.logger.warning('No internet connection: could not pre-index packages')


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


class ArchCompilationOptimizer(Thread):

    def __init__(self, logger: logging.Logger):
        super(ArchCompilationOptimizer, self).__init__(daemon=True)
        self.logger = logger
        self.re_compress_xz = re.compile(r'#?\s*COMPRESSXZ\s*=\s*.+')
        self.re_compress_zst = re.compile(r'#?\s*COMPRESSZST\s*=\s*.+')
        self.re_build_env = re.compile(r'\s+BUILDENV\s*=.+')
        self.re_ccache = re.compile(r'!?ccache')

    def _is_ccache_installed(self) -> bool:
        return bool(run_cmd('which ccache', print_error=False))

    def optimize(self):
        ti = time.time()
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

            compress_xz = self.re_compress_xz.findall(custom_makepkg or global_makepkg)

            if compress_xz:
                not_eligible = [f for f in compress_xz if not f.startswith('#') and '--threads' in f]

                if not not_eligible:
                    custom_makepkg = self.re_compress_xz.sub('', custom_makepkg or global_makepkg)
                    optimizations.append('COMPRESSXZ=(xz -c -z - --threads=0)')
                else:
                    self.logger.warning("It seems '{}' COMPRESSXZ is already customized".format(GLOBAL_MAKEPKG))
            else:
                optimizations.append('COMPRESSXZ=(xz -c -z - --threads=0)')

            compress_zst = self.re_compress_zst.findall(custom_makepkg or global_makepkg)

            if compress_zst:
                not_eligible = [f for f in compress_zst if not f.startswith('#') and '--threads' in f]

                if not not_eligible:
                    custom_makepkg = self.re_compress_zst.sub('', custom_makepkg or global_makepkg)
                    optimizations.append('COMPRESSZST=(zstd -c -z -q - --threads=0)')
                else:
                    self.logger.warning("It seems '{}' COMPRESSZST is already customized".format(GLOBAL_MAKEPKG))
            else:
                optimizations.append('COMPRESSZST=(zstd -c -z -q - --threads=0)')

            build_envs = self.re_build_env.findall(custom_makepkg or global_makepkg)

            if build_envs:
                build_def = None
                for e in build_envs:
                    env_line = e.strip()

                    ccache_defs = self.re_ccache.findall(env_line)
                    ccache_installed = self._is_ccache_installed()

                    if ccache_defs:
                        if ccache_installed:
                            custom_makepkg = (custom_makepkg or global_makepkg).replace(e, '')

                            if not build_def:
                                build_def = self.re_ccache.sub('', env_line).replace('(', '(ccache ')
                        elif not build_def:
                            build_def = self.re_ccache.sub('', env_line)

                if build_def:
                    optimizations.append(build_def)
            else:
                self.logger.warning("No BUILDENV declaration found")

                if self._is_ccache_installed():
                    self.logger.info('Adding a BUILDENV declaration')
                    optimizations.append('BUILDENV=(ccache)')

            if optimizations:
                generated_by = '# <generated by bauh>\n'
                custom_makepkg = custom_makepkg + '\n' + generated_by + '\n'.join(optimizations) + '\n'

                with open(CUSTOM_MAKEPKG_FILE, 'w+') as f:
                    f.write(custom_makepkg)

                self.logger.info("A custom optimized 'makepkg.conf' was generated at '{}'".format(CUSTOM_MAKEPKG_FILE))
            else:
                self.logger.info("No optimizations are necessary")

                if os.path.exists(CUSTOM_MAKEPKG_FILE):
                    self.logger.info("Removing old optimized 'makepkg.conf' at '{}'".format(CUSTOM_MAKEPKG_FILE))
                    os.remove(CUSTOM_MAKEPKG_FILE)

            tf = time.time()
            self.logger.info("Optimizations took {0:.2f} seconds".format(tf - ti))
            self.logger.info('Finished')

    def run(self):
        local_config = config.read_config(update_file=True)

        if not local_config['optimize']:
            self.logger.info("Arch packages compilation optimizations are disabled")

            if os.path.exists(CUSTOM_MAKEPKG_FILE):
                self.logger.info("Removing custom 'makepkg.conf' -> '{}'".format(CUSTOM_MAKEPKG_FILE))
                os.remove(CUSTOM_MAKEPKG_FILE)

            self.logger.info('Finished')
        else:
           self.optimize()
