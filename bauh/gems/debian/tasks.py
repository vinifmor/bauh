import time
import traceback
from datetime import datetime, timedelta
from logging import Logger
from threading import Thread
from typing import Optional, Set

from bauh.api.abstract.handler import TaskManager, ProcessWatcher
from bauh.commons.html import bold
from bauh.commons.system import ProcessHandler
from bauh.gems.debian import DEBIAN_ICON_PATH, PACKAGE_SYNC_TIMESTAMP_FILE
from bauh.gems.debian.aptitude import Aptitude
from bauh.gems.debian.index import ApplicationIndexer, ApplicationsMapper
from bauh.gems.debian.model import DebianApplication
from bauh.view.util.translation import I18n


class MapApplications(Thread):

    def __init__(self, taskman: TaskManager, app_indexer: ApplicationIndexer, i18n: I18n, logger: Logger,
                 deb_config: dict, app_mapper: ApplicationsMapper, check_expiration: bool = True,
                 watcher: Optional[ProcessWatcher] = None):
        super(MapApplications, self).__init__()
        self._taskman = taskman
        self._i18n = i18n
        self._log = logger
        self._id = 'debian.map_apps'
        self._indexer = app_indexer
        self._config = deb_config
        self._app_mapper = app_mapper
        self._taskman.register_task(self._id, self._i18n['debian.task.map_apps.status'], DEBIAN_ICON_PATH)
        self.apps: Optional[Set[DebianApplication]] = None
        self.cached: Optional[bool] = None
        self._check_expiration = check_expiration
        self._watcher = watcher

    def _change_substatus(self, msg: str):
        if self._watcher:
            self._watcher.change_substatus(msg)

    def run(self):
        ti = time.time()
        self._log.info("Begin: mapping Debian applications")

        self._taskman.update_progress(self._id, 1, None)

        if not self._check_expiration or self._indexer.is_expired(self._config):
            status = self._i18n['debian.task.map_apps.check_files'].format(type="'.desktop")
            self._taskman.update_progress(self._id, 1, status)
            self._change_substatus(status)
            self.apps = self._app_mapper.map_executable_applications()
            self.cached = False
        else:
            status = self._i18n['debian.task.map_apps.read_cache']
            self._taskman.update_progress(self._id, 1, status)
            self._change_substatus(status)
            self.apps = {app for app in self._indexer.read_index()}
            self.cached = True

        self._log.info(f"Number of Debian applications found: {len(self.apps) if self.apps else 0}")
        self._taskman.update_progress(self._id, 100, None)
        self._taskman.finish_task(self._id)

        tf = time.time()
        self._log.info(f"Finish: mapping Debian applications ({tf - ti:.4f} seconds)")


class UpdateApplicationIndex(Thread):

    def __init__(self, taskman: TaskManager, app_indexer: ApplicationIndexer,
                 i18n: I18n, logger: Logger, mapping_apps: MapApplications,
                 watcher: Optional[ProcessWatcher] = None):
        super(UpdateApplicationIndex, self).__init__()
        self._taskman = taskman
        self._i18n = i18n
        self._log = logger
        self._id = 'debian.app_idx'
        self._indexer = app_indexer
        self._mapping_apps = mapping_apps
        self._taskman.register_task(self._id, self._i18n['debian.task.app_index.status'], DEBIAN_ICON_PATH)
        self._watcher = watcher

    def _change_substatus(self, msg: str):
        if self._watcher:
            self._watcher.change_substatus(msg)

    def run(self):
        ti = time.time()
        self._log.info("Begin: Debian applications indexation")

        self._taskman.update_progress(self._id, 1, self._i18n['task.waiting_task'].format(bold(self._i18n['debian.task.map_apps.status'])))
        self._mapping_apps.join()

        finish_msg = None
        if self._mapping_apps.cached:
            finish_msg = self._i18n['task.canceled']
        else:
            status = self._i18n['debian.task.update_apps_idx.status']
            self._taskman.update_progress(self._id, 50, status)
            self._change_substatus(status)

            try:
                self._indexer.update_index(self._mapping_apps.apps)
            except:
                finish_msg = self._i18n['error']

        self._taskman.update_progress(self._id, 100, finish_msg)
        self._taskman.finish_task(self._id)

        tf = time.time()
        self._log.info(f"Finish: Debian applications indexation ({tf - ti:.4f} seconds)")


class SynchronizePackages(Thread):

    def __init__(self, taskman: TaskManager, i18n: I18n, logger: Logger, root_password: Optional[str],
                 aptitude: Aptitude, watcher: Optional[ProcessWatcher] = None):
        super(SynchronizePackages, self).__init__()
        self._id = 'debian.sync_pkgs'
        self._taskman = taskman
        self._i18n = i18n
        self._log = logger
        self._root_password = root_password
        self._watcher = watcher
        self._aptitude = aptitude
        self._taskman.register_task(self._id, self._i18n['debian.task.sync_pkgs.status'], DEBIAN_ICON_PATH)

    def _notify_output(self, output: str):
        self._taskman.update_output(self._id, output)

    @staticmethod
    def should_synchronize(deb_config: dict, logger: Logger) -> bool:
        try:
            period = int(deb_config.get('sync_pkgs.time', 0))
        except ValueError:
            logger.error(f"Invalid value for Debian configuration property 'sync_pkgs.time': "
                         f"{deb_config['sync_pkgs.time']}")
            return True

        if period <= 0:
            logger.warning("Packages synchronization will always be done ('sync_pkgs.time' <= 0 )'")
            return True

        try:
            with open(PACKAGE_SYNC_TIMESTAMP_FILE) as f:
                timestamp_str = f.read().strip()
        except FileNotFoundError:
            logger.info(f"No packages synchronization timestamp found ({PACKAGE_SYNC_TIMESTAMP_FILE})")
            return True

        try:
            last_timestamp = datetime.fromtimestamp(float(timestamp_str))
        except:
            logger.error(f'Could not parse the packages synchronization timestamp: {timestamp_str} '
                         f'({PACKAGE_SYNC_TIMESTAMP_FILE})')
            traceback.print_exc()
            return True

        expired = last_timestamp + timedelta(minutes=period) <= datetime.utcnow()

        if expired:
            logger.info("Packages synchronization is outdated")
        else:
            logger.info("Packages synchronization is up-to-date")

        return expired

    def run(self) -> bool:
        ti = time.time()
        self._log.info("Begin: packages synchronization")
        self._taskman.update_progress(self._id, 1, None)
        
        handler = ProcessHandler(self._watcher)
        updated, _ = handler.handle_simple(self._aptitude.update(self._root_password),
                                           output_handler=self._notify_output)
        self._taskman.update_progress(self._id, 99, None)

        if updated:
            index_timestamp = datetime.utcnow().timestamp()
            finish_msg = None
            try:
                with open(PACKAGE_SYNC_TIMESTAMP_FILE, 'w+') as f:
                    f.write(str(index_timestamp))
            except OSError:
                finish_msg = self._i18n['error']
                self._log.error(f"Could not write the packages synchronization timestamp to file "
                                f"'{PACKAGE_SYNC_TIMESTAMP_FILE}'")
        else:
            finish_msg = self._i18n['error']

        self._taskman.update_progress(self._id, 100, finish_msg)
        self._taskman.finish_task(self._id)

        tf = time.time()
        self._log.info(f"Finish: packages synchronization ({tf - ti:.4f} seconds)")
        return updated
