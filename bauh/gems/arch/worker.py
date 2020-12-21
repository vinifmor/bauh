import glob
import logging
import os
import re
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Optional

import requests

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.handler import TaskManager
from bauh.commons.html import bold
from bauh.commons.system import run_cmd, new_root_subprocess, ProcessHandler
from bauh.commons.util import datetime_as_milis
from bauh.gems.arch import pacman, disk, CUSTOM_MAKEPKG_FILE, CONFIG_DIR, AUR_INDEX_FILE, get_icon_path, database, \
    mirrors, ARCH_CACHE_PATH, BUILD_DIR, AUR_INDEX_TS_FILE
from bauh.gems.arch.aur import URL_INDEX
from bauh.view.util.translation import I18n

URL_INFO = 'https://aur.archlinux.org/rpc/?v=5&type=info&arg={}'

GLOBAL_MAKEPKG = '/etc/makepkg.conf'

RE_MAKE_FLAGS = re.compile(r'#?\s*MAKEFLAGS\s*=\s*.+\s*')
RE_CLEAR_REPLACE = re.compile(r'[\-_.]')


class AURIndexUpdater(Thread):

    def __init__(self, context: ApplicationContext, taskman: TaskManager):
        super(AURIndexUpdater, self).__init__(daemon=True)
        self.http_client = context.http_client
        self.i18n = context.i18n
        self.logger = context.logger
        self.taskman = taskman
        self.task_id = 'index_aur'

    @staticmethod
    def should_update(arch_config: dict) -> bool:
        try:
            exp_minutes = int(arch_config['aur_idx_exp'])
        except:
            traceback.print_exc()
            return True

        if exp_minutes <= 0:
            return True

        if not os.path.exists(AUR_INDEX_FILE):
            return True

        if not os.path.exists(AUR_INDEX_TS_FILE):
            return True

        with open(AUR_INDEX_TS_FILE) as f:
            timestamp_str = f.read()

        try:
            index_timestamp = datetime.fromtimestamp(float(timestamp_str))
            return (index_timestamp + timedelta(minutes=exp_minutes)) <= datetime.utcnow()
        except:
            traceback.print_exc()
            return True

    def run(self):
        ti = time.time()
        self.logger.info('Indexing AUR packages')
        self.taskman.register_task(self.task_id, self.i18n['arch.task.aur.index.status'], get_icon_path())
        self.taskman.update_progress(self.task_id, 1, self.i18n['arch.task.aur.index.substatus.download'])
        try:
            index_ts = datetime.utcnow().timestamp()
            res = self.http_client.get(URL_INDEX)

            if res and res.text:
                index_progress = 50
                self.taskman.update_progress(self.task_id, index_progress,
                                             self.i18n['arch.task.aur.index.substatus.gen_index'])
                indexed = 0

                Path(os.path.dirname(AUR_INDEX_FILE)).mkdir(parents=True, exist_ok=True)

                with open(AUR_INDEX_FILE, 'w+') as f:
                    lines = res.text.split('\n')
                    progress_inc = round(len(lines) / 50)  # 1%

                    perc_count = 0
                    for n in lines:
                        if index_progress < 100 and perc_count == progress_inc:
                            index_progress += 1
                            perc_count = 0
                            self.taskman.update_progress(self.task_id, index_progress,
                                                         self.i18n['arch.task.aur.index.substatus.gen_index'])

                        if n and not n.startswith('#'):
                            f.write('{}={}\n'.format(RE_CLEAR_REPLACE.sub('', n), n))
                            indexed += 1

                        perc_count += 1

                with open(AUR_INDEX_TS_FILE, 'w+') as f:
                    f.write(str(index_ts))

                self.logger.info('Pre-indexed {} AUR package names at {}'.format(indexed, AUR_INDEX_FILE))
                self.taskman.update_progress(self.task_id, 100, None)

            else:
                self.logger.warning('No data returned from: {}'.format(URL_INDEX))
                self.taskman.update_progress(self.task_id, 100, self.i18n['arch.task.aur.index.substatus.error.no_data'])

        except requests.exceptions.ConnectionError:
            self.logger.warning('No internet connection: could not pre-index packages')
            self.taskman.update_progress(self.task_id, 100, self.i18n['arch.task.aur.index.substatus.error.download'])

        tf = time.time()
        self.taskman.finish_task(self.task_id)
        self.logger.info("Finished. Took {0:.2f} seconds".format(tf - ti))


class ArchDiskCacheUpdater(Thread):

    def __init__(self, task_man: TaskManager, arch_config: dict, i18n: I18n, logger: logging.Logger, controller: "ArchManager", internet_available: bool,
                 aur_supported: bool, aur_indexer: Thread):
        super(ArchDiskCacheUpdater, self).__init__(daemon=True)
        self.logger = logger
        self.task_man = task_man
        self.task_id = 'arch_cache_up'
        self.i18n = i18n
        self.indexed = 0
        self.indexed_template = self.i18n['arch.task.disk_cache.indexed'] + ': {}/ {}'
        self.to_index = 0
        self.progress = 0  # progress is defined by the number of packages prepared and indexed
        self.repositories = arch_config['repositories']
        self.aur = aur_supported
        self.controller = controller
        self.internet_available = internet_available
        self.installed_hash_path = '{}/installed.sha1'.format(ARCH_CACHE_PATH)
        self.installed_cache_dir = '{}/installed'.format(ARCH_CACHE_PATH)
        self.aur_indexer = aur_indexer

    def update_indexed(self, pkgname: str):
        self.indexed += 1
        sub = self.indexed_template.format(self.indexed, self.to_index)
        progress = self.progress + (self.indexed / self.to_index) * 50
        self.task_man.update_progress(self.task_id, progress, sub)

    def _update_progress(self, progress: float, msg: str):
        self.progress = progress
        self.task_man.update_progress(self.task_id, self.progress, msg)

    def _notify_reading_files(self):
        self._update_progress(50, self.i18n['arch.task.disk_cache.indexing'])

    def run(self):
        if not any([self.aur, self.repositories]):
            return

        ti = time.time()
        self.task_man.register_task(self.task_id, self.i18n['arch.task.disk_cache'], get_icon_path())

        self.logger.info("Checking already cached package data")

        self._update_progress(1, self.i18n['arch.task.disk_cache.checking'])
        cache_dirs = [fpath for fpath in glob.glob('{}/*'.format(self.installed_cache_dir)) if os.path.isdir(fpath)]

        not_cached_names = None

        self._update_progress(15, self.i18n['arch.task.disk_cache.checking'])
        if cache_dirs:  # if there are cache data
            installed_names = pacman.list_installed_names()
            cached_pkgs = {cache_dir.split('/')[-1] for cache_dir in cache_dirs}

            not_cached_names = installed_names.difference(cached_pkgs)
            self._update_progress(20, self.i18n['arch.task.disk_cache.checking'])

            if not not_cached_names:
                self.task_man.update_progress(self.task_id, 100, '')
                self.task_man.finish_task(self.task_id)
                tf = time.time()
                time_msg = '{0:.2f} seconds'.format(tf - ti)
                self.logger.info('Finished: no package data to cache ({})'.format(time_msg))
                return

        self.logger.info('Pre-caching installed Arch packages data to disk')

        if self.aur and self.aur_indexer:
            self.task_man.update_progress(self.task_id, 20, self.i18n['arch.task.disk_cache.waiting_aur_index'].format(bold(self.i18n['arch.task.aur.index.status'])))
            self.aur_indexer.join()

        self._update_progress(21, self.i18n['arch.task.disk_cache.checking'])
        installed = self.controller.read_installed(disk_loader=None, internet_available=self.internet_available,
                                                   only_apps=False, pkg_types=None, limit=-1, names=not_cached_names,
                                                   wait_disk_cache=False).installed

        self._update_progress(35, self.i18n['arch.task.disk_cache.checking'])

        saved = 0

        pkgs = {p.name: p for p in installed if ((self.aur and p.repository == 'aur') or (self.repositories and p.repository != 'aur')) and not os.path.exists(p.get_disk_cache_path())}
        self.to_index = len(pkgs)

        # overwrite == True because the verification already happened
        self._update_progress(40, self.i18n['arch.task.disk_cache.reading_files'])
        saved += disk.write_several(pkgs=pkgs,
                                    after_desktop_files=self._notify_reading_files,
                                    after_written=self.update_indexed, overwrite=True)
        self.task_man.update_progress(self.task_id, 100, None)
        self.task_man.finish_task(self.task_id)

        tf = time.time()
        time_msg = '{0:.2f} seconds'.format(tf - ti)
        self.logger.info('Finished: pre-cached data of {} Arch packages to the disk ({})'.format(saved, time_msg))


class ArchCompilationOptimizer(Thread):

    def __init__(self, arch_config: dict, i18n: I18n, logger: logging.Logger, taskman: Optional[TaskManager] = None):
        super(ArchCompilationOptimizer, self).__init__(daemon=True)
        self.logger = logger
        self.i18n = i18n
        self.re_compress_xz = re.compile(r'#?\s*COMPRESSXZ\s*=\s*.+')
        self.re_compress_zst = re.compile(r'#?\s*COMPRESSZST\s*=\s*.+')
        self.re_build_env = re.compile(r'\s+BUILDENV\s*=.+')
        self.re_ccache = re.compile(r'!?ccache')
        self.taskman = taskman
        self.task_id = 'arch_make_optm'
        self.optimizations = bool(arch_config['optimize'])

    def _is_ccache_installed(self) -> bool:
        return bool(run_cmd('which ccache', print_error=False))

    def _update_progress(self, progress: float, substatus: str = None):
        if self.taskman:
            self.taskman.update_progress(self.task_id, progress, substatus)

            if progress == 100:
                self.taskman.finish_task(self.task_id)

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

            self._update_progress(20)

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

            self._update_progress(40)

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

            self._update_progress(60)

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

            self._update_progress(80)

            if custom_makepkg and optimizations:
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
            self._update_progress(100)
            self.logger.info("Optimizations took {0:.2f} seconds".format(tf - ti))
            self.logger.info('Finished')

    def run(self):
        if not self.optimizations:
            self.logger.info("Arch packages compilation optimizations are disabled")

            if os.path.exists(CUSTOM_MAKEPKG_FILE):
                self.logger.info("Removing custom 'makepkg.conf' -> '{}'".format(CUSTOM_MAKEPKG_FILE))
                os.remove(CUSTOM_MAKEPKG_FILE)

            self.logger.info('Finished')
        else:
            if self.taskman:
                self.taskman.register_task(self.task_id, self.i18n['arch.task.optimizing'].format(bold('makepkg.conf')), get_icon_path())

            self.optimize()


class RefreshMirrors(Thread):

    def __init__(self, taskman: TaskManager, root_password: str, i18n: I18n, sort_limit: int, logger: logging.Logger):
        super(RefreshMirrors, self).__init__(daemon=True)
        self.taskman = taskman
        self.i18n = i18n
        self.logger = logger
        self.root_password = root_password
        self.task_id = "arch_mirrors"
        self.sort_limit = sort_limit

    def _notify_output(self, output: str):
        self.taskman.update_output(self.task_id, output)

    def run(self):
        self.taskman.register_task(self.task_id, self.i18n['arch.task.mirrors'], get_icon_path())
        self.logger.info("Refreshing mirrors")

        handler = ProcessHandler()
        try:
            self.taskman.update_progress(self.task_id, 10, '')
            success, output = handler.handle_simple(pacman.refresh_mirrors(self.root_password), output_handler=self._notify_output)

            if success:

                if self.sort_limit is not None and self.sort_limit >= 0:
                    self.taskman.update_progress(self.task_id, 50, self.i18n['arch.custom_action.refresh_mirrors.status.updating'])
                    try:
                        handler.handle_simple(pacman.sort_fastest_mirrors(self.root_password, self.sort_limit), output_handler=self._notify_output)
                    except:
                        self.logger.error("Could not sort mirrors by speed")
                        traceback.print_exc()

                mirrors.register_sync(self.logger)
            else:
                self.logger.error("It was not possible to refresh mirrors")
        except:
            self.logger.error("It was not possible to refresh mirrors")
            traceback.print_exc()

        self.taskman.update_progress(self.task_id, 100, None)
        self.taskman.finish_task(self.task_id)
        self.logger.info("Finished")


class SyncDatabases(Thread):

    def __init__(self, taskman: TaskManager, root_password: str, i18n: I18n, logger: logging.Logger, refresh_mirrors: RefreshMirrors = None):
        super(SyncDatabases, self).__init__(daemon=True)
        self.task_man = taskman
        self.i18n = i18n
        self.taskman = taskman
        self.task_id = "arch_dbsync"
        self.root_password = root_password
        self.refresh_mirrors = refresh_mirrors
        self.logger = logger

    def run(self) -> None:
        self.logger.info("Synchronizing databases")
        self.taskman.register_task(self.task_id, self.i18n['arch.sync_databases.substatus'], get_icon_path())

        if self.refresh_mirrors and self.refresh_mirrors.is_alive():
            self.taskman.update_progress(self.task_id, 0, self.i18n['arch.task.sync_databases.waiting'].format('"{}"'.format(self.i18n['arch.task.mirrors'])))
            self.refresh_mirrors.join()

        progress = 10
        dbs = pacman.get_databases()
        self.taskman.update_progress(self.task_id, progress, None)

        if dbs:
            inc = 90 / len(dbs)
            try:
                p = new_root_subprocess(['pacman', '-Syy'], self.root_password)

                dbs_read, last_db = 0, None

                for o in p.stdout:
                    line = o.decode().strip()

                    if line:
                        self.task_man.update_output(self.task_id, line)
                        if line.startswith('downloading'):
                            db = line.split(' ')[1].strip()

                            if last_db is None or last_db != db:
                                last_db = db
                                dbs_read += 1
                                progress = dbs_read * inc
                            else:
                                progress += 0.25

                            self.taskman.update_progress(self.task_id, progress, self.i18n['arch.task.sync_sb.status'].format(db))

                for o in p.stderr:
                    line = o.decode().strip()

                    if line:
                        self.task_man.update_output(self.task_id, line)

                p.wait()

                if p.returncode == 0:
                    database.register_sync(self.logger)
                else:
                    self.logger.error("Could not synchronize database")

            except:
                self.logger.info("Error while synchronizing databases")
                traceback.print_exc()

        self.taskman.update_progress(self.task_id, 100, None)
        self.taskman.finish_task(self.task_id)
        self.logger.info("Finished")
