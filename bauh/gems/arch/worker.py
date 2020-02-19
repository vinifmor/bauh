import logging
import os
import re
import time
from pathlib import Path
from threading import Thread

import requests

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.handler import TaskManager
from bauh.commons.system import run_cmd
from bauh.gems.arch import pacman, disk, CUSTOM_MAKEPKG_FILE, CONFIG_DIR, BUILD_DIR, \
    AUR_INDEX_FILE, config
from bauh.gems.arch.model import ArchPackage

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


class ArchDiskCacheUpdater(Thread):

    def __init__(self, task_man: TaskManager, logger: logging.Logger):
        super(ArchDiskCacheUpdater, self).__init__(daemon=True)
        self.logger = logger
        self.task_man = task_man
        self.task_id = 'arch_cache_up'
        self.prepared = 0
        self.prepared_template = 'Prepared: {} / {}'
        self.indexed = 0
        self.indexed_template = 'Indexed: {} / {}'
        self.to_index = 0
        self.progress = 0  # progress is defined by the number of packages prepared and indexed

    def update_prepared(self, pkgname: str, add: bool = True):
        if add:
            self.prepared += 1

        sub = self.prepared_template.format(self.prepared, self.to_index)
        self.task_man.update_progress(self.task_id, ((self.prepared + self.indexed) / self.progress) * 100, sub)

    def update_indexed(self, pkgname: str):
        self.indexed += 1
        sub = self.indexed_template.format(self.indexed, self.to_index)
        self.task_man.update_progress(self.task_id, ((self.prepared + self.indexed) / self.progress) * 100, sub)

    def run(self):
        self.task_man.register_task(self.task_id, 'Indexing packages')

        ti = time.time()
        self.logger.info('Pre-caching installed Arch packages data to disk')
        installed = pacman.map_installed()

        self.task_man.update_progress(self.task_id, 0, 'Determining installed packages')
        for k in ('signed', 'not_signed'):
            installed[k] = {p for p in installed[k] if not os.path.exists(ArchPackage.disk_cache_path(p))}

        saved = 0
        pkgs = {*installed['signed'], *installed['not_signed']}

        repo_map = {}

        if installed['not_signed']:
            repo_map.update({p: 'aur' for p in installed['not_signed']})

        if installed['signed']:
            repo_map.update(pacman.map_repositories(installed['signed']))

        self.to_index = len(pkgs)
        self.progress = self.to_index * 2
        self.update_prepared(None, add=False)

        saved += disk.save_several(pkgs, repo_map, when_prepared=self.update_prepared, after_written=self.update_indexed)
        self.task_man.update_progress(self.task_id, 100, None)
        self.task_man.finish_task(self.task_id)

        tf = time.time()
        time_msg = 'Took {0:.2f} seconds'.format(tf - ti)
        self.logger.info('Pre-cached data of {} Arch packages to the disk. {}'.format(saved, time_msg))


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
