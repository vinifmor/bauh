import logging
import os
import shutil
import tarfile
from pathlib import Path

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.exception import NoInternetException
from bauh.commons import system
from bauh.gems.web import BIN_PATH, NODE_DIR_PATH, NODE_BIN_PATH
from bauh.view.util.translation import I18n


class NodeUpdater:

    def __init__(self, logger: logging.Logger, file_downloader: FileDownloader, i18n: I18n):
        self.logger = logger
        self.file_downloader = file_downloader
        self.i18n = i18n

    def _is_internet_available(self) -> bool:
        self.logger.info('Checking internet connection')
        # TODO
        return True

    def _download_and_install(self, cloud_version: str, watcher: ProcessWatcher ) -> bool:
        npm_dlink = 'https://nodejs.org/dist/v12.13.1/node-v12.13.1-linux-x64.tar.xz'
        self.logger.info("Downloading NodeJS {}: {}".format(cloud_version, npm_dlink))

        tarf_path = '{}/{}'.format(BIN_PATH, npm_dlink.split('/')[-1])
        downloaded = self.file_downloader.download(npm_dlink, watcher=watcher, output_path=tarf_path, cwd=BIN_PATH)

        if not downloaded:
            self.logger.error("Could not download '{}'. Aborting...".format(npm_dlink))
            return False
        else:
            try:
                tf = tarfile.open(tarf_path)
                tf.extractall(path=BIN_PATH)

                extracted_file = '{}/{}'.format(BIN_PATH, tf.getnames()[0])

                os.rename(extracted_file, NODE_DIR_PATH)

            except:
                self.logger.error('Could not extract {}'.format(tarf_path))
                return False
            finally:
                if os.path.exists(tarf_path):
                    try:
                        os.remove(tarf_path)
                    except:
                        self.logger.error('Could not delete file {}'.format(tarf_path))

    def update_node(self, watcher: ProcessWatcher = None) -> bool:
        if not self._is_internet_available():
            raise NoInternetException()

        self.logger.info('Checking Node version from bauh-files')
        # TODO
        cloud_version = 'v12.13.1'

        Path(BIN_PATH).mkdir(parents=True, exist_ok=True)

        if not os.path.exists(NODE_DIR_PATH):
            if not self._download_and_install(cloud_version, watcher):
                return False
        else:
            installed_version = system.run_cmd('{} --version'.format(NODE_BIN_PATH))

            if installed_version:
                installed_version = installed_version.strip()

                self.logger.info('Node -> installed: {}. cloud: {}.'.format(installed_version, cloud_version))

                if cloud_version != installed_version:
                    return self._download_and_install(cloud_version, watcher)
                else:
                    self.logger.info("Node is already up to date")
                    return True
            else:
                self.logger.warning("Could not determine the current NodeJS installed version")
                self.logger.info("Removing {}".format(NODE_DIR_PATH))
                try:
                    shutil.rmtree(NODE_DIR_PATH)
                    return self._download_and_install(cloud_version, watcher)
                except:
                    self.logger.error('Could not delete the dir {}'.format(NODE_DIR_PATH))
                    return False
