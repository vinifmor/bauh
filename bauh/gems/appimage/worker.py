import logging
import os
import time
from multiprocessing import Process
from threading import Thread

from bauh.api.constants import HOME_PATH
from bauh.api.http import HttpClient


class DatabaseUpdater(Thread if bool(int(os.getenv('BAUH_DEBUG', 0))) else Process):

    URL_APPS = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/apps.db'
    URL_RELEASES = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/appimage/releases.db'
    APPS_PATH = '{}/.local/share/bauh/appimage/apps.db'.format(HOME_PATH)
    RELEASES_PATH = '{}/.local/share/bauh/appimage/releases.db'.format(HOME_PATH)

    def __init__(self, http_client: HttpClient, logger: logging.Logger):
        super(DatabaseUpdater, self).__init__(daemon=True)
        self.http_client = http_client
        self.logger = logger
        self.enabled = bool(int(os.getenv('BAUH_APPIMAGE_DB_UPDATER', 1)))
        self.sleep = 60 * 20

    def _download_file(self, url: str, output: str):
        res = self.http_client.get(url, headers={'Authorization': 'token {}'.format(os.getenv('GITHUB_TOKEN'))})

        if res:
            with open(output, 'wb+') as f:
                f.write(res.content)

            self.logger.info("Database file saved at {}".format(output))
        else:
            self.logger.warning('Could not download the database file {}'.format(url))

    def run(self):
        if self.enabled:
            while True:
                self.logger.info('Retrieving AppImage databases')

                threads = [Thread(target=self._download_file, args=(self.URL_APPS, self.APPS_PATH)),
                           Thread(target=self._download_file, args=(self.URL_RELEASES, self.RELEASES_PATH))]

                for t in threads:
                    t.start()

                for t in threads:
                    t.join()

                self.logger.info('Sleeping')
                time.sleep(self.sleep)
        else:
            self.logger.warning('Disabled')
