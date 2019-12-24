import logging
import os
import shutil
import tarfile
from pathlib import Path
from threading import Thread
from typing import Dict, List

import requests
import yaml

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MessageType
from bauh.api.http import HttpClient
from bauh.commons import system
from bauh.commons.html import bold
from bauh.commons.system import SimpleProcess, ProcessHandler
from bauh.gems.web import ENV_PATH, NODE_DIR_PATH, NODE_BIN_PATH, NODE_MODULES_PATH, NATIVEFIER_BIN_PATH, \
    ELECTRON_PATH, ELECTRON_DOWNLOAD_URL, ELECTRON_SHA256_URL, URL_ENVIRONMENT_SETTINGS, NPM_BIN_PATH, NODE_PATHS, \
    nativefier, URL_NATIVEFIER
from bauh.gems.web.model import WebApplication
from bauh.view.util.translation import I18n


class EnvironmentComponent:

    def __init__(self, id: str, name: str, size: str, version: str, url: str, update: bool = False):
        self.id = id
        self.name = name
        self.size = size
        self.version = version
        self.url = url
        self.update = update


class EnvironmentUpdater:

    def __init__(self, logger: logging.Logger, http_client: HttpClient, file_downloader: FileDownloader, i18n: I18n):
        self.logger = logger
        self.file_downloader = file_downloader
        self.i18n = i18n
        self.http_client = http_client

    def _download_and_install(self, version: str, version_url: str, watcher: ProcessWatcher) -> bool:
        self.logger.info("Downloading NodeJS {}: {}".format(version, version_url))

        tarf_path = '{}/{}'.format(ENV_PATH, version_url.split('/')[-1])
        downloaded = self.file_downloader.download(version_url, watcher=watcher, output_path=tarf_path, cwd=ENV_PATH)

        if not downloaded:
            self.logger.error("Could not download '{}'. Aborting...".format(version_url))
            return False
        else:
            try:
                tf = tarfile.open(tarf_path)
                tf.extractall(path=ENV_PATH)

                extracted_file = '{}/{}'.format(ENV_PATH, tf.getnames()[0])

                os.rename(extracted_file, NODE_DIR_PATH)

                if os.path.exists(NODE_MODULES_PATH):
                    self.logger.info('Deleting {}'.format(NODE_MODULES_PATH))
                    try:
                        shutil.rmtree(NODE_MODULES_PATH)
                    except:
                        self.logger.error("Could not delete the directory {}".format(NODE_MODULES_PATH))
                        return False

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

    def check_node_installed(self, version: str) -> bool:
        if not os.path.exists(NODE_DIR_PATH):
            return False
        else:
            installed_version = system.run_cmd('{} --version'.format(NODE_BIN_PATH), print_error=False)

            if installed_version:
                installed_version = installed_version.strip()

                if installed_version.startswith('v'):
                    installed_version = installed_version[1:]

                self.logger.info('Node versions: installed ({}), cloud ({})'.format(installed_version, version))

                if version != installed_version:
                    self.logger.info("The NodeJs installed version is different from the Cloud.")
                    return False
                else:
                    self.logger.info("Node is already up to date")
                    return True
            else:
                self.logger.warning("Could not determine the current NodeJS installed version")
                return False

    def update_node(self, version: str, version_url: str, watcher: ProcessWatcher = None) -> bool:
        Path(ENV_PATH).mkdir(parents=True, exist_ok=True)

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

    def _install_node_lib(self, name: str, version: str, handler: ProcessHandler):
        lib_repr = '{}{}'.format(name, '@{}'.format(version) if version else '')
        self.logger.info("Installing {}".format(lib_repr))

        if handler and handler.watcher:
            handler.watcher.change_substatus(self.i18n['web.environment.install'].format(bold(lib_repr)))

        proc = SimpleProcess([NPM_BIN_PATH, 'install', lib_repr], cwd=ENV_PATH, extra_paths=NODE_PATHS)

        installed = handler.handle_simple(proc)[0]

        if installed:
            self.logger.info("{} successfully installed".format(lib_repr))

        return installed

    def _install_nativefier(self, version: str, handler: ProcessHandler) -> bool:
        self.logger.info("Checking if nativefier@{} exists".format(version))

        url = URL_NATIVEFIER.format(version=version)
        if not self.http_client.exists(url):
            self.logger.warning("The file {} seems not to exist".format(url))
            handler.watcher.show_message(title=self.i18n['message.file.not_exist'],
                                         body=self.i18n['message.file.not_exist.body'].format(bold(url)),
                                         type_=MessageType.ERROR)
            return False

        success = self._install_node_lib('nativefier', version, handler)

        if success:
            return self._is_nativefier_installed()

    def _is_nativefier_installed(self) -> bool:
        return os.path.exists(NATIVEFIER_BIN_PATH)

    def download_electron(self, version: str, url: str, watcher: ProcessWatcher) -> bool:
        Path(ELECTRON_PATH).mkdir(parents=True, exist_ok=True)
        self.logger.info("Downloading Electron {}".format(version))
        electron_path = '{}/{}'.format(ELECTRON_PATH, url.split('/')[-1])

        if not self.http_client.exists(url):
            self.logger.warning("The file {} seems not to exist".format(url))
            watcher.show_message(title=self.i18n['message.file.not_exist'],
                                 body=self.i18n['message.file.not_exist.body'].format(bold(url)),
                                 type_=MessageType.ERROR)
            return False

        return self.file_downloader.download(file_url=url, watcher=watcher, output_path=electron_path, cwd=ELECTRON_PATH)

    def download_electron_sha256(self, version: str, url: str, watcher: ProcessWatcher) -> bool:
        self.logger.info("Downloading Electron {} sha526".format(version))
        sha256_path = '{}/{}'.format(ELECTRON_PATH, url.split('/')[-1]) + '-{}'.format(version)

        if not self.http_client.exists(url):
            self.logger.warning("The file {} seems not to exist".format(url))
            watcher.show_message(title=self.i18n['message.file.not_exist'],
                                 body=self.i18n['message.file.not_exist.body'].format(bold(url)),
                                 type_=MessageType.ERROR)
            return False

        return self.file_downloader.download(file_url=url, watcher=watcher, output_path=sha256_path, cwd=ELECTRON_PATH)

    def _get_electron_url(self, version: str, is_x86_x64_arch: bool) -> str:
        return ELECTRON_DOWNLOAD_URL.format(version=version, arch='x64' if is_x86_x64_arch else 'ia32')

    def check_electron_installed(self, version: str, is_x86_x64_arch: bool) -> Dict[str, bool]:
        self.logger.info("Checking if Electron {} is installed".format(version))
        res = {'electron': False, 'sha256': False}

        if not os.path.exists(ELECTRON_PATH):
            self.logger.info("The Electron folder {} was not found".format(ELECTRON_PATH))
        else:
            files = os.listdir(ELECTRON_PATH)

            if files:
                file_name = self._get_electron_url(version, is_x86_x64_arch).split('/')[-1]
                res['electron'] = bool([f for f in files if f == file_name])

                if not res['electron']:
                    res['sha256'] = True
                else:
                    file_name = ELECTRON_SHA256_URL.split('/')[-1] + '-{}'.format(version)
                    res['sha256'] = bool([f for f in files if f == file_name])
            else:
                self.logger.info('No Electron file found in {}'.format(ELECTRON_PATH))

            for att in ('electron', 'sha256'):
                if res[att]:
                    self.logger.info('{} ({}) already downloaded'.format(att, version))

        return res

    def read_settings(self) -> dict:
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

    def _check_and_fill_electron(self, pkg: WebApplication, env: dict, local_config: dict, x86_x64: bool, output: List[EnvironmentComponent]):
        electron_version = env['electron']['version']

        if pkg.version and pkg.version != electron_version:
            self.logger.info('A preset Electron version is defined for {}: {}'.format(pkg.url, pkg.version))
            electron_version = pkg.version

        if local_config['environment']['electron']['version']:
            self.logger.warning("A custom Electron version will be used {} to install {}".format(electron_version, pkg.url))
            electron_version = local_config['environment']['electron']['version']

        electron_status = self.check_electron_installed(version=electron_version, is_x86_x64_arch=x86_x64)

        electron_url = self._get_electron_url(version=electron_version, is_x86_x64_arch=x86_x64)
        output.append(EnvironmentComponent(name=electron_url.split('/')[-1],
                                           version=electron_version,
                                           url=electron_url,
                                           size=self.http_client.get_content_length(electron_url),
                                           id='electron',
                                           update=not electron_status['electron']))

        sha_url = ELECTRON_SHA256_URL.format(version=electron_version)
        output.append(EnvironmentComponent(name=sha_url.split('/')[-1],
                                           version=electron_version,
                                           url=sha_url,
                                           size=self.http_client.get_content_length(sha_url),
                                           id='electron_sha256',
                                           update=not electron_status['electron'] or not electron_status['sha256']))

    def _check_and_fill_node(self, env: dict, output: List[EnvironmentComponent]):
        node = EnvironmentComponent(name=env['nodejs']['url'].split('/')[-1],
                                    url=env['nodejs']['url'],
                                    size=self.http_client.get_content_length(env['nodejs']['url']),
                                    version=env['nodejs']['version'],
                                    id='nodejs')
        output.append(node)

        native = self._map_nativefier_file(env['nativefier'])
        output.append(native)

        if not self.check_node_installed(env['nodejs']['version']):
            node.update, native.update = True, True
        else:
            if not self._check_nativefier_installed(env['nativefier']):
                native.update = True

    def _check_nativefier_installed(self, nativefier_settings: dict) -> bool:
        if not os.path.exists(NODE_MODULES_PATH):
            self.logger.info('Node modules path {} not found'.format(NODE_MODULES_PATH))
            return False
        else:
            if not self._is_nativefier_installed():
                return False

            installed_version = nativefier.get_version()

            if installed_version:
                installed_version = installed_version.strip()

            self.logger.info("Nativefier versions: installed ({}), cloud ({})".format(installed_version, nativefier_settings['version']))

            if nativefier_settings['version'] != installed_version:
                self.logger.info("Installed nativefier version is different from cloud's. Changing version.")
                return False

            self.logger.info("Nativefier is already installed and up to date")
            return True

    def _map_nativefier_file(self, nativefier_settings: dict) -> EnvironmentComponent:
        url = URL_NATIVEFIER.format(version=nativefier_settings['version'])
        return EnvironmentComponent(name='nativefier@{}'.format(nativefier_settings['version']),
                                    url=url,
                                    size=self.http_client.get_content_length(url),
                                    version=nativefier_settings['version'],
                                    id='nativefier')

    def check_environment(self, env: dict, local_config: dict, app: WebApplication, is_x86_x64_arch: bool) -> List[EnvironmentComponent]:
        """
        :param app:
        :param is_x86_x64_arch:
        :return: the environment settings
        """
        components, check_threads = [], []

        system_env = local_config['environment'].get('system', False)

        if system_env:
            self.logger.warning("Using system's nativefier to install {}".format(app.url))
        else:
            node_check = Thread(target=self._check_and_fill_node, args=(env, components))
            node_check.start()
            check_threads.append(node_check)

        elec_check = Thread(target=self._check_and_fill_electron, args=(app, env, local_config, is_x86_x64_arch, components))
        elec_check.start()
        check_threads.append(elec_check)

        for t in check_threads:
            t.join()

        return components

    def update(self, components: List[EnvironmentComponent], handler: ProcessHandler) -> bool:
        self.logger.info('Updating  environment')
        Path(ENV_PATH).mkdir(parents=True, exist_ok=True)

        comp_map = {c.id: c for c in components}

        node_data = comp_map.get('nodejs')
        nativefier_data = comp_map.get('nativefier')

        if node_data:
            if not self._download_and_install(version=node_data.version, version_url=node_data.url, watcher=handler.watcher):
                return False

            if not self._install_nativefier(version=nativefier_data.version, handler=handler):
                return False
        else:
            if nativefier_data and not self._install_nativefier(version=nativefier_data.version, handler=handler):
                return False

        electron_data = comp_map.get('electron')

        if electron_data:
            if not self.download_electron(version=electron_data.version, url=electron_data.url, watcher=handler.watcher):
                return False

        sha256_data = comp_map.get('electron_sha256')

        if sha256_data:
            if not self.download_electron_sha256(version=sha256_data.version, url=sha256_data.url, watcher=handler.watcher):
                return False

        self.logger.info('Environment successfully updated')
        return True
