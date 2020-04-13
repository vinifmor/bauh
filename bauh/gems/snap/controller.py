import re
import time
from datetime import datetime
from threading import Thread
from typing import List, Set, Type

from bauh.api.abstract.controller import SoftwareManager, SearchResult, ApplicationContext, UpgradeRequirements
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import SoftwarePackage, PackageHistory, PackageUpdate, PackageSuggestion, \
    SuggestionPriority
from bauh.api.abstract.view import SingleSelectComponent, SelectViewType, InputOption
from bauh.commons.category import CategoriesDownloader
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, ProcessHandler, new_root_subprocess
from bauh.gems.snap import snap, URL_CATEGORIES_FILE, SNAP_CACHE_PATH, CATEGORIES_FILE_PATH, SUGGESTIONS_FILE, \
    get_icon_path
from bauh.gems.snap.constants import SNAP_API_URL
from bauh.gems.snap.model import SnapApplication
from bauh.gems.snap.worker import SnapAsyncDataLoader

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

    def get_info_path(self) -> str:
        if self.info_path is None:
            self.info_path = snap.get_app_info_path()

        return self.info_path

    def map_json(self, app_json: dict, installed: bool,  disk_loader: DiskCacheLoader, internet: bool = True) -> SnapApplication:
        app = SnapApplication(publisher=app_json.get('publisher'),
                              rev=app_json.get('rev'),
                              notes=app_json.get('notes'),
                              has_apps_field=app_json.get('apps_field', False),
                              id=app_json.get('name'),
                              name=app_json.get('name'),
                              version=app_json.get('version'),
                              latest_version=app_json.get('version'),
                              description=app_json.get('description', app_json.get('summary')),
                              verified_publisher=app_json.get('developer_validation', '') == 'verified')

        if app.publisher and app.publisher.endswith('*'):
            app.verified_publisher = True
            app.publisher = app.publisher.replace('*', '')

        categories = self.categories.get(app.name.lower())

        if categories:
            app.categories = categories

        app.installed = installed

        if not app.is_application():
            categories = app.categories

            if categories is None:
                categories = []
                app.categories = categories

            if 'runtime' not in categories:
                categories.append('runtime')

        api_data = self.api_cache.get(app_json['name'])
        expired_data = api_data and api_data.get('expires_at') and api_data['expires_at'] <= datetime.utcnow()

        if (not api_data or expired_data) and app.is_application():
            if disk_loader and app.installed:
                disk_loader.fill(app)

            if internet:
                SnapAsyncDataLoader(app=app, api_cache=self.api_cache, manager=self, context=self.context).start()
        else:
            app.fill_cached_data(api_data)

        return app

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        if is_url:
            return SearchResult([], [], 0)

        if snap.is_snapd_running():
            installed = self.read_installed(disk_loader).installed

            res = SearchResult([], [], 0)

            for app_json in snap.search(words):

                already_installed = None

                if installed:
                    already_installed = [i for i in installed if i.id == app_json.get('name')]
                    already_installed = already_installed[0] if already_installed else None

                if already_installed:
                    res.installed.append(already_installed)
                else:
                    res.new.append(self.map_json(app_json, installed=False, disk_loader=disk_loader))

            res.total = len(res.installed) + len(res.new)
            return res
        else:
            return SearchResult([], [], 0)

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None) -> SearchResult:
        info_path = self.get_info_path()

        if snap.is_snapd_running() and info_path:
            installed = [self.map_json(app_json, installed=True, disk_loader=disk_loader, internet=internet_available) for app_json in snap.read_installed(info_path)]
            return SearchResult(installed, None, len(installed))
        else:
            return SearchResult([], None, 0)

    def downgrade(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=snap.downgrade_and_stream(pkg.name, root_password), wrong_error_phrase=None))

    def upgrade(self, requirements: UpgradeRequirements, root_password: str, watcher: ProcessWatcher) -> SystemProcess:
        raise Exception("'update' is not supported by {}".format(pkg.__class__.__name__))

    def uninstall(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        uninstalled = ProcessHandler(watcher).handle(SystemProcess(subproc=snap.uninstall_and_stream(pkg.name, root_password)))

        if self.suggestions_cache:
            self.suggestions_cache.delete(pkg.name)

        return uninstalled

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        return {SnapApplication}

    def clean_cache_for(self, pkg: SnapApplication):
        super(SnapManager, self).clean_cache_for(pkg)
        self.api_cache.delete(pkg.id)

    def get_info(self, pkg: SnapApplication) -> dict:
        info = snap.get_info(pkg.name, attrs=('license', 'contact', 'commands', 'snap-id', 'tracking', 'installed'))
        info['description'] = pkg.description
        info['publisher'] = pkg.publisher
        info['revision'] = pkg.rev
        info['name'] = pkg.name

        if info.get('commands'):
            info['commands'] = ' '.join(info['commands'])

        if info.get('license') and info['license'] == 'unset':
            del info['license']

        return info

    def get_history(self, pkg: SnapApplication) -> PackageHistory:
        raise Exception("'get_history' is not supported by {}".format(pkg.__class__.__name__))

    def install(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        info_path = self.get_info_path()

        if not info_path:
            self.logger.warning('Information directory was not found. It will not be possible to determine if the installed application can be launched')

        res, output = ProcessHandler(watcher).handle_simple(snap.install_and_stream(pkg.name, pkg.confinement, root_password))

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

                        if res and info_path:
                            pkg.has_apps_field = snap.has_apps_field(pkg.name, info_path)

                        return res
                else:
                    self.logger.error("Could not find available channels in the installation output: {}".format(output))
        else:
            if info_path:
                pkg.has_apps_field = snap.has_apps_field(pkg.name, info_path)

        return res

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> bool:
        return snap.is_installed()

    def requires_root(self, action: str, pkg: SnapApplication):
        return action not in ('search', 'prepare')

    def refresh(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=snap.refresh_and_stream(pkg.name, root_password)))

    def _start_category_task(self, task_man: TaskManager):
        task_man.register_task('snap_cats', self.i18n['task.download_categories'].format('Snap'), get_icon_path())
        task_man.update_progress('snap_cats', 50, None)

    def _finish_category_task(self, task_man: TaskManager):
        task_man.update_progress('snap_cats', 100, None)
        task_man.finish_task('snap_cats')

    def prepare(self, task_manager: TaskManager, root_password: str, internet_available: bool):
        CategoriesDownloader(id_='snap', manager=self, http_client=self.http_client, logger=self.logger,
                             url_categories_file=URL_CATEGORIES_FILE, disk_cache_dir=SNAP_CACHE_PATH,
                             categories_path=CATEGORIES_FILE_PATH,
                             before=lambda: self._start_category_task(task_manager),
                             after=lambda: self._finish_category_task(task_manager)).start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        pass

    def list_warnings(self, internet_available: bool) -> List[str]:
        if snap.is_installed():
            if not snap.is_snapd_running():
                snap_bold = bold('Snap')
                return [self.i18n['snap.notification.snapd_unavailable'].format(bold('snapd'), snap_bold),
                        self.i18n['snap.notification.snap.disable'].format(snap_bold, bold('{} > {}'.format(self.i18n['settings'].capitalize(),
                                                                                                            self.i18n['core.config.tab.types'])))]

            elif internet_available:
                available, output = snap.is_api_available()

                if not available:
                    self.logger.warning('It seems Snap API is not available. Search output: {}'.format(output))
                    return [self.i18n['snap.notifications.api.unavailable'].format(bold('Snaps'), bold('Snap'))]

    def _fill_suggestion(self, pkg_name: str, priority: SuggestionPriority, out: List[PackageSuggestion]):
        res = self.http_client.get_json(SNAP_API_URL + '/search?q=package_name:{}'.format(pkg_name))

        if res and res['_embedded']['clickindex:package']:
            pkg = res['_embedded']['clickindex:package'][0]
            pkg['rev'] = pkg['revision']
            pkg['name'] = pkg_name

            sug = PackageSuggestion(self.map_json(pkg, installed=False, disk_loader=None), priority)
            self.suggestions_cache.add(pkg_name, sug)
            out.append(sug)
        else:
            self.logger.warning("Could not retrieve suggestion '{}'".format(pkg_name))

    def list_suggestions(self, limit: int, filter_installed: bool) -> List[PackageSuggestion]:
        res = []

        if snap.is_snapd_running():
            self.logger.info('Downloading suggestions file {}'.format(SUGGESTIONS_FILE))
            file = self.http_client.get(SUGGESTIONS_FILE)

            if not file or not file.text:
                self.logger.warning("No suggestion found in {}".format(SUGGESTIONS_FILE))
                return res
            else:
                self.logger.info('Mapping suggestions')

                suggestions, threads = [], []
                installed = {i.name.lower() for i in self.read_installed(disk_loader=None).installed} if filter_installed else None

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
                                    t = Thread(target=self._fill_suggestion, args=(name, SuggestionPriority(int(sug[0])), res))
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
        snap.run(pkg, self.context.logger)

    def get_screenshots(self, pkg: SoftwarePackage) -> List[str]:
        res = self.http_client.get_json('{}/search?q={}'.format(SNAP_API_URL, pkg.name))

        if res:
            if res.get('_embedded') and res['_embedded'].get('clickindex:package'):
                snap_data = res['_embedded']['clickindex:package'][0]

                if snap_data.get('screenshot_urls'):
                    return snap_data['screenshot_urls']
                else:
                    self.logger.warning("No 'screenshots_urls' defined for {}".format(pkg))
            else:
                self.logger.error('It seems the API is returning a different response: {}'.format(res))
        else:
            self.logger.warning('Could not retrieve data for {}'.format(pkg))

        return []
