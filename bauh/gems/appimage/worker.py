import glob
import logging
import os
import tarfile
import time
import traceback
from pathlib import Path
from threading import Thread

import requests

from bauh.api.http import HttpClient
from bauh.commons import internet
from bauh.gems.appimage import LOCAL_PATH


class DatabaseUpdater(Thread):
    URL_DB = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/dbs.tar.gz'
    COMPRESS_FILE_PATH = LOCAL_PATH + '/db.tar.gz'

    def __init__(self, http_client: HttpClient, logger: logging.Logger, db_locks: dict, interval: int):
        super(DatabaseUpdater, self).__init__(daemon=True)
        self.http_client = http_client
        self.logger = logger
        self.db_locks = db_locks
        self.sleep = interval

    def download_databases(self):
        try:
            if not internet.is_available(self.http_client, self.logger):
                return
        except requests.exceptions.ConnectionError:
            self.logger.warning('The internet connection seems to be off.')
            return

        self.logger.info('Retrieving AppImage databases')

        res = self.http_client.get(self.URL_DB)

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

        else:
            self.logger.warning('Could not download the database file {}'.format(self.URL_DB))

    def run(self):
        while True:
            self.download_databases()
            self.logger.info('Sleeping')
            time.sleep(self.sleep)
