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
from typing import Optional

from bauh.api.abstract.handler import TaskManager, ProcessWatcher
from bauh.api.http import HttpClient
from bauh.commons.boot import CreateConfigFile
from bauh.commons.html import bold
from bauh.gems.appimage import get_icon_path, INSTALLATION_PATH, SYMLINKS_DIR, util, DATABASES_TS_FILE, \
    DATABASES_DIR, DATABASE_APPS_FILE, DATABASE_RELEASES_FILE, URL_COMPRESSED_DATABASES
from bauh.gems.appimage.model import AppImage
from bauh.view.util.translation import I18n


class DatabaseUpdater(Thread):
    COMPRESS_FILE_PATH = '{}/db.tar.gz'.format(DATABASES_DIR)

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

        files = {*glob.glob('{}/*'.format(DATABASES_DIR))}

        if not files:
            self.logger.warning('No database files on {}'.format(DATABASES_DIR))
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

        Path(DATABASES_DIR).mkdir(parents=True, exist_ok=True)

        with open(self.COMPRESS_FILE_PATH, 'wb+') as f:
            f.write(res.content)

        self.logger.info("Database file saved at {}".format(self.COMPRESS_FILE_PATH))

        self._update_task_progress(50, self.i18n['appimage.update_database.deleting_old'])
        old_db_files = glob.glob(DATABASES_DIR + '/*.db')

        if old_db_files:
            self.logger.info('Deleting old database files')
            for f in old_db_files:
                os.remove(f)

            self.logger.info('Old database files deleted')

        self._update_task_progress(75, self.i18n['appimage.update_database.uncompressing'])
        self.logger.info('Uncompressing {}'.format(self.COMPRESS_FILE_PATH))

        try:
            tf = tarfile.open(self.COMPRESS_FILE_PATH)
            tf.extractall(DATABASES_DIR)
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
        if os.path.exists(INSTALLATION_PATH):
            installed_files = glob.glob('{}/*/*.json'.format(INSTALLATION_PATH))

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
