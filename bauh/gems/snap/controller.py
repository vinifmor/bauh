import time
from datetime import datetime
from threading import Thread
from typing import List, Set, Type

from bauh.api.abstract.controller import SoftwareManager, SearchResult, ApplicationContext
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageHistory, PackageUpdate, PackageSuggestion, \
    SuggestionPriority
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, ProcessHandler
from bauh.gems.snap import snap, suggestions
from bauh.gems.snap.constants import SNAP_API_URL
from bauh.gems.snap.model import SnapApplication
from bauh.gems.snap.worker import SnapAsyncDataLoader


class SnapManager(SoftwareManager):

    def __init__(self, context: ApplicationContext):
        super(SnapManager, self).__init__(context=context)
        self.i18n = context.i18n
        self.api_cache = context.cache_factory.new()
        context.disk_loader_factory.map(SnapApplication, self.api_cache)
        self.enabled = True
        self.http_client = context.http_client
        self.logger = context.logger

    def map_json(self, app_json: dict, installed: bool,  disk_loader: DiskCacheLoader, internet: bool = True) -> SnapApplication:
        app = SnapApplication(publisher=app_json.get('publisher'),
                              rev=app_json.get('rev'),
                              notes=app_json.get('notes'),
                              app_type=app_json.get('type'),
                              id=app_json.get('name'),
                              name=app_json.get('name'),
                              version=app_json.get('version'),
                              latest_version=app_json.get('version'),
                              description=app_json.get('description', app_json.get('summary')))

        if app.publisher:
            app.publisher = app.publisher.replace('*', '')

        app.installed = installed

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

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1) -> SearchResult:
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
        if snap.is_snapd_running():
            installed = [self.map_json(app_json, installed=True, disk_loader=disk_loader, internet=internet_available) for app_json in snap.read_installed()]
            return SearchResult(installed, None, len(installed))
        else:
            return SearchResult([], None, 0)

    def downgrade(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=snap.downgrade_and_stream(pkg.name, root_password), wrong_error_phrase=None))

    def update(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> SystemProcess:
        raise Exception("'update' is not supported by {}".format(pkg.__class__.__name__))

    def uninstall(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=snap.uninstall_and_stream(pkg.name, root_password)))

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

        return info

    def get_history(self, pkg: SnapApplication) -> PackageHistory:
        raise Exception("'get_history' is not supported by {}".format(pkg.__class__.__name__))

    def install(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=snap.install_and_stream(pkg.name, pkg.confinement, root_password)))

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> bool:
        return snap.is_installed()

    def requires_root(self, action: str, pkg: SnapApplication):
        return action != 'search'

    def refresh(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=snap.refresh_and_stream(pkg.name, root_password)))

    def prepare(self):
        pass

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        pass

    def list_warnings(self) -> List[str]:
        if snap.is_installed() and not snap.is_snapd_running():
            snap_bold = bold('Snap')
            return [self.i18n['snap.notification.snapd_unavailable'].format(bold('snapd'), snap_bold),
                    self.i18n['snap.notification.snap.disable'].format(snap_bold, bold(self.i18n['manage_window.settings.gems']))]

    def _fill_suggestion(self, pkg_name: str, priority: SuggestionPriority, out: List[PackageSuggestion]):
        res = self.http_client.get_json(SNAP_API_URL + '/search?q=package_name:{}'.format(pkg_name))

        if res and res['_embedded']['clickindex:package']:
            pkg = res['_embedded']['clickindex:package'][0]
            pkg['rev'] = pkg['revision']
            pkg['name'] = pkg_name

            out.append(PackageSuggestion(self.map_json(pkg, installed=False, disk_loader=None), priority))
        else:
            self.logger.warning("Could not retrieve suggestion '{}'".format(pkg_name))

    def list_suggestions(self, limit: int) -> List[PackageSuggestion]:
        res = []

        if snap.is_snapd_running():
            sugs = [(i, p) for i, p in suggestions.ALL.items()]
            sugs.sort(key=lambda t: t[1].value, reverse=True)

            threads = []
            for sug in sugs:

                if limit <= 0 or len(res) < limit:
                    t = Thread(target=self._fill_suggestion, args=(sug[0], sug[1], res))
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
