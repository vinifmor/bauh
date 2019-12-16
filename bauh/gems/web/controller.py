import glob
import locale
import os
import re
import shutil
import subprocess
import time
import traceback
from pathlib import Path
from threading import Thread
from typing import List, Type, Set, Tuple

import yaml
from colorama import Fore

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SearchResult
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageAction, PackageSuggestion, PackageUpdate, PackageHistory, \
    SuggestionPriority, PackageStatus
from bauh.api.abstract.view import MessageType, MultipleSelectComponent, InputOption, SingleSelectComponent, \
    SelectViewType, TextInputComponent, FormComponent, FileChooserComponent
from bauh.api.constants import DESKTOP_ENTRIES_DIR
from bauh.commons import resource
from bauh.commons.html import bold
from bauh.commons.system import ProcessHandler, get_dir_size, get_human_size_str
from bauh.gems.web import INSTALLED_PATH, nativefier, DESKTOP_ENTRY_PATH_PATTERN, URL_FIX_PATTERN, ENV_PATH, UA_CHROME, \
    ROOT_DIR
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
RE_SEVERAL_SPACES = re.compile(r'\s+')
RE_SYMBOLS_SPLIT = re.compile(r'[\-|_\s:.]')


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
        self.env_thread = None

    def _get_lang_header(self) -> str:
        try:
            system_locale = locale.getdefaultlocale()
            return system_locale[0] if system_locale else 'en_US'
        except:
            return 'en_US'

    def _get_app_name(self, url_no_protocol: str, soup: "BeautifulSoup") -> str:
        name_tag = soup.head.find('meta', attrs={'name': 'application-name'})
        name = name_tag.get('content') if name_tag else None

        if not name:
            name_tag = soup.head.find('title')
            name = name_tag.text.strip() if name_tag else None

        if not name:
            name = url_no_protocol.split('.')[0].strip()

        if name:
            name = RE_SYMBOLS_SPLIT.split(name)[0].strip()

        return name

    def _get_app_icon_url(self, url: str, soup: "BeautifulSoup") -> str:
        for rel in ('icon', 'ICON'):
            icon_tag = soup.head.find('link', attrs={"rel": rel})
            icon_url = icon_tag.get('href') if icon_tag else None

            if icon_url and not icon_url.startswith('http'):
                if icon_url.startswith('//'):
                    icon_url = 'https:{}'.format(icon_url)
                elif icon_url.startswith('/'):
                    icon_url = url + icon_url
                else:
                    icon_url = url + '/{}'.format(icon_url)

            if icon_url:
                return icon_url

        if not icon_url:
            icon_tag = soup.head.find('meta', attrs={"property": 'og:image'})
            icon_url = icon_tag.get('content') if icon_tag else None

            if icon_url:
                return icon_url

    def _get_fix_for(self, url_no_protocol: str) -> str:
        res = self.http_client.get(URL_FIX_PATTERN.format(url=url_no_protocol))

        if res:
            return res.text

    def _strip_url_protocol(self, url: str) -> str:
        return RE_PROTOCOL_STRIP.split(url)[1].strip().lower()

    def serialize_to_disk(self, pkg: SoftwarePackage, icon_bytes: bytes, only_icon: bool):
        super(WebApplicationManager, self).serialize_to_disk(pkg=pkg, icon_bytes=None, only_icon=False)

    def _map_url(self, url: str) -> BeautifulSoup:
        url_res = self.http_client.get(url,
                                       headers={'Accept-language': self._get_lang_header(), 'User-Agent': UA_CHROME},
                                       ignore_ssl=True, single_call=True)

        if url_res:
            return BeautifulSoup(url_res.text, 'lxml', parse_only=SoupStrainer('head'))

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        res = SearchResult([], [], 0)

        installed = self.read_installed(disk_loader=disk_loader, limit=limit).installed

        if is_url:
            url = words[0:-1] if words.endswith('/') else words

            url_no_protocol = self._strip_url_protocol(url)

            installed_matches = [app for app in installed if self._strip_url_protocol(app.url) == url_no_protocol]

            if installed_matches:
                res.installed.extend(installed_matches)
            else:
                soup = self._map_url(url)

                if soup:
                    name = self._get_app_name(url_no_protocol, soup)

                    desc_tag = soup.head.find('meta', attrs={'name': 'description'})
                    desc = desc_tag.get('content') if desc_tag else words

                    icon_url = self._get_app_icon_url(url, soup)

                    app = WebApplication(url=url, name=name, description=desc, icon_url=icon_url)

                    if self.env_settings.get('electron') and self.env_settings['electron'].get('version'):
                        app.version = self.env_settings['electron']['version']
                        app.latest_version = app.version

                    res.new = [app]
        else:
            lower_words = words.lower().strip()
            installed_matches = [app for app in installed if lower_words in app.name.lower()]

            if installed_matches:
                res.installed.extend(installed_matches)

        res.total += len(res.installed)
        res.total += len(res.new)
        return res

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = True) -> SearchResult:
        res = SearchResult([], [], 0)

        if os.path.exists(INSTALLED_PATH):
            for data_path in glob.glob('{}/*/*data.yml'.format(INSTALLED_PATH)):
                with open(data_path, 'r') as f:
                    res.installed.append(WebApplication(installed=True, **yaml.safe_load(f.read())))
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

        autostart_path = pkg.get_autostart_path()
        if os.path.exists(autostart_path):
            try:
                os.remove(autostart_path)
            except:
                watcher.show_message(title=self.i18n['error'],
                                     body=self.i18n['web.uninstall.error.remove'].format(bold(autostart_path)),
                                     type_=MessageType.ERROR)
                traceback.print_exc()

        return True

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        return {WebApplication}

    def get_info(self, pkg: WebApplication) -> dict:
        if pkg.installed:
            info = {'{}_{}'.format(idx + 1, att): getattr(pkg, att) for idx, att in enumerate(('url', 'description', 'version', 'categories', 'installation_dir', 'desktop_entry'))}
            info['7_exec_file'] = pkg.get_exec_path()
            info['8_icon_path'] = pkg.get_disk_icon_path()

            if os.path.exists(pkg.installation_dir):
                info['9_size'] = get_human_size_str(get_dir_size(pkg.installation_dir))

            if info.get('4_categories'):
                info['4_categories'] = [self.i18n[c.lower()].capitalize() for c in info['4_categories']]

            return info

    def get_history(self, pkg: SoftwarePackage) -> PackageHistory:
        pass

    def _ask_install_options(self, app: WebApplication, watcher: ProcessWatcher) -> Tuple[bool, List[str]]:
        watcher.change_substatus(self.i18n['web.install.substatus.options'])

        inp_url = TextInputComponent(label=self.i18n['address'], value=app.url, read_only=True)
        inp_name = TextInputComponent(label=self.i18n['name'], value=app.name)
        inp_desc = TextInputComponent(label=self.i18n['description'], value=app.description)

        cat_ops = [InputOption(label=self.i18n['web.install.option.category.none'].capitalize(), value=0)]
        cat_ops.extend([InputOption(label=self.i18n[c.lower()].capitalize(), value=c) for c in self.context.default_categories])

        inp_cat = SingleSelectComponent(label=self.i18n['category'], type_=SelectViewType.COMBO, options=cat_ops, default_option=cat_ops[0])

        tray_op_off = InputOption(id_='tray_off', label=self.i18n['web.install.option.tray.off.label'], value=0, tooltip=self.i18n['web.install.option.tray.off.tip'])
        tray_op_default = InputOption(id_='tray_def', label=self.i18n['web.install.option.tray.default.label'], value='--tray', tooltip=self.i18n['web.install.option.tray.default.tip'])
        tray_op_min = InputOption(id_='tray_min', label=self.i18n['web.install.option.tray.min.label'], value='--tray=start-in-tray', tooltip=self.i18n['web.install.option.tray.min.tip'])

        inp_tray = SingleSelectComponent(type_=SelectViewType.COMBO,
                                         options=[tray_op_off, tray_op_default, tray_op_min],
                                         label=self.i18n['web.install.option.tray.label'])

        icon_chooser = FileChooserComponent(allowed_extensions={'png'}, label=self.i18n['web.install.option.icon.label'])

        form_1 = FormComponent(components=[inp_url, inp_name, inp_desc, inp_cat, icon_chooser, inp_tray], label=self.i18n['web.install.options.basic'].capitalize())

        op_single = InputOption(id_='single', label=self.i18n['web.install.option.single.label'], value="--single-instance", tooltip=self.i18n['web.install.option.single.tip'])
        op_max = InputOption(id_='max', label=self.i18n['web.install.option.max.label'], value="--maximize", tooltip=self.i18n['web.install.option.max.tip'])
        op_fs = InputOption(id_='fullscreen', label=self.i18n['web.install.option.fullscreen.label'], value="--full-screen", tooltip=self.i18n['web.install.option.fullscreen.tip'])
        op_nframe = InputOption(id_='no_frame', label=self.i18n['web.install.option.noframe.label'], value="--hide-window-frame", tooltip=self.i18n['web.install.option.noframe.tip'])
        op_allow_urls = InputOption(id_='allow_urls', label=self.i18n['web.install.option.allow_urls.label'], value='--internal-urls=.*', tooltip=self.i18n['web.install.option.allow_urls.tip'])
        op_ncache = InputOption(id_='no_cache', label=self.i18n['web.install.option.nocache.label'], value="--clear-cache", tooltip=self.i18n['web.install.option.nocache.tip'])
        op_insecure = InputOption(id_='insecure', label=self.i18n['web.install.option.insecure.label'], value="--insecure", tooltip=self.i18n['web.install.option.insecure.tip'])
        op_igcert = InputOption(id_='ignore_certs', label=self.i18n['web.install.option.ignore_certificate.label'], value="--ignore-certificate", tooltip=self.i18n['web.install.option.ignore_certificate.tip'])

        check_options = MultipleSelectComponent(options=[op_single, op_allow_urls, op_max, op_fs, op_nframe, op_ncache, op_insecure, op_igcert], default_options={op_single}, label=self.i18n['web.install.options.advanced'].capitalize())

        res = watcher.request_confirmation(title=self.i18n['web.install.options_dialog.title'],
                                           body=None,
                                           components=[form_1, check_options],
                                           confirmation_label=self.i18n['continue'].capitalize(),
                                           deny_label=self.i18n['cancel'].capitalize())

        if res:
            selected = []

            if check_options.values:
                selected.extend(check_options.get_selected_values())

            tray_mode = inp_tray.get_selected()
            if tray_mode is not None and tray_mode != 0:
                selected.append(tray_mode)

            custom_name = inp_name.get_value()

            if custom_name:
                app.name = custom_name

            custom_desc = inp_desc.get_value()

            if custom_desc:
                app.description = inp_desc.get_value()

            cat = inp_cat.get_selected()

            if cat != 0:
                app.categories = [cat]

            if icon_chooser.file_path:
                app.set_custom_icon(icon_chooser.file_path)
                selected.append('--icon={}'.format(icon_chooser.file_path))

            return res, selected

        return False, []

    def _gen_app_id(self, name: str) -> Tuple[str, str]:

        treated_name = name.lower().strip().replace(' ', '-')

        while True:
            random_number = str(int(time.time()))
            app_id = '{}-{}'.format(random_number, treated_name)

            if not os.path.exists('{}/{}'.format(INSTALLED_PATH, app_id)):
                return app_id, treated_name

    def _gen_desktop_entry_path(self, app_id: str) -> str:
        base_id = app_id
        counter = 1

        while True:
            desk_path = DESKTOP_ENTRY_PATH_PATTERN.format(name=base_id)
            if not os.path.exists(desk_path):
                return desk_path
            else:
                base_id = '{}_{}'.format(app_id, counter)
                counter += 1

    def install(self, pkg: WebApplication, root_password: str, watcher: ProcessWatcher) -> bool:

        continue_install, install_options = self._ask_install_options(pkg, watcher)

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

        app_id, treated_name = self._gen_app_id(pkg.name)
        pkg.id = app_id
        app_dir = '{}/{}'.format(INSTALLED_PATH, app_id)

        watcher.change_substatus(self.i18n['web.install.substatus.checking_fixes'])
        fix = self._get_fix_for(url_no_protocol=self._strip_url_protocol(pkg.url))
        fix_path = '{}/fix.js'.format(app_dir)

        if fix:
            # just adding the fix as an installation option. The file will be written later
            self.logger.info('Fix found for {}'.format(pkg.url))
            watcher.print('Fix found for {}'.format(pkg.url))
            install_options.append('--inject={}'.format(fix_path))

        watcher.change_substatus(self.i18n['web.install.substatus.call_nativefier'].format(bold('nativefier')))
        installed = handler.handle_simple(nativefier.install(url=pkg.url, name=app_id, output_dir=app_dir,
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
        temp_dir = '{}/tmp_{}'.format(INSTALLED_PATH, treated_name)
        os.rename(inner_dir, temp_dir)
        shutil.rmtree(app_dir)
        os.rename(temp_dir, app_dir)

        # injecting a fix
        if fix:
            self.logger.info('Writting JS fix at {}'.format(fix_path))
            with open(fix_path, 'w+') as f:
                f.write(fix)

        pkg.installation_dir = app_dir

        version_path = '{}/version'.format(app_dir)

        if os.path.exists(version_path):
            with open(version_path, 'r') as f:
                pkg.version = f.read().strip()
                pkg.latest_version = pkg.version

        watcher.change_substatus(self.i18n['web.install.substatus.shortcut'])

        desktop_entry_path = self._gen_desktop_entry_path(app_id)

        entry_content = self._gen_desktop_entry_content(pkg)

        Path(DESKTOP_ENTRIES_DIR).mkdir(parents=True, exist_ok=True)

        with open(desktop_entry_path, 'w+') as f:
            f.write(entry_content)

        pkg.desktop_entry = desktop_entry_path

        if '--tray=start-in-tray' in install_options:
            autostart_dir = '{}/.config/autostart'.format(Path.home())
            Path(autostart_dir).mkdir(parents=True, exist_ok=True)

            with open(pkg.get_autostart_path(), 'w+') as f:
                f.write(entry_content)

        return True

    def _gen_desktop_entry_content(self, pkg: WebApplication) -> str:
        return """
        [Desktop Entry]
        Type=Application
        Name={name} ( web )
        Comment={desc}
        Icon={icon}
        Exec={exec_path}
        {categories}
        """.format(name=pkg.name, exec_path=pkg.get_exec_path(),
                   desc=pkg.description or pkg.url, icon=pkg.get_disk_icon_path(),
                   categories='Categories={}'.format(';'.join(pkg.categories)) if pkg.categories else '')

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
        self.env_thread = Thread(target=self._update_environment)
        self.env_thread.start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        pass

    def list_warnings(self, internet_available: bool) -> List[str]:
        pass

    def _fill_suggestion(self, app: WebApplication):
        soup = self._map_url(app.url)

        if soup:
            if not app.name:
                app.name = self._get_app_name(app.url, soup)

            if not app.description:
                desc_tag = soup.head.find('meta', attrs={'name': 'description'})

                if desc_tag:
                    app.description = desc_tag.get('content')

                if not app.description:
                    desc_tag = soup.find('title')
                    app.description = desc_tag.text if desc_tag else app.url

            find_url = not app.icon_url or (app.icon_url and not self.http_client.exists(app.icon_url))

            if find_url:
                app.icon_url = self._get_app_icon_url(app.url, soup)

        app.status = PackageStatus.READY

    def _map_suggestion(self, suggestion: dict) -> PackageSuggestion:
        app = WebApplication(name=suggestion.get('name'),
                             url=suggestion.get('url'),
                             icon_url=suggestion.get('icon_url'),
                             categories=[suggestion['category']] if suggestion.get('category') else None,
                             preset_options=suggestion.get('options'))
        app.status = PackageStatus.LOADING_DATA

        Thread(target=self._fill_suggestion, args=(app,)).start()

        return PackageSuggestion(priority=SuggestionPriority(suggestion['priority']), package=app)

    def list_suggestions(self, limit: int) -> List[PackageSuggestion]:
        with open(resource.get_path('suggestions.yml', ROOT_DIR), 'r') as f:
            suggestions = yaml.safe_load(f.read())

        if suggestions:
            suggestions = list(suggestions.values())
            suggestions.sort(key=lambda s: s.get('priority', 0), reverse=True)
            to_map = suggestions if limit <= 0 else suggestions[0:limit]
            res = [self._map_suggestion(s) for s in to_map]
            self.env_thread.join()

            if self.env_settings:
                for s in res:
                    s.package.version = self.env_settings['electron']['version']
                    s.package.latest_version = s.package.version

            return res

    def execute_custom_action(self, action: PackageAction, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        pass

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: WebApplication):
        subprocess.Popen(pkg.get_exec_path())

    def get_screenshots(self, pkg: SoftwarePackage) -> List[str]:
        pass

    def clear_data(self):
        if os.path.exists(ENV_PATH):
            print('[bauh][web] Deleting directory {}'.format(ENV_PATH))

            try:
                shutil.rmtree(ENV_PATH)
                print('{}[bauh][web] Directory {} deleted{}'.format(Fore.YELLOW, ENV_PATH, Fore.RESET))
            except:
                print('{}[bauh][web] An exception has happened when deleting {}{}'.format(Fore.RED, ENV_PATH, Fore.RESET))
                traceback.print_exc()