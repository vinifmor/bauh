import glob
import json
import logging
import os
import tarfile
import time
import traceback
from pathlib import Path
from threading import Thread

import requests

from bauh.api.abstract.handler import TaskManager, ProcessWatcher
from bauh.api.http import HttpClient
from bauh.commons import internet
from bauh.gems.appimage import LOCAL_PATH, get_icon_path, INSTALLATION_PATH, SYMLINKS_DIR, util
from bauh.gems.appimage.model import AppImage
from bauh.view.util.translation import I18n


class DatabaseUpdater(Thread):
    URL_DB = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/dbs.tar.gz'
    COMPRESS_FILE_PATH = LOCAL_PATH + '/db.tar.gz'

    def __init__(self, task_man: TaskManager, i18n: I18n, http_client: HttpClient, logger: logging.Logger, db_locks: dict, interval: int):
        super(DatabaseUpdater, self).__init__(daemon=True)
        self.http_client = http_client
        self.logger = logger
        self.db_locks = db_locks
        self.sleep_time = interval
        self.i18n = i18n
        self.task_man = task_man
        self.task_id = 'appim_db'

    def _finish_task(self):
        if self.task_man:
            self.task_man.update_progress(self.task_id, 100, None)
            self.task_man.finish_task(self.task_id)
            self.task_man = None

    def download_databases(self):
        if self.task_man:
            self.task_man.register_task(self.task_id, self.i18n['appimage.task.db_update'], get_icon_path())
            self.task_man.update_progress(self.task_id, 10, None)

        try:
            if not internet.is_available():
                self._finish_task()
                return
        except requests.exceptions.ConnectionError:
            self.logger.warning('The internet connection seems to be off.')
            self._finish_task()
            return

        self.logger.info('Retrieving AppImage databases')

        try:
            res = self.http_client.get(self.URL_DB, session=False)
        except Exception as e:
            self.logger.error("An error ocurred while downloading the AppImage database: {}".format(e.__class__.__name__))
            res = None

        if res:
            Path(LOCAL_PATH).mkdir(parents=True, exist_ok=True)

            with open(self.COMPRESS_FILE_PATH, 'wb+') as f:
                f.write(res.content)

            self.logger.info("Database file saved at {}".format(self.COMPRESS_FILE_PATH))

            old_db_files = glob.glob(LOCAL_PATH + '/*.db')

            if old_db_files:
                self.logger.info('Deleting old database files')
                for f in old_db_files:
                    self.db_locks[f].acquire()
                    try:
                        os.remove(f)
                    finally:
                        self.db_locks[f].release()

                self.logger.info('Old database files deleted')

            self.logger.info('Uncompressing {}'.format(self.COMPRESS_FILE_PATH))

            try:
                tf = tarfile.open(self.COMPRESS_FILE_PATH)
                tf.extractall(LOCAL_PATH)
                self.logger.info('Successfully uncompressed file {}'.format(self.COMPRESS_FILE_PATH))
            except:
                self.logger.error('Could not extract file {}'.format(self.COMPRESS_FILE_PATH))
                traceback.print_exc()
            finally:
                self.logger.info('Deleting {}'.format(self.COMPRESS_FILE_PATH))
                os.remove(self.COMPRESS_FILE_PATH)
                self.logger.info('Successfully removed {}'.format(self.COMPRESS_FILE_PATH))
            self._finish_task()
        else:
            self.logger.warning('Could not download the database file {}'.format(self.URL_DB))
            self._finish_task()

    def run(self):
        while True:
            self.download_databases()
            self.logger.info('Sleeping')
            time.sleep(self.sleep_time)


class SymlinksVerifier(Thread):

    def __init__(self, taskman: TaskManager, i18n: I18n, logger: logging.Logger):
        super(SymlinksVerifier, self).__init__(daemon=True)
        self.taskman = taskman
        self.i18n = i18n
        self.logger = logger
        self.task_id = 'appim_symlink_check'

    @staticmethod
    def create_symlink(app: AppImage, file_path: str, logger: logging.Logger, watcher: ProcessWatcher = None):
        logger.info("Creating a symlink for '{}'".format(app.name))
        possible_names = (app.name.lower(), '{}-appimage'.format(app.name.lower()))

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
        self.taskman.register_task(self.task_id, self.i18n['appimage.task.symlink_check'], get_icon_path())

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
