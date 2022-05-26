import glob
import json
import logging
import os
import tarfile
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Optional, Generator

import requests

from bauh.api.abstract.handler import TaskManager, ProcessWatcher
from bauh.api.http import HttpClient
from bauh.commons.boot import CreateConfigFile
from bauh.commons.html import bold
from bauh.gems.appimage import get_icon_path, INSTALLATION_DIR, SYMLINKS_DIR, util, DATABASES_TS_FILE, \
    APPIMAGE_CACHE_DIR, DATABASE_APPS_FILE, DATABASE_RELEASES_FILE, URL_COMPRESSED_DATABASES
from bauh.gems.appimage.model import AppImage
from bauh.view.util.translation import I18n


class DatabaseUpdater(Thread):
    COMPRESS_FILE_PATH = f'{APPIMAGE_CACHE_DIR}/db.tar.gz'

    def __init__(self, i18n: I18n, http_client: HttpClient, logger: logging.Logger, taskman: TaskManager,
                 watcher: Optional[ProcessWatcher] = None, appimage_config: Optional[dict] = None, create_config: Optional[CreateConfigFile] = None):
        super(DatabaseUpdater, self).__init__(daemon=True)
        self.http_client = http_client
        self.logger = logger
        self.i18n = i18n
        self.taskman = taskman
        self.watcher = watcher
        self.task_id = 'appim_db'
        self.config = appimage_config
        self.create_config = create_config
        self.taskman.register_task(self.task_id, self.i18n['appimage.task.db_update'], get_icon_path())

    def should_update(self, appimage_config: dict) -> bool:
        ti = time.time()

        try:
            db_exp = int(appimage_config['database']['expiration'])
        except ValueError:
            self.logger.error("Could not parse settings property 'database.expiration': {}".format(appimage_config['database']['expiration']))
            return True

        if db_exp <= 0:
            self.logger.info("No expiration time configured for the AppImage database")
            return True

        files = {*glob.glob(f'{APPIMAGE_CACHE_DIR}/*')}

        if not files:
            self.logger.warning(f'No database files on {APPIMAGE_CACHE_DIR}')
            return True

        if DATABASES_TS_FILE not in files:
            self.logger.warning("No database timestamp file found ({})".format(DATABASES_TS_FILE))
            return True

        if DATABASE_APPS_FILE not in files:
            self.logger.warning("Database file '{}' not found".format(DATABASE_APPS_FILE))
            return True

        if DATABASE_RELEASES_FILE not in files:
            self.logger.warning("Database file '{}' not found".format(DATABASE_RELEASES_FILE))
            return True

        with open(DATABASES_TS_FILE) as f:
            dbs_ts_str = f.read()

        try:
            dbs_timestamp = datetime.fromtimestamp(float(dbs_ts_str))
        except:
            self.logger.error('Could not parse the databases timestamp: {}'.format(dbs_ts_str))
            traceback.print_exc()
            return True

        update = dbs_timestamp + timedelta(minutes=db_exp) <= datetime.utcnow()
        self.logger.info('Finished. Took {0:.2f} seconds'.format(time.time() - ti))
        return update

    def _update_task_progress(self, progress: float, substatus: Optional[str] = None):
        self.taskman.update_progress(self.task_id, progress, substatus)

        if self.watcher:
            self.watcher.change_substatus(substatus)

    def download_databases(self) -> bool:
        self._update_task_progress(10, self.i18n['appimage.update_database.downloading'])
        self.logger.info('Retrieving AppImage databases')

        database_timestamp = datetime.utcnow().timestamp()
        try:
            res = self.http_client.get(URL_COMPRESSED_DATABASES, session=False)
        except Exception as e:
            self.logger.error("An error ocurred while downloading the AppImage database: {}".format(e.__class__.__name__))
            res = None

        if not res:
            self.logger.warning('Could not download the database file {}'.format(URL_COMPRESSED_DATABASES))
            return False

        Path(APPIMAGE_CACHE_DIR).mkdir(parents=True, exist_ok=True)

        with open(self.COMPRESS_FILE_PATH, 'wb+') as f:
            f.write(res.content)

        self.logger.info("Database file saved at {}".format(self.COMPRESS_FILE_PATH))

        self._update_task_progress(50, self.i18n['appimage.update_database.deleting_old'])
        old_db_files = glob.glob(f'{APPIMAGE_CACHE_DIR}/*.db')

        if old_db_files:
            self.logger.info('Deleting old database files')
            for f in old_db_files:
                os.remove(f)

            self.logger.info('Old database files deleted')

        self._update_task_progress(75, self.i18n['appimage.update_database.uncompressing'])
        self.logger.info('Uncompressing {}'.format(self.COMPRESS_FILE_PATH))

        try:
            tf = tarfile.open(self.COMPRESS_FILE_PATH)
            tf.extractall(APPIMAGE_CACHE_DIR)
            self.logger.info('Successfully uncompressed file {}'.format(self.COMPRESS_FILE_PATH))
        except:
            self.logger.error('Could not extract file {}'.format(self.COMPRESS_FILE_PATH))
            traceback.print_exc()
            return False
        finally:
            self.logger.info('Deleting {}'.format(self.COMPRESS_FILE_PATH))
            os.remove(self.COMPRESS_FILE_PATH)
            self.logger.info('File {} deleted'.format(self.COMPRESS_FILE_PATH))

        self._update_task_progress(95)
        self.logger.info("Saving database timestamp {}".format(database_timestamp))

        with open(DATABASES_TS_FILE, 'w+') as f:
            f.write(str(database_timestamp))

        self.logger.info("Database timestamp saved")

        return True

    def run(self):
        ti = time.time()

        if self.create_config:
            self.taskman.update_progress(self.task_id, 0, self.i18n['task.waiting_task'].format(bold(self.create_config.task_name)))
            self.create_config.join()
            self.config = self.create_config.config

        self.taskman.update_progress(self.task_id, 1, self.i18n['appimage.task.db_update.checking'])

        if self.should_update(self.config):
            self.download_databases()

        self.taskman.update_progress(self.task_id, 100, None)
        self.taskman.finish_task(self.task_id)
        tf = time.time()
        self.logger.info("Finished. Took {0:.2f} seconds".format(tf - ti))


class SymlinksVerifier(Thread):

    def __init__(self, taskman: TaskManager, i18n: I18n, logger: logging.Logger):
        super(SymlinksVerifier, self).__init__(daemon=True)
        self.taskman = taskman
        self.i18n = i18n
        self.logger = logger
        self.task_id = 'appim_symlink_check'
        self.taskman.register_task(self.task_id, self.i18n['appimage.task.symlink_check'], get_icon_path())

    @staticmethod
    def create_symlink(app: AppImage, file_path: str, logger: logging.Logger, watcher: ProcessWatcher = None):
        logger.info("Creating a symlink for '{}'".format(app.name))
        possible_names = (app.get_clean_name(), '{}-appimage'.format(app.get_clean_name()), app.name.lower(), '{}-appimage'.format(app.name.lower()))

        if os.path.exists(SYMLINKS_DIR) and not os.path.isdir(SYMLINKS_DIR):
            logger.warning("'{}' is not a directory. It will not be possible to create a symlink for '{}'".format(SYMLINKS_DIR, app.name))
            return

        available_system_dirs = (SYMLINKS_DIR, *(l for l in ('/usr/bin', '/usr/local/bin') if os.path.isdir(l)))

        # checking if the link already exists:

        available_name = None
        for name in possible_names:
            available_name = name
            for sysdir in available_system_dirs:
                if os.path.exists('{}/{}'.format(sysdir, name)):
                    available_name = None
                    break

            if available_name:
                break

        if not available_name:
            msg = "It was not possible to create a symlink for '{}' because the names {} are already available on the system".format(app.name,
                                                                                                                                     possible_names)
            logger.warning(msg)
            if watcher:
                watcher.print('[warning] {}'.format(msg))
        else:
            try:
                Path(SYMLINKS_DIR).mkdir(parents=True, exist_ok=True)
            except:
                logger.error("Could not create symlink directory '{}'".format(SYMLINKS_DIR))
                return

            symlink_path = '{}/{}'.format(SYMLINKS_DIR, available_name)

            try:
                os.symlink(src=file_path, dst=symlink_path)
                app.symlink = symlink_path

                msg = "symlink successfully created at {}".format(symlink_path)
                logger.info(msg)

                if watcher:
                    watcher.print(msg)
            except:
                msg = "Could not create the symlink '{}'".format(symlink_path)
                logger.error(msg)

                if watcher:
                    watcher.print('[error] {}'.format(msg))

    def run(self):
        if os.path.exists(INSTALLATION_DIR):
            installed_files = glob.glob(f'{INSTALLATION_DIR}/*/*.json')

            if installed_files:
                self.logger.info("Checking installed AppImage files with no symlinks created")

                progress_per_file = (1/len(installed_files)) * 100
                total_progress = 0
                for json_file in installed_files:
                    with open(json_file) as f:
                        try:
                            data = json.loads(f.read())
                        except:
                            self.logger.warning("Could not parse data from '{}'".format(json_file))
                            data = None

                    if data and not data.get('symlink'):
                        if not data.get('install_dir'):
                            data['install_dir'] = '/'.join(json_file.split('/')[0:-1])

                        app = AppImage(**data, i18n=self.i18n)

                        file_path = util.find_appimage_file(app.install_dir)

                        if file_path:
                            self.create_symlink(app, file_path, self.logger)
                            data['symlink'] = app.symlink

                            # caching
                            try:
                                with open(json_file, 'w+') as f:
                                    f.write(json.dumps(data))
                            except:
                                self.logger.warning("Could not update cached data on '{}'".format(json_file))
                                traceback.print_exc()

                        else:
                            self.logger.warning("No AppImage file found on installation dir '{}'".format(file_path))

                    total_progress += progress_per_file
                    self.taskman.update_progress(self.task_id, total_progress, '')

                self.taskman.update_progress(self.task_id, 100, '')
                self.taskman.finish_task(self.task_id)
                return

        self.logger.info("No AppImage applications found. Aborting")
        self.taskman.update_progress(self.task_id, 100, '')
        self.taskman.finish_task(self.task_id)


class AppImageSuggestionsDownloader(Thread):

    def __init__(self, logger: logging.Logger, http_client: HttpClient, i18n: I18n, file_url: Optional[str],
                 create_config: Optional[CreateConfigFile] = None, appimage_config: Optional[dict] = None,
                 taskman: Optional[TaskManager] = None):
        super(AppImageSuggestionsDownloader, self).__init__(daemon=True)
        self.create_config = create_config
        self.logger = logger
        self.i18n = i18n
        self.http_client = http_client
        self.taskman = taskman
        self.config = appimage_config
        self.task_id = 'appim.suggestions'
        self._cached_file_path: Optional[str] = None
        self._cached_ts_file_path: Optional[str] = None

        if file_url:
            self._file_url = file_url
        else:
            self._file_url = f'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/suggestions.txt'

    @property
    def cached_file_path(self) -> str:
        if not self._cached_file_path:
            self._cached_file_path = f'{APPIMAGE_CACHE_DIR}/suggestions.txt'

        return self._cached_file_path

    @property
    def cached_ts_file_path(self) -> str:
        if not self._cached_ts_file_path:
            self._cached_ts_file_path = f'{APPIMAGE_CACHE_DIR}/suggestions.ts'

        return self._cached_ts_file_path

    def register_task(self):
        self.taskman.register_task(id_=self.task_id,
                                   label=self.i18n['task.download_suggestions'], icon_path=get_icon_path())

    def is_custom_local_file_mapped(self) -> bool:
        return self._file_url and self._file_url.startswith('/')

    def should_download(self, appimage_config: dict) -> bool:
        if not self._file_url:
            self.logger.error("No AppImage suggestions file URL defined")
            return False

        if self.is_custom_local_file_mapped():
            return False

        try:
            exp_hours = int(appimage_config['suggestions']['expiration'])
        except:
            self.logger.error("An exception happened while trying to parse the AppImage 'suggestions.expiration'")
            traceback.print_exc()
            return True

        if exp_hours <= 0:
            self.logger.info("The AppImage suggestions cache is disabled")
            return True

        if not os.path.exists(self.cached_file_path):
            self.logger.info(f"File {self.cached_file_path} not found. It must be downloaded")
            return True

        if not os.path.exists(self.cached_ts_file_path):
            self.logger.info(f"File {self.cached_ts_file_path}  not found. The suggestions file must be downloaded.")
            return True

        with open(self.cached_ts_file_path) as f:
            timestamp_str = f.read()

        try:
            suggestions_timestamp = datetime.fromtimestamp(float(timestamp_str))
        except:
            self.logger.error(f'Could not parse the cached AppImage suggestions timestamp: {timestamp_str}')
            traceback.print_exc()
            return True

        update = suggestions_timestamp + timedelta(hours=exp_hours) <= datetime.utcnow()
        return update

    def read(self) -> Generator[str, None, None]:
        if not self._file_url:
            self.logger.error("No AppImage suggestions file URL defined")
            yield from ()

        self.logger.info("Checking if AppImage suggestions should be downloaded")
        if self.should_download(self.config):
            suggestions_timestamp = datetime.utcnow().timestamp()
            suggestions_str = self.download()

            Thread(target=self.cache_suggestions, args=(suggestions_str, suggestions_timestamp), daemon=True).start()
        else:
            if self.is_custom_local_file_mapped():
                file_path, log_ref = self._file_url, 'local'
            else:
                file_path, log_ref = self.cached_file_path, 'cached'

            self.logger.info(f"Reading {log_ref} AppImage suggestions from {file_path}")
            with open(file_path) as f:
                suggestions_str = f.read()

        yield from self.map_suggestions(suggestions_str) if suggestions_str else ()

    def cache_suggestions(self, text: str, timestamp: float):
        self.logger.info(f"Caching AppImage suggestions to {self.cached_file_path}")

        cache_dir = os.path.dirname(self.cached_file_path)

        try:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            cache_dir_ok = True
        except OSError:
            self.logger.error(f"Could not create the caching directory {cache_dir}")
            traceback.print_exc()
            cache_dir_ok = False

        if cache_dir_ok:
            try:
                with open(self.cached_file_path, 'w+') as f:
                    f.write(text)
            except:
                self.logger.error(f"An exception happened while writing AppImage suggestions to {self.cached_file_path}")
                traceback.print_exc()

            try:
                with open(self.cached_ts_file_path, 'w+') as f:
                    f.write(str(timestamp))
            except:
                self.logger.error(f"An exception happened while writing the cached AppImage suggestions timestamp "
                                  f"to {self.cached_ts_file_path}")
                traceback.print_exc()

    def download(self) -> Optional[str]:
        if not self._file_url:
            self.logger.error("No AppImage suggestions file URL defined")
            return

        if self.is_custom_local_file_mapped():
            self.logger.warning("Local AppImage suggestions file mapped. Nothing will be downloaded")
            return

        self.logger.info(f"Downloading AppImage suggestions from {self._file_url}")

        try:
            res = self.http_client.get(self._file_url)
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"Could not download suggestion from {self._file_url}")
            return

        if not res:
            self.logger.warning(f"Could not download suggestion from {self._file_url}")
            return

        if not res.text:
            self.logger.warning(f"No AppImage suggestion found in {self._file_url}")
            return

        return res.text

    def map_suggestions(self, text: str) -> Generator[str, None, None]:
        return (line for line in text.split('\n') if line)

    def run(self):
        ti = time.time()

        if not self.is_custom_local_file_mapped():
            if  self.create_config:
                wait_msg = self.i18n['task.waiting_task'].format(bold(self.create_config.task_name))
                self.taskman.update_progress(self.task_id, 0, wait_msg)
                self.create_config.join()
                self.config = self.create_config.config

            ti = time.time()
            self.taskman.update_progress(self.task_id, 1, None)

            self.logger.info("Checking if AppImage suggestions should be downloaded")
            should_download = self.should_download(self.config)
            self.taskman.update_progress(self.task_id, 30, None)

            try:
                if should_download:
                    suggestions_timestamp = datetime.utcnow().timestamp()
                    suggestions_str = self.download()
                    self.taskman.update_progress(self.task_id, 70, None)

                    if suggestions_str:
                        self.cache_suggestions(suggestions_str, suggestions_timestamp)
                else:
                    self.logger.info("Cached AppImage suggestions are up-to-date")
            except:
                self.logger.error("An unexpected exception happened while downloading AppImage suggestions")
                traceback.print_exc()

        self.taskman.update_progress(self.task_id, 100, None)
        self.taskman.finish_task(self.task_id)
        tf = time.time()
        self.logger.info(f"Took {tf - ti:.9f} seconds to download suggestions")
