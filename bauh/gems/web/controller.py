import glob
import json
import os
import re
import shutil
import subprocess
import traceback
from pathlib import Path
from threading import Thread
from typing import List, Type, Set, Tuple

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SearchResult
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageAction, PackageSuggestion, PackageUpdate, PackageHistory
from bauh.api.abstract.view import MessageType, MultipleSelectComponent, InputOption, SingleSelectComponent, \
    SelectViewType
from bauh.commons.html import bold
from bauh.commons.system import ProcessHandler, get_dir_size, get_human_size_str
from bauh.gems.web import INSTALLED_PATH, nativefier, DESKTOP_ENTRY_PATH_PATTERN
from bauh.gems.web.environment import EnvironmentUpdater
from bauh.gems.web.model import WebApplication

try:
    from bs4 import BeautifulSoup, SoupStrainer
    BS4_AVAILABLE = True
except:
    BS4_AVAILABLE = False


try:
    import lxml
    LXML_AVAILABLE = True
except:
    LXML_AVAILABLE = False

RE_PROTOCOL_STRIP = re.compile(r'[a-zA-Z]+://')


class WebApplicationManager(SoftwareManager):

    def __init__(self, context: ApplicationContext, env_updater: Thread = None):
        super(WebApplicationManager, self).__init__(context=context)
        self.http_client = context.http_client
        self.node_updater = EnvironmentUpdater(logger=context.logger, http_client=context.http_client,
                                               file_downloader=context.file_downloader, i18n=context.i18n)
        self.enabled = True
        self.i18n = context.i18n
        self.env_updater = env_updater
        self.env_settings = {}
        self.logger = context.logger

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        res = SearchResult([], [], 0)

        if is_url:

            installed = self.read_installed(disk_loader=disk_loader, limit=limit).installed

            url_no_protocol = RE_PROTOCOL_STRIP.split(words)[0].strip().lower()

            installed_matches = [app for app in installed if RE_PROTOCOL_STRIP.split(app.url)[0].lower() == url_no_protocol]

            if installed_matches:
                res.installed.extend(installed_matches)
                return res

            url_res = self.http_client.get(words)

            if url_res:
                soup = BeautifulSoup(url_res.text, 'lxml', parse_only=SoupStrainer('head'))

                name_tag = soup.head.find('meta', attrs={'name': 'application-name'})
                name = name_tag.get('content') if name_tag else words.split('.')[0].split('://')[1]

                desc_tag = soup.head.find('meta', attrs={'name': 'description'})
                desc = desc_tag.get('content') if desc_tag else words

                icon_tag = soup.head.find('link', attrs={"rel": "icon"})
                icon_url = icon_tag.get('href') if icon_tag else None

                app = WebApplication(url=words, name=name, description=desc, icon_url=icon_url)

                if self.env_settings.get('electron') and self.env_settings['electron'].get('version'):
                    app.version = self.env_settings['electron']['version']
                    app.latest_version = app.version

                res.new = [app]
                res.total = 1
        else:
            # TODO
            pass

        return res

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = True) -> SearchResult:
        res = SearchResult([], [], 0)

        if os.path.exists(INSTALLED_PATH):
            for data_path in glob.glob('{}/*/*data.json'.format(INSTALLED_PATH)):
                with open(data_path, 'r') as f:
                    res.installed.append(WebApplication(installed=True, **json.loads(f.read())))
                    res.total += 1

        return res

    def downgrade(self, pkg: SoftwarePackage, root_password: str, handler: ProcessWatcher) -> bool:
        pass

    def update(self, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        pass

    def uninstall(self, pkg: WebApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        self.logger.info("Checking if {} installation directory {} exists".format(pkg.name, pkg.installation_dir))

        if not os.path.exists(pkg.installation_dir):
            watcher.show_message(title=self.i18n['error'],
                                 body=self.i18n['web.uninstall.error.install_dir.not_found'].format(bold(pkg.installation_dir)),
                                 type_=MessageType.ERROR)
            return False

        self.logger.info("Removing {} installation directory {}".format(pkg.name, pkg.installation_dir))
        try:
            shutil.rmtree(pkg.installation_dir)
        except:
            watcher.show_message(title=self.i18n['error'],
                                 body=self.i18n['web.uninstall.error.remove'].format(bold(pkg.installation_dir)),
                                 type_=MessageType.ERROR)
            traceback.print_exc()
            return False

        self.logger.info("Checking if {} desktop entry file {} exists".format(pkg.name, pkg.desktop_entry))
        if os.path.exists(pkg.desktop_entry):
            try:
                os.remove(pkg.desktop_entry)
            except:
                watcher.show_message(title=self.i18n['error'],
                                     body=self.i18n['web.uninstall.error.remove'].format(bold(pkg.desktop_entry)),
                                     type_=MessageType.ERROR)
                traceback.print_exc()
                return False

        return True

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        return {WebApplication}

    def get_info(self, pkg: WebApplication) -> dict:
        if pkg.installed:
            info = {'{}_{}'.format(idx + 1, att): getattr(pkg, att) for idx, att in enumerate(('url', 'description', 'version', 'installation_dir', 'desktop_entry'))}
            info['6_exec_file'] = pkg.get_exec_path()
            info['7_icon_path'] = pkg.get_disk_icon_path()

            if os.path.exists(pkg.installation_dir):
                info['8_size'] = get_human_size_str(get_dir_size(pkg.installation_dir))

            return info

    def get_history(self, pkg: SoftwarePackage) -> PackageHistory:
        pass

    def _ask_install_options(self, watcher: ProcessWatcher) -> Tuple[bool, List[str]]:
        watcher.change_substatus(self.i18n['web.install.substatus.options'])

        bt_continue = self.i18n['continue'].capitalize()

        option_single_instance = InputOption(label="Single", value="--single-instance", tooltip="It will not allow the application to be opened again if it is already opened")
        option_maximized = InputOption(label="Open maximized", value="--maximize", tooltip="If the installed app should always open maximized")
        option_fullscren = InputOption(label="Fullscreen", value="--full-screen",
                                       tooltip="If the installed app should always open in fullscreen mode")
        option_no_frame = InputOption(label="No frame", value="--hide-window-frame", tooltip="If the installed app should not have a frame around it like browsers have")

        tray_option_off = InputOption(label="Off", value=0, tooltip="Tray mode disabled")
        tray_option_default = InputOption(label="Default", value='--tray', tooltip="The app icon will be attached to the system tray")
        tray_option_min = InputOption(label="Start minimzed", value='--tray=start-in-tray', tooltip="The app will start minized as an icon in the system tray")
        input_tray = SingleSelectComponent(type_=SelectViewType.COMBO, options=[tray_option_off, tray_option_default, tray_option_min], label="Tray mode")
        check_options = MultipleSelectComponent(options=[option_single_instance, option_maximized, option_fullscren, option_no_frame],
                                                default_options={option_single_instance}, label='')

        # input_internal_urls = TextInput()
        components = [
            check_options,
            input_tray
        ]
        res = watcher.request_confirmation(title=self.i18n['web.install.options_dialog.title'],
                                           body=self.i18n['web.install.options_dialog.body'].format(bold(bt_continue)),
                                           components=components,
                                           confirmation_label=bt_continue,
                                           deny_label=self.i18n['cancel'].capitalize())

        if res:
            selected = []

            if check_options.values:
                selected.extend(check_options.get_selected_values())

            if input_tray.value != 0:
                selected.append(input_tray.get_selected_value())

            return res, selected

        return False, []

    def install(self, pkg: WebApplication, root_password: str, watcher: ProcessWatcher) -> bool:

        continue_install, install_options = self._ask_install_options(watcher)

        if not continue_install:
            watcher.print("Installation aborted by the user")
            return False

        if self.env_updater and self.env_updater.is_alive():
            watcher.change_substatus(self.i18n['web.waiting.env_updater'])
            self.env_updater.join()

        watcher.change_substatus(self.i18n['web.env.checking'])
        handler = ProcessHandler(watcher)
        if not self._update_environment(handler=handler):
            watcher.show_message(title=self.i18n['error'], body=self.i18n['web.env.error'].format(bold(pkg.name)), type_=MessageType.ERROR)
            return False

        Path(INSTALLED_PATH).mkdir(parents=True, exist_ok=True)

        pkg_name = pkg.name.lower()

        app_name_id, app_dir = pkg_name, '{}/{}'.format(INSTALLED_PATH, pkg_name)

        counter = 1
        while True:
            if not os.path.exists(app_dir):
                break
            else:
                app_name_id = pkg_name + str(counter)
                app_dir = '{}/{}'.format(INSTALLED_PATH, app_name_id)
                counter += 1

        watcher.change_substatus(self.i18n['web.install.substatus.call_nativefier'].format(bold('nativefier')))
        installed = handler.handle_simple(nativefier.install(url=pkg.url, name=pkg_name, output_dir=app_dir,
                                                             electron_version=self.env_settings['electron']['version'],
                                                             cwd=INSTALLED_PATH,
                                                             extra_options=install_options))

        if not installed:
            msg = '{}.{}.'.format(self.i18n['wen.install.error'].format(bold(pkg.name)),
                                  self.i18n['web.install.nativefier.error.unknown'].format(bold(self.i18n['details'].capitalize())))
            watcher.show_message(title=self.i18n['error'], body=msg, type_=MessageType.ERROR)
            return False

        inner_dir = os.listdir(app_dir)

        if not inner_dir:
            msg = '{}.{}.'.format(self.i18n['wen.install.error'].format(bold(pkg.name)),
                                  self.i18n['web.install.nativefier.error.inner_dir'].format(bold(app_dir)))
            watcher.show_message(title=self.i18n['error'], body=msg, type_=MessageType.ERROR)
            return False

        # bringing the inner app folder to the 'installed' folder level:
        inner_dir = '{}/{}'.format(app_dir, inner_dir[0])
        temp_dir = '{}/tmp_{}'.format(INSTALLED_PATH, app_name_id)
        os.rename(inner_dir, temp_dir)
        shutil.rmtree(app_dir)
        os.rename(temp_dir, app_dir)

        pkg.installation_dir = app_dir

        version_path = '{}/version'.format(app_dir)

        if os.path.exists(version_path):
            with open(version_path, 'r') as f:
                pkg.version = f.read().strip()
                pkg.latest_version = pkg.version

        watcher.change_substatus(self.i18n['web.install.substatus.shortcut'])

        entry_id = app_name_id
        desktop_entry = DESKTOP_ENTRY_PATH_PATTERN.format(name=entry_id)
        while True:
            if not os.path.exists(desktop_entry):
                break
            else:
                counter += 1
                entry_id = pkg_name + str(counter)
                desktop_entry += DESKTOP_ENTRY_PATH_PATTERN.format(name=entry_id)

        entry_content = self._gen_desktop_entry_content(pkg)

        with open(desktop_entry, 'w+') as f:
            f.write(entry_content)

        pkg.desktop_entry = desktop_entry
        return True

    def _gen_desktop_entry_content(self, pkg: WebApplication) -> str:
        return """
        [Desktop Entry]
        Type=Application
        Name={name} ( web )
        Categories=Applications;
        Comment={desc}
        Icon={icon}
        Exec={exec_path}
        """.format(name=pkg.name, exec_path=pkg.get_exec_path(),
                   desc=pkg.description or pkg.url, icon=pkg.get_disk_icon_path())

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> bool:
        return BS4_AVAILABLE and LXML_AVAILABLE

    def requires_root(self, action: str, pkg: SoftwarePackage):
        return False

    def _update_environment(self, handler: ProcessHandler = None) -> bool:
        updated_settings = self.node_updater.update_environment(self.context.is_system_x86_64(), handler=handler)

        if updated_settings is not None:
            self.env_settings = updated_settings
            return True

        return False

    def prepare(self):
        if bool(int(os.getenv('BAUH_WEB_UPDATE_NODE', 1))):
            self.env_updater = Thread(daemon=True, target=self._update_environment)
            self.env_updater.start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        pass

    def list_warnings(self, internet_available: bool) -> List[str]:
        pass

    def list_suggestions(self, limit: int) -> List[PackageSuggestion]:
        pass

    def execute_custom_action(self, action: PackageAction, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        pass

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: WebApplication):
        subprocess.Popen(pkg.get_exec_path())

    def get_screenshots(self, pkg: SoftwarePackage) -> List[str]:
        pass
