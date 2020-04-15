import glob
import logging
import os
import tarfile
import time
import traceback
from pathlib import Path
from threading import Thread

import requests

from bauh.api.abstract.handler import TaskManager
from bauh.api.http import HttpClient
from bauh.commons import internet
from bauh.gems.appimage import LOCAL_PATH, get_icon_path
from bauh.view.util.translation import I18n


class DatabaseUpdater(Thread):
    URL_DB = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/dbs.tar.gz'
    COMPRESS_FILE_PATH = LOCAL_PATH + '/db.tar.gz'

    def __init__(self, task_man: TaskManager, i18n: I18n, http_client: HttpClient, logger: logging.Logger, db_locks: dict, interval: int):
        super(DatabaseUpdater, self).__init__(daemon=True)
        self.http_client = http_client
        self.logger = logger
        self.db_locks = db_locks
        self.sleep = interval
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
            time.sleep(self.sleep)
