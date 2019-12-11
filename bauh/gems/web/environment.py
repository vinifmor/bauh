import logging
import os
import shutil
import tarfile
from pathlib import Path

import requests
import yaml

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.http import HttpClient
from bauh.commons import system
from bauh.commons.html import bold
from bauh.commons.system import SimpleProcess, ProcessHandler, run_cmd
from bauh.gems.web import BIN_PATH, NODE_DIR_PATH, NODE_BIN_PATH, NPM_BIN_PATH, NODE_MODULES_PATH, NATIVEFIER_BIN_PATH, \
    ELECTRON_PATH, ELECTRON_DOWNLOAD_URL, ELECTRON_SHA256_URL, URL_ENVIRONMENT_SETTINGS
from bauh.view.util.translation import I18n


class EnvironmentUpdater:

    def __init__(self, logger: logging.Logger, http_client: HttpClient, file_downloader: FileDownloader, i18n: I18n):
        self.logger = logger
        self.file_downloader = file_downloader
        self.i18n = i18n
        self.http_client = http_client

    def _download_and_install(self, version: str, version_url: str, watcher: ProcessWatcher) -> bool:
        self.logger.info("Downloading NodeJS {}: {}".format(version, version_url))

        tarf_path = '{}/{}'.format(BIN_PATH, version_url.split('/')[-1])
        downloaded = self.file_downloader.download(version_url, watcher=watcher, output_path=tarf_path, cwd=BIN_PATH)

        if not downloaded:
            self.logger.error("Could not download '{}'. Aborting...".format(version_url))
            return False
        else:
            try:
                tf = tarfile.open(tarf_path)
                tf.extractall(path=BIN_PATH)

                extracted_file = '{}/{}'.format(BIN_PATH, tf.getnames()[0])

                os.rename(extracted_file, NODE_DIR_PATH)
                return True
            except:
                self.logger.error('Could not extract {}'.format(tarf_path))
                return False
            finally:
                if os.path.exists(tarf_path):
                    try:
                        os.remove(tarf_path)
                    except:
                        self.logger.error('Could not delete file {}'.format(tarf_path))

    def update_node(self, version: str, version_url: str, watcher: ProcessWatcher = None) -> bool:
        Path(BIN_PATH).mkdir(parents=True, exist_ok=True)

        if not os.path.exists(NODE_DIR_PATH):
            return self._download_and_install(version=version, version_url=version_url, watcher=watcher)
        else:
            installed_version = system.run_cmd('{} --version'.format(NODE_BIN_PATH), print_error=False)

            if installed_version:
                installed_version = installed_version.strip()

                if installed_version.startswith('v'):
                    installed_version = installed_version[1:]

                self.logger.info('Node versions: installed ({}), cloud ({})'.format(installed_version, version))

                if version != installed_version:
                    self.logger.info("The NodeJs installed version is different from the Cloud.")
                    return self._download_and_install(version=version, version_url=version_url, watcher=watcher)
                else:
                    self.logger.info("Node is already up to date")
                    return True
            else:
                self.logger.warning("Could not determine the current NodeJS installed version")
                self.logger.info("Removing {}".format(NODE_DIR_PATH))
                try:
                    shutil.rmtree(NODE_DIR_PATH)
                    return self._download_and_install(version=version, version_url=version_url, watcher=watcher)
                except:
                    self.logger.error('Could not delete the dir {}'.format(NODE_DIR_PATH))
                    return False

    def _install_nativefier(self, version: str, handler: ProcessHandler) -> bool:
        self.logger.info("Installing nativefier")

        if handler and handler.watcher:
            handler.watcher.change_substatus(self.i18n['web.environment.install'].format(bold('nativefier')))

        proc = SimpleProcess([NPM_BIN_PATH, 'install', 'nativefier@{}'.format(version)], cwd=BIN_PATH)

        if handler:
            return handler.handle_simple(proc)[0]
        else:
            proc.instance.wait()

            if self._is_nativefier_installed():
                self.logger.info("nativefier {} installed".format(version))
                return True
            else:
                self.logger.error("Could not install nativefier {}".format(version))
                return False

    def _is_nativefier_installed(self) -> bool:
        return os.path.exists(NATIVEFIER_BIN_PATH)

    def install_nativefier(self, version: str, remove_modules: bool = False, handler: ProcessHandler = None) -> bool:
        self.logger.info("Preparing to install nativefier {}".format(version))

        if remove_modules and os.path.exists(NODE_MODULES_PATH):
            self.logger.info('Removing old dir {}'.format(NODE_MODULES_PATH))
            try:
                shutil.rmtree(NODE_MODULES_PATH)
            except:
                self.logger.error('Could not remove dir {}. Aborting...'.format(NODE_MODULES_PATH))
                return False

            return self._install_nativefier(version=version, handler=handler)
        else:
            if not self._is_nativefier_installed():
                return self._install_nativefier(version=version, handler=handler)

            installed_version = run_cmd('{} --version'.format(NATIVEFIER_BIN_PATH), print_error=False)

            if installed_version:
                installed_version = installed_version.strip()

            self.logger.info("Nativefier versions: installed ({}), cloud ({})".format(installed_version, version))
            if version != installed_version:
                self.logger.info("Installed nativefier version is different from cloud's. Changing version.")
                return self._install_nativefier(version=version, handler=handler)

            self.logger.info("Nativefier is already installed and up to date")
            return True

    def _download_electron(self, version: str, is_x86_x64_arch: bool, watcher: ProcessWatcher) -> bool:
        self.logger.info("Downloading Electron {}".format(version))
        arch = 'ia32' if not is_x86_x64_arch else 'x64'

        electron_url = ELECTRON_DOWNLOAD_URL.format(arch=arch, version=version)
        electron_path = '{}/{}'.format(ELECTRON_PATH, electron_url.split('/')[-1])

        return self.file_downloader.download(file_url=electron_url, watcher=watcher, output_path=electron_path, cwd=ELECTRON_PATH)

    def _download_electron_sha256(self, version: str, watcher: ProcessWatcher) -> bool:
        self.logger.info("Downloading Electron {} sha526".format(version))

        sha256_url = ELECTRON_SHA256_URL.format(version=version)
        sha256_path = '{}/{}'.format(ELECTRON_PATH, sha256_url.split('/')[-1])
        return self.file_downloader.download(file_url=sha256_url, watcher=watcher, output_path=sha256_path, cwd=ELECTRON_PATH)

    def install_electron(self, version: str, is_x86_x64_arch: bool, watcher: ProcessWatcher) -> bool:
        self.logger.info("Checking installed Electron")

        if not os.path.exists(ELECTRON_PATH):
            self.logger.info("Electron is not installed")
            Path(ELECTRON_PATH).mkdir(parents=True, exist_ok=True)
            if self._download_electron(version=version, is_x86_x64_arch=is_x86_x64_arch, watcher=watcher):
                return self._download_electron_sha256(version=version, watcher=watcher)
        else:
            files = os.listdir(ELECTRON_PATH)

            if files:
                file_name = ELECTRON_DOWNLOAD_URL.format(version=version, arch='x64' if is_x86_x64_arch else 'ia32').split('/')[-1]
                electron_file = [f for f in files if f == file_name]

                if electron_file:
                    self.logger.info("Electron {} already downloaded".format(version))
                else:
                    if not self._download_electron(version=version, is_x86_x64_arch=is_x86_x64_arch, watcher=watcher):
                        return False

                file_name = ELECTRON_SHA256_URL.split('/')[-1]
                sha256_file = [f for f in files if f == file_name]

                if sha256_file:
                    self.logger.info("Electron {} sha256 already downloaded".format(version))
                    return True
                else:
                    return self._download_electron_sha256(version=version, watcher=watcher)

            self.logger.info('No Electron file found')
            if self._download_electron(version=version, is_x86_x64_arch=is_x86_x64_arch, watcher=watcher):
                return self._download_electron_sha256(version=version, watcher=watcher)

            return False

    def get_environment(self) -> dict:
        try:
            res = self.http_client.get(URL_ENVIRONMENT_SETTINGS)

            if not res:
                self.logger.warning('Could not retrieve the environments settings from the cloud')
                return

            try:
                return yaml.safe_load(res.content)
            except yaml.YAMLError:
                self.logger.error('Could not parse environment settings: {}'.format(res.text))
                return
        except requests.exceptions.ConnectionError:
            return

    def update_environment(self, is_x86_x64_arch: bool, handler: ProcessHandler = None) -> dict:

        settings = self.get_environment()

        if settings is None:
            return

        if not self.update_node(version=settings['nodejs']['version'], version_url=settings['nodejs']['url'],
                                watcher=handler.watcher if handler else None):
            self.logger.warning('Could not install / update NodeJS')
            return

        if not self.install_nativefier(version=settings['nativefier']['version'], handler=handler):
            self.logger.warning('Could not install / update nativefier')
            return

        res = self.install_electron(version=settings['electron']['version'], is_x86_x64_arch=is_x86_x64_arch,
                                    watcher=handler.watcher if handler else None)

        if res:
            self.logger.info('Environment updated')
        else:
            self.logger.warning('Could not update the environment')

        return settings
