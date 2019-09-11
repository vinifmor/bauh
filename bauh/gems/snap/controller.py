from datetime import datetime
from typing import List, Set, Type

from bauh.api.abstract.controller import SoftwareManager, SearchResult, ApplicationContext
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageHistory, PackageUpdate, PackageSuggestion
from bauh.commons.system import SystemProcess, ProcessHandler

from bauh.gems.snap import snap, suggestions
from bauh.gems.snap.model import SnapApplication
from bauh.gems.snap.worker import SnapAsyncDataLoader


class SnapManager(SoftwareManager):

    def __init__(self, context: ApplicationContext):
        super(SnapManager, self).__init__(context=context)
        self.i18n = context.i18n
        self.api_cache = context.cache_factory.new()
        context.disk_loader_factory.map(SnapApplication, self.api_cache)

    def map_json(self, app_json: dict, installed: bool,  disk_loader: DiskCacheLoader) -> SnapApplication:
        app = SnapApplication(publisher=app_json.get('publisher'),
                              rev=app_json.get('rev'),
                              notes=app_json.get('notes'),
                              app_type=app_json.get('type'),
                              id=app_json.get('name'),
                              name=app_json.get('name'),
                              version=app_json.get('version'),
                              latest_version=app_json.get('version'),
                              description=app_json.get('description'))

        if app.publisher:
            app.publisher = app.publisher.replace('*', '')

        app.installed = installed

        api_data = self.api_cache.get(app_json['name'])
        expired_data = api_data and api_data.get('expires_at') and api_data['expires_at'] <= datetime.utcnow()

        if (not api_data or expired_data) and app.is_application():
            if disk_loader and app.installed:
                disk_loader.fill(app)

            SnapAsyncDataLoader(app=app, api_cache=self.api_cache, manager=self, context=self.context).start()
        else:
            app.fill_cached_data(api_data)

        return app

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1) -> SearchResult:
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

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None) -> SearchResult:
        installed = [self.map_json(app_json, installed=True, disk_loader=disk_loader) for app_json in snap.read_installed()]
        return SearchResult(installed, None, len(installed))

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
        return snap.is_installed()

    def requires_root(self, action: str, pkg: SnapApplication):
        return action != 'search'

    def refresh(self, pkg: SnapApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=snap.refresh_and_stream(pkg.name, root_password)))

    def prepare(self):
        pass

    def list_updates(self) -> List[PackageUpdate]:
        pass

    def list_warnings(self) -> List[str]:
        if snap.get_snapd_version() == 'unavailable':
            return [self.i18n['snap.notification.snapd_unavailable']]

    def list_suggestions(self, limit: int) -> List[PackageSuggestion]:
        res = []

        sugs = [(i, p) for i, p in suggestions.ALL.items()]
        sugs.sort(key=lambda t: t[1].value, reverse=True)

        for sug in sugs:

            if limit <= 0 or len(res) < limit:
                found = snap.search(sug[0], exact_name=True)
                if found:
                    res.append(PackageSuggestion(self.map_json(found[0], installed=False, disk_loader=None), sug[1]))
            else:
                break

        return res
