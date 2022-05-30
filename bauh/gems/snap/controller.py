import re
import time
import traceback
from threading import Thread
from typing import List, Set, Type, Optional, Tuple, Generator

from bauh.api.abstract.controller import SoftwareManager, SearchResult, ApplicationContext, UpgradeRequirements, \
    TransactionResult, SoftwareAction, SettingsView, SettingsController
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import SoftwarePackage, PackageHistory, PackageUpdate, PackageSuggestion, \
    SuggestionPriority, PackageStatus
from bauh.api.abstract.view import SingleSelectComponent, SelectViewType, InputOption, PanelComponent, \
    FormComponent, TextInputComponent
from bauh.api.exception import NoInternetException
from bauh.commons import suggestions
from bauh.commons.boot import CreateConfigFile
from bauh.commons.category import CategoriesDownloader
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, ProcessHandler, new_root_subprocess
from bauh.commons.view_utils import new_select, get_human_size_str
from bauh.gems.snap import snap, URL_CATEGORIES_FILE, CATEGORIES_FILE_PATH, \
    get_icon_path, snapd
from bauh.gems.snap.config import SnapConfigManager
from bauh.gems.snap.model import SnapApplication
from bauh.gems.snap.snapd import SnapdClient

RE_AVAILABLE_CHANNELS = re.compile(re.compile(r'(\w+)\s+(snap install.+)'))


class SnapManager(SoftwareManager, SettingsController):

    def __init__(self, context: ApplicationContext):
        super(SnapManager, self).__init__(context=context)
        self.i18n = context.i18n
        self.api_cache = context.cache_factory.new()
        context.disk_loader_factory.map(SnapApplication, self.api_cache)
        self.enabled = True
        self.http_client = context.http_client
        self.logger = context.logger
        self.ubuntu_distro = context.distro == 'ubuntu'
        self.categories = {}
        self.suggestions_cache = context.cache_factory.new()
        self.info_path = None
        self.configman = SnapConfigManager()
        self._suggestions_url: Optional[str] = None

    def _fill_categories(self, app: SnapApplication):
        categories = self.categories.get(app.name.lower())

        if categories:
            app.categories = categories

        if not app.is_application():
            categories = app.categories

            if categories is None:
                categories = []
                app.categories = categories

            if 'runtime' not in categories:
                categories.append('runtime')

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        if is_url or (not snap.is_installed() and not snapd.is_running()):
            return SearchResult([], [], 0)

        snapd_client = SnapdClient(self.logger)
        apps_found = snapd_client.query(words)

        res = SearchResult([], [], 0)

        if apps_found:
            installed = self.read_installed(disk_loader).installed

            for app_json in apps_found:
                already_installed = None

                if installed:
                    already_installed = [i for i in installed if i.id == app_json.get('id')]
                    already_installed = already_installed[0] if already_installed else None

                if already_installed:
                    res.installed.append(already_installed)
                else:
                    res.new.append(self._map_to_app(app_json, installed=False))

        res.total = len(res.installed) + len(res.new)
        return res

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None) -> SearchResult:
        if snap.is_installed() and snapd.is_running():
            snapd_client = SnapdClient(self.logger)
            app_names = {a['snap'] for a in snapd_client.list_only_apps()}
            installed = [self._map_to_app(app_json=appjson,
                                          installed=True,
                                          disk_loader=disk_loader,
                                          is_application=app_names and appjson['name'] in app_names) for appjson in snapd_client.list_all_snaps()]
            return SearchResult(installed, None, len(installed))
        else:
            return SearchResult([], None, 0)

    def downgrade(self, pkg: SnapApplication, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        if not snap.is_installed():
            watcher.print("'snap' seems not to be installed")
            return False
        if not snapd.is_running():
            watcher.print("'snapd' seems not to be running")
            return False

        return ProcessHandler(watcher).handle_simple(snap.downgrade_and_stream(pkg.name, root_password))[0]

    def upgrade(self, requirements: UpgradeRequirements, root_password: Optional[str], watcher: ProcessWatcher) -> SystemProcess:
        raise Exception(f"'upgrade' is not supported by {SnapManager.__class__.__name__}")

    def uninstall(self, pkg: SnapApplication, root_password: Optional[str], watcher: ProcessWatcher, disk_loader: DiskCacheLoader) -> TransactionResult:
        if snap.is_installed() and snapd.is_running():
            uninstalled = ProcessHandler(watcher).handle_simple(snap.uninstall_and_stream(pkg.name, root_password))[0]

            if uninstalled:
                if self.suggestions_cache:
                    self.suggestions_cache.delete(pkg.name)

                return TransactionResult(success=True, installed=None, removed=[pkg])

        return TransactionResult.fail()

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        return {SnapApplication}

    def clean_cache_for(self, pkg: SnapApplication):
        super(SnapManager, self).clean_cache_for(pkg)
        self.api_cache.delete(pkg.id)

    def get_info(self, pkg: SnapApplication) -> dict:
        info = {
            'description': pkg.description,
            'developer': pkg.developer,
            'license': pkg.license,
            'contact': pkg.contact,
            'snap-id': pkg.id,
            'name': pkg.name,
            'publisher': pkg.publisher,
            'revision': pkg.rev,
            'tracking': pkg.tracking,
            'channel': pkg.channel,
            'type': pkg.type
        }

        if pkg.installed:
            commands = [*{c['name'] for c in SnapdClient(self.logger).list_commands(pkg.name)}]
            commands.sort()
            info['commands'] = commands

            if pkg.installed_size:
                info['installed_size']: get_human_size_str(pkg.installed_size)
        elif pkg.download_size:
            info['download_size'] = get_human_size_str(pkg.download_size)

        return info

    def get_history(self, pkg: SnapApplication) -> PackageHistory:
        raise Exception(f"'get_history' is not supported by {pkg.__class__.__name__}")

    def install(self, pkg: SnapApplication, root_password: Optional[str], disk_loader: DiskCacheLoader, watcher: ProcessWatcher) -> TransactionResult:
        # retrieving all installed so it will be possible to know the additional installed runtimes after the operation succeeds
        if not snap.is_installed():
            watcher.print("'snap' seems not to be installed")
            return TransactionResult.fail()

        if not snapd.is_running():
            watcher.print("'snapd' seems not to be running")
            return TransactionResult.fail()

        installed_names = {s['name'] for s in SnapdClient(self.logger).list_all_snaps()}

        client = SnapdClient(self.logger)
        snap_config = self.configman.get_config()

        try:
            channel = self._request_channel_installation(pkg=pkg, snap_config=snap_config, snapd_client=client, watcher=watcher)
            pkg.channel = channel
        except:
            watcher.print('Aborted by user')
            return TransactionResult.fail()

        res, output = ProcessHandler(watcher).handle_simple(snap.install_and_stream(app_name=pkg.name,
                                                                                    confinement=pkg.confinement,
                                                                                    root_password=root_password,
                                                                                    channel=channel))

        if 'error:' in output:
            res = False
            if 'not available on stable' in output:
                channels = RE_AVAILABLE_CHANNELS.findall(output)

                if channels:
                    opts = [InputOption(label=c[0], value=c[1]) for c in channels]
                    channel_select = SingleSelectComponent(type_=SelectViewType.RADIO, label='', options=opts, default_option=opts[0])
                    body = f"<p>{self.i18n['snap.install.available_channels.message'].format(bold(self.i18n['stable']), bold(pkg.name))}.</p>"
                    body += f"<p>{self.i18n['snap.install.available_channels.help']}:</p>"

                    if watcher.request_confirmation(title=self.i18n['snap.install.available_channels.title'],
                                                    body=body,
                                                    components=[channel_select],
                                                    confirmation_label=self.i18n['continue'],
                                                    deny_label=self.i18n['cancel']):
                        self.logger.info(f"Installing '{pkg.name}' with the custom command '{channel_select.value}'")
                        res = ProcessHandler(watcher).handle(SystemProcess(new_root_subprocess(channel_select.value.value.split(' '), root_password=root_password)))
                        return self._gen_installation_response(success=res, pkg=pkg,
                                                               installed=installed_names, disk_loader=disk_loader)
                else:
                    self.logger.error(f"Could not find available channels in the installation output: {output}")

        return self._gen_installation_response(success=res, pkg=pkg, installed=installed_names, disk_loader=disk_loader)

    def _gen_installation_response(self, success: bool, pkg: SnapApplication, installed: Set[str], disk_loader: DiskCacheLoader):
        if success:
            new_installed = []
            try:
                net_available = self.context.internet_checker.is_available()
                current_installed = self.read_installed(disk_loader=disk_loader, internet_available=net_available).installed
            except:
                new_installed = [pkg]
                traceback.print_exc()
                current_installed = None

            if current_installed:
                for p in current_installed:
                    if p.name == pkg.name or (not installed or p.name not in installed):
                        new_installed.append(p)

            return TransactionResult(success=success, installed=new_installed, removed=[])
        else:
            return TransactionResult.fail()

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> Tuple[bool, Optional[str]]:
        return (True, None) if snap.is_installed() else (False, self.i18n['missing_dep'].format(dep=bold('snap')))

    def requires_root(self, action: SoftwareAction, pkg: SnapApplication) -> bool:
        return action not in (SoftwareAction.PREPARE, SoftwareAction.SEARCH)

    def refresh(self, pkg: SnapApplication, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle_simple(snap.refresh_and_stream(pkg.name, root_password))[0]

    def change_channel(self, pkg: SnapApplication, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        if not self.context.internet_checker.is_available():
            raise NoInternetException()

        try:
            channel = self._request_channel_installation(pkg=pkg,
                                                         snap_config=None,
                                                         snapd_client=SnapdClient(self.logger),
                                                         watcher=watcher,
                                                         exclude_current=True)

            if not channel:
                watcher.show_message(title=self.i18n['snap.action.channel.label'],
                                     body=self.i18n['snap.action.channel.error.no_channel'])
                return False

            return ProcessHandler(watcher).handle_simple(snap.refresh_and_stream(app_name=pkg.name,
                                                                                 root_password=root_password,
                                                                                 channel=channel))[0]
        except:
            return False

    def _start_category_task(self, taskman: TaskManager, create_config: CreateConfigFile, downloader: CategoriesDownloader):
        if taskman:
            taskman.update_progress('snap_cats', 0, self.i18n['task.waiting_task'].format(bold(create_config.task_name)))
            create_config.join()

            categories_exp = create_config.config['categories_exp']
            downloader.expiration = categories_exp if isinstance(categories_exp, int) else None
            taskman.update_progress('snap_cats', 1, None)

    def _finish_category_task(self, taskman: TaskManager):
        if taskman:
            taskman.update_progress('snap_cats', 100, None)
            taskman.finish_task('snap_cats')

    def prepare(self, task_manager: TaskManager, root_password: Optional[str], internet_available: bool):
        create_config = CreateConfigFile(taskman=task_manager, configman=self.configman, i18n=self.i18n,
                                         task_icon_path=get_icon_path(), logger=self.logger)
        create_config.start()

        task_manager.register_task('snap_cats', self.i18n['task.download_categories'], get_icon_path())
        category_downloader = CategoriesDownloader(id_='snap', manager=self, http_client=self.http_client,
                                                   logger=self.logger,
                                                   url_categories_file=URL_CATEGORIES_FILE,
                                                   categories_path=CATEGORIES_FILE_PATH,
                                                   internet_connection=internet_available,
                                                   internet_checker=self.context.internet_checker,
                                                   after=lambda: self._finish_category_task(task_manager))
        category_downloader.before = lambda: self._start_category_task(task_manager, create_config, category_downloader)
        category_downloader.start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        pass

    def list_warnings(self, internet_available: bool) -> Optional[List[str]]:
        if not snapd.is_running():
            snap_bold = bold('Snap')
            return [self.i18n['snap.notification.snapd_unavailable'].format(bold('snapd'), snap_bold),
                    self.i18n['snap.notification.snap.disable'].format(snap_bold,
                                                                       bold(f"{self.i18n['settings'].capitalize()} > {self.i18n['core.config.tab.types']}"))]
        elif internet_available:
            available, output = snap.is_api_available()

            if not available:
                self.logger.warning(f'It seems Snap API is not available. Search output: {output}')
                return [self.i18n['snap.notifications.api.unavailable'].format(bold('Snaps'), bold('Snap'))]

    def _fill_suggestion(self, name: str, priority: SuggestionPriority, snapd_client: SnapdClient,
                         out: List[PackageSuggestion]):
        res = snapd_client.find_by_name(name)

        if res:
            if len(res) == 1:
                app_json = res[0]
            else:
                jsons_found = [p for p in res if p['name'] == name]
                app_json = jsons_found[0] if jsons_found else None

            if app_json:
                sug = PackageSuggestion(self._map_to_app(app_json, False), priority)
                self.suggestions_cache.add(name, sug)
                out.append(sug)
                return

        self.logger.warning(f"Could not retrieve suggestion '{name}'")

    def _map_to_app(self, app_json: dict, installed: bool, disk_loader: Optional[DiskCacheLoader] = None, is_application: bool = False) -> SnapApplication:
        app = SnapApplication(id=app_json.get('id'),
                              name=app_json.get('name'),
                              license=app_json.get('license'),
                              version=app_json.get('version'),
                              latest_version=app_json.get('version'),
                              description=app_json.get('description', app_json.get('summary')),
                              installed=installed,
                              rev=app_json.get('revision'),
                              publisher=app_json['publisher'].get('display-name', app_json['publisher'].get('username')),
                              verified_publisher=app_json['publisher'].get('validation') == 'verified',
                              icon_url=app_json.get('icon'),
                              screenshots={m['url'] for m in app_json.get('media', []) if m['type'] == 'screenshot'},
                              download_size=app_json.get('download-size'),
                              channel=app_json.get('channel'),
                              confinement=app_json.get('confinement'),
                              app_type=app_json.get('type'),
                              app=is_application,
                              installed_size=app_json.get('installed-size'))

        if disk_loader and app.installed:
            disk_loader.fill(app)

        self._fill_categories(app)

        app.status = PackageStatus.READY
        return app

    def _read_local_suggestions_file(self) -> Optional[str]:
        try:
            with open(self.suggestions_url) as f:
                suggestions_str = f.read()

            return suggestions_str
        except FileNotFoundError:
            self.logger.error(f"Local Snap suggestions file not found: {self.suggestions_url}")
        except OSError:
            self.logger.error(f"Could not read local Snap suggestions file: {self.suggestions_url}")
            traceback.print_exc()

    def _download_remote_suggestions_file(self) -> Optional[str]:
        self.logger.info(f"Downloading the Snap suggestions from {self.suggestions_url}")
        file = self.http_client.get(self.suggestions_url)

        if file:
            return file.text

    def list_suggestions(self, limit: int, filter_installed: bool) -> Optional[List[PackageSuggestion]]:
        if limit == 0 or not snapd.is_running():
            return

        if self.is_local_suggestions_file_mapped():
            suggestions_str = self._read_local_suggestions_file()
        else:
            suggestions_str = self._download_remote_suggestions_file()

        if suggestions_str is None:
            return

        if not suggestions_str:
            self.logger.warning(f"No Snap suggestion found in {self.suggestions_url}")
            return

        ids_prios = suggestions.parse(suggestions_str, self.logger, 'Snap')

        if not ids_prios:
            self.logger.warning(f"No Snap suggestion could be parsed from {self.suggestions_url}")
            return

        suggestion_by_priority = suggestions.sort_by_priority(ids_prios)
        snapd_client = SnapdClient(self.logger)

        if filter_installed:
            installed = {s['name'].lower() for s in snapd_client.list_all_snaps()}

            if installed:
                suggestion_by_priority = tuple(n for n in suggestion_by_priority if n not in installed)

        if suggestion_by_priority and 0 < limit < len(suggestion_by_priority):
            suggestion_by_priority = suggestion_by_priority[0:limit]

        self.logger.info(f'Available Snap suggestions: {len(suggestion_by_priority)}')

        if not suggestion_by_priority:
            return

        self.logger.info("Mapping Snap suggestions")

        instances, threads = [], []

        res, cached_count = [], 0
        for name in suggestion_by_priority:
            cached_sug = self.suggestions_cache.get(name)

            if cached_sug:
                res.append(cached_sug)
                cached_count += 1
            else:
                t = Thread(target=self._fill_suggestion, args=(name, ids_prios[name], snapd_client, res))
                t.start()
                threads.append(t)
                time.sleep(0.001)  # to avoid being blocked

        for t in threads:
            t.join()

        if cached_count > 0:
            self.logger.info(f"Returning {cached_count} cached Snap suggestions")

        return res

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: SnapApplication):
        commands = SnapdClient(self.logger).list_commands(pkg.name)

        if commands:
            if len(commands) == 1:
                cmd = commands[0]['name']
            else:
                desktop_cmd = [c for c in commands if 'desktop-file' in c]

                if desktop_cmd:
                    cmd = desktop_cmd[0]['name']
                else:
                    cmd = commands[0]['name']

            self.logger.info(f"Running '{pkg.name}': {cmd}")
            snap.run(cmd)

    def get_screenshots(self, pkg: SnapApplication) -> Generator[str, None, None]:
        if pkg.screenshots:
            yield from pkg.screenshots

    def get_settings(self) -> Optional[Generator[SettingsView, None, None]]:
        snap_config = self.configman.get_config()

        install_channel = new_select(label=self.i18n['snap.config.install_channel'],
                                     opts=[(self.i18n['yes'].capitalize(), True, None),
                                           (self.i18n['no'].capitalize(), False, None)],
                                     value=bool(snap_config['install_channel']),
                                     id_='snap_install_channel',
                                     tip=self.i18n['snap.config.install_channel.tip'])

        cat_exp_val = snap_config['categories_exp'] if isinstance(snap_config['categories_exp'], int) else ''
        categories_exp = TextInputComponent(id_='snap_cat_exp',
                                            value=cat_exp_val,
                                            only_int=True,
                                            label=self.i18n['snap.config.categories_exp'],
                                            tooltip=self.i18n['snap.config.categories_exp.tip'])

        panel = PanelComponent([FormComponent([install_channel, categories_exp], self.i18n['installation'].capitalize())])
        yield SettingsView(self, panel)

    def save_settings(self, component: PanelComponent) -> Tuple[bool, Optional[List[str]]]:
        config_ = self.configman.get_config()

        form = component.get_component_by_idx(0, FormComponent)
        config_['install_channel'] = form.get_component('snap_install_channel', SingleSelectComponent).get_selected()
        config_['categories_exp'] = form.get_component('snap_cat_exp', TextInputComponent).get_int_value()

        try:
            self.configman.save_config(config_)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def _request_channel_installation(self, pkg: SnapApplication, snap_config: Optional[dict], snapd_client: SnapdClient, watcher: ProcessWatcher, exclude_current: bool = False) -> Optional[str]:
        if snap_config is None or snap_config['install_channel']:
            try:
                data = [r for r in snapd_client.find_by_name(pkg.name) if r['name'] == pkg.name]
            except:
                self.logger.warning(f"snapd client could not retrieve channels for '{pkg.name}'")
                return

            if not data:
                self.logger.warning(f"snapd client could find a match for name '{pkg.name}' when retrieving its channels")
            else:
                if not data[0].get('channels'):
                    self.logger.info(f"No channel available for '{pkg.name}'. Skipping selection.")
                else:
                    if pkg.channel:
                        current_channel = pkg.channel if '/' in pkg.channel else f'latest/{pkg.channel}'
                    else:
                        current_channel = f"latest/{data[0].get('channel', 'stable')}"

                    opts = []
                    def_opt = None
                    for channel in sorted(data[0]['channels'].keys()):
                        if exclude_current:
                            if channel != current_channel:
                                opts.append(InputOption(label=channel, value=channel))
                        else:
                            op = InputOption(label=channel, value=channel)
                            opts.append(op)

                            if not def_opt and channel == current_channel:
                                def_opt = op

                    if not opts:
                        self.logger.info(f"No different channel available for '{pkg.name}'. Skipping selection.")
                        return

                    select = SingleSelectComponent(label='',
                                                   options=opts,
                                                   default_option=def_opt if def_opt else opts[0],
                                                   type_=SelectViewType.RADIO)

                    if not watcher.request_confirmation(title=self.i18n['snap.install.available_channels.title'],
                                                        body=self.i18n['snap.install.channel.body'] + ':',
                                                        components=[select],
                                                        confirmation_label=self.i18n['proceed'].capitalize(),
                                                        deny_label=self.i18n['cancel'].capitalize()):
                        raise Exception('aborted')
                    else:
                        return select.get_selected()

    @property
    def suggestions_url(self) -> str:
        if not self._suggestions_url:
            file_url = self.context.get_suggestion_url(self.__module__)

            if not file_url:
                file_url = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/snap/suggestions.txt'

            self._suggestions_url = file_url

            if file_url.startswith('/'):
                self.logger.info(f"Local Snap suggestions file mapped: {file_url}")

        return self._suggestions_url

    def is_local_suggestions_file_mapped(self) -> bool:
        return self.suggestions_url.startswith('/')
