import re
import time
import traceback
from threading import Thread
from typing import List, Set, Type, Optional, Tuple

from bauh.api.abstract.controller import SoftwareManager, SearchResult, ApplicationContext, UpgradeRequirements, \
    TransactionResult
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import SoftwarePackage, PackageHistory, PackageUpdate, PackageSuggestion, \
    SuggestionPriority, CustomSoftwareAction, PackageStatus
from bauh.api.abstract.view import SingleSelectComponent, SelectViewType, InputOption, ViewComponent, PanelComponent, \
    FormComponent
from bauh.api.exception import NoInternetException
from bauh.commons import resource, internet
from bauh.commons.category import CategoriesDownloader
from bauh.commons.config import save_config
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, ProcessHandler, new_root_subprocess, get_human_size_str
from bauh.commons.view_utils import new_select
from bauh.gems.snap import snap, URL_CATEGORIES_FILE, SNAP_CACHE_PATH, CATEGORIES_FILE_PATH, SUGGESTIONS_FILE, \
    get_icon_path, snapd, CONFIG_FILE
from bauh.gems.snap.config import read_config
from bauh.gems.snap.model import SnapApplication
from bauh.gems.snap.snapd import SnapdClient

RE_AVAILABLE_CHANNELS = re.compile(re.compile(r'(\w+)\s+(snap install.+)'))


class SnapManager(SoftwareManager):

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
        self.custom_actions = [
            CustomSoftwareAction(i18n_status_key='snap.action.refresh.status',
                                 i18n_label_key='snap.action.refresh.label',
                                 icon_path=resource.get_path('img/refresh.svg', context.get_view_path()),
                                 manager_method='refresh',
                                 requires_root=True,
                                 i18n_confirm_key='snap.action.refresh.confirm'),
            CustomSoftwareAction(i18n_status_key='snap.action.channel.status',
                                 i18n_label_key='snap.action.channel.label',
                                 i18n_confirm_key='snap.action.channel.confirm',
                                 icon_path=resource.get_path('img/refresh.svg', context.get_view_path()),
                                 manager_method='change_channel',
                                 requires_root=True)
        ]

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

    def downgrade(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        if not snap.is_installed():
            watcher.print("'snap' seems not to be installed")
            return False
        if not snapd.is_running():
            watcher.print("'snapd' seems not to be running")
            return False

        return ProcessHandler(watcher).handle_simple(snap.downgrade_and_stream(pkg.name, root_password))[0]

    def upgrade(self, requirements: UpgradeRequirements, root_password: str, watcher: ProcessWatcher) -> SystemProcess:
        raise Exception("'upgrade' is not supported by {}".format(SnapManager.__class__.__name__))

    def uninstall(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher, disk_loader: DiskCacheLoader) -> TransactionResult:
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
        raise Exception("'get_history' is not supported by {}".format(pkg.__class__.__name__))

    def install(self, pkg: SnapApplication, root_password: str, disk_loader: DiskCacheLoader, watcher: ProcessWatcher) -> TransactionResult:
        # retrieving all installed so it will be possible to know the additional installed runtimes after the operation succeeds
        if not snap.is_installed():
            watcher.print("'snap' seems not to be installed")
            return TransactionResult.fail()

        if not snapd.is_running():
            watcher.print("'snapd' seems not to be running")
            return TransactionResult.fail()

        installed_names = {s['name'] for s in SnapdClient(self.logger).list_all_snaps()}

        client = SnapdClient(self.logger)
        snap_config = read_config()

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
                    body = '<p>{}.</p>'.format(self.i18n['snap.install.available_channels.message'].format(bold(self.i18n['stable']), bold(pkg.name)))
                    body += '<p>{}:</p>'.format(self.i18n['snap.install.available_channels.help'])

                    if watcher.request_confirmation(title=self.i18n['snap.install.available_channels.title'],
                                                    body=body,
                                                    components=[channel_select],
                                                    confirmation_label=self.i18n['continue'],
                                                    deny_label=self.i18n['cancel']):
                        self.logger.info("Installing '{}' with the custom command '{}'".format(pkg.name, channel_select.value))
                        res = ProcessHandler(watcher).handle(SystemProcess(new_root_subprocess(channel_select.value.value.split(' '), root_password=root_password)))
                        return self._gen_installation_response(success=res, pkg=pkg,
                                                               installed=installed_names, disk_loader=disk_loader)
                else:
                    self.logger.error("Could not find available channels in the installation output: {}".format(output))

        return self._gen_installation_response(success=res, pkg=pkg, installed=installed_names, disk_loader=disk_loader)

    def _gen_installation_response(self, success: bool, pkg: SnapApplication, installed: Set[str], disk_loader: DiskCacheLoader):
        if success:
            new_installed = []
            try:
                current_installed = self.read_installed(disk_loader=disk_loader, internet_available=internet.is_available()).installed
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

    def can_work(self) -> bool:
        return snap.is_installed()

    def requires_root(self, action: str, pkg: SnapApplication):
        return action not in ('search', 'prepare')

    def refresh(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle_simple(snap.refresh_and_stream(pkg.name, root_password))[0]

    def change_channel(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        if not internet.is_available():
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

    def _start_category_task(self, task_man: TaskManager):
        if task_man:
            task_man.register_task('snap_cats', self.i18n['task.download_categories'].format('Snap'), get_icon_path())
            task_man.update_progress('snap_cats', 50, None)

    def _finish_category_task(self, task_man: TaskManager):
        if task_man:
            task_man.update_progress('snap_cats', 100, None)
            task_man.finish_task('snap_cats')

    def prepare(self, task_manager: TaskManager, root_password: str, internet_available: bool):
        Thread(target=read_config, args=(True,), daemon=True).start()

        CategoriesDownloader(id_='snap', manager=self, http_client=self.http_client, logger=self.logger,
                             url_categories_file=URL_CATEGORIES_FILE, disk_cache_dir=SNAP_CACHE_PATH,
                             categories_path=CATEGORIES_FILE_PATH,
                             before=lambda: self._start_category_task(task_manager),
                             after=lambda: self._finish_category_task(task_manager)).start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        pass

    def list_warnings(self, internet_available: bool) -> List[str]:
        if snap.is_installed():
            if not snapd.is_running():
                snap_bold = bold('Snap')
                return [self.i18n['snap.notification.snapd_unavailable'].format(bold('snapd'), snap_bold),
                        self.i18n['snap.notification.snap.disable'].format(snap_bold, bold('{} > {}'.format(self.i18n['settings'].capitalize(),
                                                                                                            self.i18n['core.config.tab.types'])))]

            elif internet_available:
                available, output = snap.is_api_available()

                if not available:
                    self.logger.warning('It seems Snap API is not available. Search output: {}'.format(output))
                    return [self.i18n['snap.notifications.api.unavailable'].format(bold('Snaps'), bold('Snap'))]

    def _fill_suggestion(self, name: str, priority: SuggestionPriority, snapd_client: SnapdClient, out: List[PackageSuggestion]):
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

        self.logger.warning("Could not retrieve suggestion '{}'".format(name))

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
                              installed_size=app_json.get('installed-size'),
                              extra_actions=self.custom_actions)

        if disk_loader and app.installed:
            disk_loader.fill(app)

        self._fill_categories(app)

        app.status = PackageStatus.READY
        return app

    def list_suggestions(self, limit: int, filter_installed: bool) -> List[PackageSuggestion]:
        res = []

        if snapd.is_running():
            self.logger.info('Downloading suggestions file {}'.format(SUGGESTIONS_FILE))
            file = self.http_client.get(SUGGESTIONS_FILE)

            if not file or not file.text:
                self.logger.warning("No suggestion found in {}".format(SUGGESTIONS_FILE))
                return res
            else:
                self.logger.info('Mapping suggestions')

                suggestions, threads = [], []
                snapd_client = SnapdClient(self.logger)
                installed = {s['name'].lower() for s in snapd_client.list_all_snaps()}

                for l in file.text.split('\n'):
                    if l:
                        if limit <= 0 or len(suggestions) < limit:
                            sug = l.strip().split('=')
                            name = sug[1]

                            if not installed or name not in installed:
                                cached_sug = self.suggestions_cache.get(name)

                                if cached_sug:
                                    res.append(cached_sug)
                                else:
                                    t = Thread(target=self._fill_suggestion, args=(name, SuggestionPriority(int(sug[0])), snapd_client, res))
                                    t.start()
                                    threads.append(t)
                                    time.sleep(0.001)  # to avoid being blocked
                        else:
                            break

                for t in threads:
                    t.join()

                res.sort(key=lambda s: s.priority.value, reverse=True)
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

            self.logger.info("Running '{}': {}".format(pkg.name, cmd))
            snap.run(cmd)

    def get_screenshots(self, pkg: SnapApplication) -> List[str]:
        return pkg.screenshots if pkg.has_screenshots() else []

    def get_settings(self, screen_width: int, screen_height: int) -> ViewComponent:
        snap_config = read_config()

        install_channel = new_select(label=self.i18n['snap.config.install_channel'],
                                     opts=[(self.i18n['yes'].capitalize(), True, None),
                                           (self.i18n['no'].capitalize(), False, None)],
                                     value=bool(snap_config['install_channel']),
                                     id_='install_channel',
                                     max_width=200,
                                     tip=self.i18n['snap.config.install_channel.tip'])

        return PanelComponent([FormComponent([install_channel], self.i18n['installation'].capitalize())])

    def save_settings(self, component: ViewComponent) -> Tuple[bool, Optional[List[str]]]:
        config = read_config()
        config['install_channel'] = component.components[0].components[0].get_selected()

        try:
            save_config(config, CONFIG_FILE)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def _request_channel_installation(self, pkg: SnapApplication, snap_config: Optional[dict], snapd_client: SnapdClient, watcher: ProcessWatcher, exclude_current: bool = False) -> Optional[str]:
        if snap_config is None or snap_config['install_channel']:
            try:
                data = [r for r in snapd_client.find_by_name(pkg.name) if r['name'] == pkg.name]
            except:
                self.logger.warning("snapd client could not retrieve channels for '{}'".format(pkg.name))
                return

            if not data:
                self.logger.warning("snapd client could find a match for name '{}' when retrieving its channels".format(pkg.name))
            else:
                if not data[0].get('channels'):
                    self.logger.info("No channel available for '{}'. Skipping selection.".format(pkg.name))
                else:
                    if pkg.channel:
                        current_channel = pkg.channel if '/' in pkg.channel else 'latest/{}'.format(pkg.channel)
                    else:
                        current_channel = 'latest/{}'.format(data[0].get('channel', 'stable'))

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
                        self.logger.info("No different channel available for '{}'. Skipping selection.".format(pkg.name))
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
