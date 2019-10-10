import logging
import os
import time
from multiprocessing import Process
from threading import Thread

from bauh.api.http import HttpClient


class DatabaseUpdater(Thread if bool(int(os.getenv('BAUH_DEBUG', 0))) else Process):

    URL_APPS = 'https://github.com/vinifmor/bauh-files/blob/master/appimage/apps.db?raw=true'
    URL_RELEASES = 'https://github.com/vinifmor/bauh-files/blob/master/appimage/releases.db?raw=true'
    APPS_PATH = '{}/.local/share/bauh/appimage/apps.db'
    RELEASES_PATH = '{}/.local/share/bauh/appimage/releases.db'

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
            self.logger.warning('Could not download a database file from {}'.format(url))

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
