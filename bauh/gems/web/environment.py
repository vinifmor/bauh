import logging
import os
import shutil
import tarfile
import traceback
from pathlib import Path

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.exception import NoInternetException
from bauh.commons import system
from bauh.commons.system import SimpleProcess, ProcessHandler, run_cmd
from bauh.gems.web import BIN_PATH, NODE_DIR_PATH, NODE_BIN_PATH, NPM_BIN_PATH, NODE_MODULES_PATH, NATIVEFIER_BIN_PATH, \
    ELECTRON_PATH, ELECTRON_DOWNLOAD_URL, ELECTRON_SHA256_URL, ELECTRON_VERSION
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

    def _install_nativefier(self, handler: ProcessHandler) -> bool:
        self.logger.info("Installing nativefier")
        # TODO freeze specific version
        proc = SimpleProcess([NPM_BIN_PATH, 'install', 'nativefier'], cwd=BIN_PATH)

        if handler:
            return handler.handle_simple(proc)[0]
        else:
            proc.instance.wait()

            if self._is_nativefier_installed():
                self.logger.info("nativefier installed")
                return True
            else:
                self.logger.error("Could not install nativefier")
                return False

    def _is_nativefier_installed(self) -> bool:
        try:
            return bool(system.run_cmd('{} --version'.format(NATIVEFIER_BIN_PATH)))
        except:
            self.logger.error("Could not determine the installed nativefier version")
            traceback.print_exc()
            return False

    def install_nativefier(self, remove_modules: bool = False, handler: ProcessHandler = None) -> bool:
        self.logger.info("Preparing to install nativefier")

        if remove_modules and os.path.exists(NODE_MODULES_PATH):
            self.logger.info('Removing old dir {}'.format(NODE_MODULES_PATH))
            try:
                shutil.rmtree(NODE_MODULES_PATH)
            except:
                self.logger.error('Could not remove dir {}. Aborting...'.format(NODE_MODULES_PATH))
                return False

            return self._install_nativefier(handler)
        else:
            if not self._is_nativefier_installed():
                return self._install_nativefier(handler)

            self.logger.info("Nativefier is already installed")
            return True

    def _download_electron(self, version: str, is_x86_x64_arch: bool, watcher: ProcessWatcher) -> bool:
        self.logger.info("Downloading Electron {}".format(version))
        arch = 'ia32' if not is_x86_x64_arch else 'x64'

        Path(ELECTRON_PATH).mkdir(parents=True, exist_ok=True)

        electron_url = ELECTRON_DOWNLOAD_URL.format(arch=arch, version=version)
        electron_path = '{}/{}'.format(ELECTRON_PATH, electron_url.split('/')[-1])

        return self.file_downloader.download(file_url=electron_url, watcher=watcher, output_path=electron_path,cwd=ELECTRON_PATH)

    def _download_electron_sha256(self, version: str, watcher: ProcessWatcher) -> bool:
        self.logger.info("Downloading Electron {} sha526".format(version))

        Path(ELECTRON_PATH).mkdir(parents=True, exist_ok=True)

        sha256_url = ELECTRON_SHA256_URL.format(version=version)
        sha256_path = '{}/{}'.format(ELECTRON_PATH, sha256_url.split('/')[-1])
        return self.file_downloader.download(file_url=sha256_url, watcher=watcher, output_path=sha256_path, cwd=ELECTRON_PATH)

    def install_electron(self, version: str, is_x86_x64_arch: bool, watcher: ProcessWatcher) -> bool:
        self.logger.info("Checking installed Electron")

        if not os.path.exists(ELECTRON_PATH):
            self.logger.info("Electron is not installed")
            self._download_electron(version=version, is_x86_x64_arch=is_x86_x64_arch, watcher=watcher)
        else:
            files = run_cmd('ls', print_error=False, cwd=ELECTRON_PATH)

            if files:
                file_list = files.split('\n')
                file_name = ELECTRON_DOWNLOAD_URL.format(version=version, arch='x64' if is_x86_x64_arch else 'ia32').split('/')[-1]
                electron_file = [f for f in file_list if f == file_name]

                if electron_file:
                    self.logger.info("Electron {} already downloaded".format(version))
                else:
                    if not self._download_electron(version=version, is_x86_x64_arch=is_x86_x64_arch, watcher=watcher):
                        return False

                file_name = ELECTRON_SHA256_URL.split('/')[-1]
                sha256_file = [f for f in file_list if f == file_name]

                if sha256_file:
                    self.logger.info("Electron {} sha256 already downloaded".format(version))
                    return True
                else:
                    return self._download_electron_sha256(version=version, watcher=watcher)

            self.logger.info('No Electron file found')
            if self._download_electron(version=version, is_x86_x64_arch=is_x86_x64_arch, watcher=watcher):
                return self._download_electron_sha256(version=version, watcher=watcher)

            return False

    def update_environment(self, is_x86_x64_arch: bool, handler: ProcessHandler = None):
        if not self.update_node(handler.watcher if handler else None):
            self.logger.warning('Could not update the environment')
            return False

        if not self.install_nativefier(handler=handler):
            self.logger.warning('Could not update the environment')
            return False

        res = self.install_electron(version=ELECTRON_VERSION, is_x86_x64_arch=is_x86_x64_arch, watcher=handler.watcher if handler else None)

        if res:
            self.logger.info('Environment updated')
        else:
            self.logger.warning('Could not update the environment')

        return res
