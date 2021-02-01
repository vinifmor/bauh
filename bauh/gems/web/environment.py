import glob
import logging
import os
import shutil
import tarfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Dict, List, Optional

import requests
import yaml

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.view import MessageType
from bauh.api.http import HttpClient
from bauh.commons import system
from bauh.commons.html import bold
from bauh.commons.system import SimpleProcess, ProcessHandler
from bauh.gems.web import ENV_PATH, NODE_DIR_PATH, NODE_BIN_PATH, NODE_MODULES_PATH, NATIVEFIER_BIN_PATH, \
    ELECTRON_PATH, ELECTRON_DOWNLOAD_URL, ELECTRON_SHA256_URL, URL_ENVIRONMENT_SETTINGS, NPM_BIN_PATH, NODE_PATHS, \
    nativefier, ELECTRON_WIDEVINE_URL, ELECTRON_WIDEVINE_SHA256_URL, \
    ENVIRONMENT_SETTINGS_CACHED_FILE, ENVIRONMENT_SETTINGS_TS_FILE, get_icon_path, NATIVEFIER_BASE_URL
from bauh.gems.web.model import WebApplication
from bauh.view.util.translation import I18n


class EnvironmentComponent:

    def __init__(self, id: str, name: str, size: str, version: str, url: str, update: bool = False, properties: Optional[dict] = None):
        self.id = id
        self.name = name
        self.size = size
        self.version = version
        self.url = url
        self.update = update
        self.properties = properties


class EnvironmentUpdater:

    def __init__(self, logger: logging.Logger, http_client: HttpClient, file_downloader: FileDownloader, i18n: I18n, taskman: Optional[TaskManager] = None):
        self.logger = logger
        self.file_downloader = file_downloader
        self.i18n = i18n
        self.http_client = http_client
        self.task_read_settings_id = 'web_read_settings'
        self.taskman = taskman

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

                if os.path.exists(NODE_DIR_PATH):
                    self.logger.info("Removing old NodeJS version installation dir -> {}".format(NODE_DIR_PATH))
                    try:
                        shutil.rmtree(NODE_DIR_PATH)
                    except:
                        self.logger.error("Could not delete old NodeJS version dir -> {}".format(NODE_DIR_PATH))
                        traceback.print_exc()
                        return False

                try:
                    os.rename(extracted_file, NODE_DIR_PATH)
                except:
                    self.logger.error("Could not rename the NodeJS version file {} as {}".format(extracted_file, NODE_DIR_PATH))
                    traceback.print_exc()
                    return False

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
                traceback.print_exc()
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

    def _install_nativefier(self, version: str, url: str, handler: ProcessHandler) -> bool:
        self.logger.info("Checking if nativefier@{} exists".format(version))

        if not url or not self.http_client.exists(url):
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

    def download_electron(self, version: str, url: str, widevine: bool, watcher: ProcessWatcher) -> bool:
        Path(ELECTRON_PATH).mkdir(parents=True, exist_ok=True)
        self.logger.info("Downloading Electron {}".format(version))

        electron_path = self._get_electron_file_path(url=url, relative=False)

        if not self.http_client.exists(url):
            self.logger.warning("The file {} seems not to exist".format(url))
            watcher.show_message(title=self.i18n['message.file.not_exist'],
                                 body=self.i18n['message.file.not_exist.body'].format(bold(url)),
                                 type_=MessageType.ERROR)
            return False

        return self.file_downloader.download(file_url=url, watcher=watcher, output_path=electron_path, cwd=ELECTRON_PATH)

    def download_electron_sha256(self, version: str, url: str, widevine: bool, watcher: ProcessWatcher) -> bool:
        self.logger.info("Downloading Electron {} sha526".format(version))

        sha256_path = self._get_electron_file_path(url=url, relative=False)

        if not self.http_client.exists(url):
            self.logger.warning("The file {} seems not to exist".format(url))
            watcher.show_message(title=self.i18n['message.file.not_exist'],
                                 body=self.i18n['message.file.not_exist.body'].format(bold(url)),
                                 type_=MessageType.ERROR)
            return False

        return self.file_downloader.download(file_url=url, watcher=watcher, output_path=sha256_path, cwd=ELECTRON_PATH)

    def _get_electron_url(self, version: str, is_x86_x64_arch: bool, widevine: bool) -> str:
        arch = 'x64' if is_x86_x64_arch else 'ia32'
        if widevine:
            return ELECTRON_WIDEVINE_URL.format(version=version, arch=arch)
        else:
            return ELECTRON_DOWNLOAD_URL.format(version=version, arch=arch)

    def _get_electron_sha256_url(self, version: str, widevine: bool) -> str:
        if widevine:
            return ELECTRON_WIDEVINE_SHA256_URL.format(version=version)
        else:
            return ELECTRON_SHA256_URL.format(version=version)

    def _get_electron_file_path(self, url: str, relative: bool) -> str:
        file_path = url.replace(':', '').replace('/', '') + '/' + url.split('/')[-1]
        return '{}/{}'.format(ELECTRON_PATH, file_path) if not relative else file_path

    def check_electron_installed(self, version: str, is_x86_x64_arch: bool, widevine: bool) -> Dict[str, bool]:
        self.logger.info("Checking if Electron {} (widevine={}) is installed".format(version, widevine))
        res = {'electron': False, 'sha256': False}

        if not os.path.exists(ELECTRON_PATH):
            self.logger.info("The Electron folder {} was not found".format(ELECTRON_PATH))
        else:
            files = {f.split(ELECTRON_PATH + '/')[1] for f in glob.glob(ELECTRON_PATH + '/**', recursive=True) if os.path.isfile(f)}

            if files:
                electron_url = self._get_electron_url(version, is_x86_x64_arch, widevine)
                file_path = self._get_electron_file_path(url=electron_url, relative=True)

                res['electron'] = file_path in files

                if not res['electron']:
                    res['sha256'] = True
                else:
                    sha_url = self._get_electron_sha256_url(version=version, widevine=widevine)
                    sha_path = self._get_electron_file_path(url=sha_url, relative=True)
                    res['sha256'] = sha_path in files
            else:
                self.logger.info('No Electron file found in {}'.format(ELECTRON_PATH))

            for att in ('electron', 'sha256'):
                if res[att]:
                    self.logger.info('{} ({}) already downloaded'.format(att, version))

        return res

    def _finish_task_download_settings(self):
        if self.taskman:
            self.taskman.update_progress(self.task_read_settings_id, 100, None)
            self.taskman.finish_task(self.task_read_settings_id)

    def should_download_settings(self, web_config: dict) -> bool:
        try:
            settings_exp = int(web_config['environment']['cache_exp'])
        except ValueError:
            self.logger.error("Could not parse settings property 'environment.cache_exp': {}".format(web_config['environment']['cache_exp']))
            return True

        if settings_exp <= 0:
            self.logger.info("No expiration time configured for the environment settings cache file.")
            return True

        self.logger.info("Checking cached environment settings file")

        if not os.path.exists(ENVIRONMENT_SETTINGS_CACHED_FILE):
            self.logger.warning("Environment settings file not cached.")
            return True

        if not os.path.exists(ENVIRONMENT_SETTINGS_TS_FILE):
            self.logger.warning("Environment settings file has no timestamp associated with it.")
            return True

        with open(ENVIRONMENT_SETTINGS_TS_FILE) as f:
            env_ts_str = f.read()

        try:
            env_timestamp = datetime.fromtimestamp(float(env_ts_str))
        except:
            self.logger.error("Could not parse environment settings file timestamp: {}".format(env_ts_str))
            return True

        expired = env_timestamp + timedelta(hours=settings_exp) <= datetime.utcnow()

        if expired:
            self.logger.info("Environment settings file has expired. It should be re-downloaded")
            return True
        else:
            self.logger.info("Cached environment settings file is up to date")
            return False

    def read_cached_settings(self, web_config: dict) -> Optional[dict]:
        if not self.should_download_settings(web_config):
            with open(ENVIRONMENT_SETTINGS_CACHED_FILE) as f:
                cached_settings_str = f.read()

            try:
                return yaml.safe_load(cached_settings_str)
            except yaml.YAMLError:
                self.logger.error('Could not parse the cache environment settings file: {}'.format(cached_settings_str))

    def read_settings(self, web_config: dict, cache: bool = True) -> Optional[dict]:
        if self.taskman:
            self.taskman.register_task(self.task_read_settings_id, self.i18n['web.task.download_settings'], get_icon_path())
            self.taskman.update_progress(self.task_read_settings_id, 1, None)

        cached_settings = self.read_cached_settings(web_config) if cache else None

        if cached_settings:
            return cached_settings

        try:
            if self.taskman:
                self.taskman.update_progress(self.task_read_settings_id, 10, None)

            self.logger.info("Downloading environment settings")
            res = self.http_client.get(URL_ENVIRONMENT_SETTINGS)

            if not res:
                self.logger.warning('Could not retrieve the environments settings from the cloud')
                self._finish_task_download_settings()
                return

            try:
                settings = yaml.safe_load(res.content)
            except yaml.YAMLError:
                self.logger.error('Could not parse environment settings: {}'.format(res.text))
                self._finish_task_download_settings()
                return

            self.logger.info("Caching environment settings to disk")
            cache_dir = os.path.dirname(ENVIRONMENT_SETTINGS_CACHED_FILE)

            try:
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
            except OSError:
                self.logger.error("Could not create Web cache directory: {}".format(cache_dir))
                self.logger.info('Finished')
                self._finish_task_download_settings()
                return

            cache_timestamp = datetime.utcnow().timestamp()
            with open(ENVIRONMENT_SETTINGS_CACHED_FILE, 'w+') as f:
                f.write(yaml.safe_dump(settings))

            with open(ENVIRONMENT_SETTINGS_TS_FILE, 'w+') as f:
                f.write(str(cache_timestamp))

            self._finish_task_download_settings()
            self.logger.info("Finished")
            return settings

        except requests.exceptions.ConnectionError:
            self._finish_task_download_settings()
            return

    def _check_and_fill_electron(self, pkg: WebApplication, env: dict, local_config: dict, x86_x64: bool, widevine: bool, output: List[EnvironmentComponent]):
        electron_version = env['electron-wvvmp' if widevine else 'electron']['version']

        if not widevine and pkg.version and pkg.version != electron_version:  # this feature does not support custom widevine electron at the moment
            self.logger.info('A preset Electron version is defined for {}: {}'.format(pkg.url, pkg.version))
            electron_version = pkg.version

        if not widevine and local_config['environment']['electron']['version']:
            self.logger.warning("A custom Electron version will be used {} to install {}".format(electron_version, pkg.url))
            electron_version = local_config['environment']['electron']['version']

        electron_status = self.check_electron_installed(version=electron_version, is_x86_x64_arch=x86_x64, widevine=widevine)

        electron_url = self._get_electron_url(version=electron_version, is_x86_x64_arch=x86_x64, widevine=widevine)
        output.append(EnvironmentComponent(name=electron_url.split('/')[-1],
                                           version=electron_version,
                                           url=electron_url,
                                           size=self.http_client.get_content_length(electron_url),
                                           id='electron',
                                           update=not electron_status['electron'],
                                           properties={'widevine': widevine}))

        sha_url = self._get_electron_sha256_url(version=electron_version, widevine=widevine)

        output.append(EnvironmentComponent(name=sha_url.split('/')[-1],
                                           version=electron_version,
                                           url=sha_url,
                                           size=self.http_client.get_content_length(sha_url),
                                           id='electron_sha256',
                                           update=not electron_status['electron'] or not electron_status['sha256'],
                                           properties={'widevine': widevine}))

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
        base_url = nativefier_settings.get('url')
        if not base_url:
            self.logger.warning("'url' not found in nativefier environment settings. Using hardcoded URL '{}'".format(NATIVEFIER_BASE_URL))
            base_url = NATIVEFIER_BASE_URL

        url = base_url.format(version=nativefier_settings['version'])
        return EnvironmentComponent(name='nativefier@{}'.format(nativefier_settings['version']),
                                    url=url,
                                    size=self.http_client.get_content_length(url),
                                    version=nativefier_settings['version'],
                                    id='nativefier')

    def check_environment(self, env: dict, local_config: dict, app: WebApplication,
                          is_x86_x64_arch: bool, widevine: bool) -> List[EnvironmentComponent]:
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

        elec_check = Thread(target=self._check_and_fill_electron, args=(app, env, local_config, is_x86_x64_arch, widevine, components))
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

            if not self._install_nativefier(version=nativefier_data.version, url=nativefier_data.url, handler=handler):
                return False
        else:
            if nativefier_data and not self._install_nativefier(version=nativefier_data.version, url=nativefier_data.url, handler=handler):
                return False

        electron_data = comp_map.get('electron')

        if electron_data:
            if not self.download_electron(version=electron_data.version, url=electron_data.url, watcher=handler.watcher, widevine=electron_data.properties['widevine']):
                return False

        sha256_data = comp_map.get('electron_sha256')

        if sha256_data:
            if not self.download_electron_sha256(version=sha256_data.version, url=sha256_data.url, watcher=handler.watcher, widevine=sha256_data.properties['widevine']):
                return False

        self.logger.info('Environment successfully updated')
        return True
