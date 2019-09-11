from datetime import datetime
from typing import List, Set, Type

from bauh.api.abstract.controller import SearchResult, SoftwareManager, ApplicationContext
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import PackageHistory, PackageUpdate, SoftwarePackage, PackageSuggestion
from bauh.api.abstract.view import MessageType
from bauh.commons.html import strip_html
from bauh.commons.system import SystemProcess, ProcessHandler

from bauh.gems.flatpak import flatpak, suggestions
from bauh.gems.flatpak.model import FlatpakApplication
from bauh.gems.flatpak.worker import FlatpakAsyncDataLoader, FlatpakUpdateLoader


class FlatpakManager(SoftwareManager):

    def __init__(self, context: ApplicationContext):
        super(FlatpakManager, self).__init__(context=context)
        self.i18n = context.i18n
        self.api_cache = context.cache_factory.new()
        context.disk_loader_factory.map(FlatpakApplication, self.api_cache)

    def get_managed_types(self) -> Set["type"]:
        return {FlatpakApplication}

    def _map_to_model(self, app_json: dict, installed: bool, disk_loader: DiskCacheLoader) -> FlatpakApplication:

        app = FlatpakApplication(arch=app_json.get('arch'),
                                 branch=app_json.get('branch'),
                                 origin=app_json.get('origin'),
                                 runtime=app_json.get('runtime'),
                                 ref=app_json.get('ref'),
                                 commit=app_json.get('commit'),
                                 id=app_json.get('id'),
                                 name=app_json.get('name'),
                                 version=app_json.get('version'),
                                 latest_version=app_json.get('latest_version'))

        app.installed = installed

        api_data = self.api_cache.get(app_json['id'])

        expired_data = api_data and api_data.get('expires_at') and api_data['expires_at'] <= datetime.utcnow()

        if not api_data or expired_data:
            if not app_json['runtime']:
                if disk_loader:
                    disk_loader.fill(app)  # preloading cached disk data
                FlatpakAsyncDataLoader(app=app, api_cache=self.api_cache, manager=self, context=self.context).start()

        else:
            app.fill_cached_data(api_data)

        return app

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1) -> SearchResult:

        res = SearchResult([], [], 0)
        apps_found = flatpak.search(words)

        if apps_found:
            already_read = set()
            installed_apps = self.read_installed(disk_loader=disk_loader).installed

            if installed_apps:
                for app_found in apps_found:
                    for installed_app in installed_apps:
                        if app_found['id'] == installed_app.id:
                            res.installed.append(installed_app)
                            already_read.add(app_found['id'])

            if len(apps_found) > len(already_read):
                for app_found in apps_found:
                    if app_found['id'] not in already_read:
                        res.new.append(self._map_to_model(app_found, False, disk_loader))

        res.total = len(res.installed) + len(res.new)
        return res

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None) -> SearchResult:
        installed = flatpak.list_installed()
        models = []

        if installed:

            available_updates = flatpak.list_updates_as_str()

            for app_json in installed:
                model = self._map_to_model(app_json=app_json, installed=True, disk_loader=disk_loader)
                model.update = app_json['id'] in available_updates
                models.append(model)

        return SearchResult(models, None, len(models))

    def downgrade(self, pkg: FlatpakApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        watcher.change_progress(10)
        watcher.change_substatus(self.i18n['flatpak.downgrade.commits'])
        commits = flatpak.get_app_commits(pkg.ref, pkg.origin)

        commit_idx = commits.index(pkg.commit)

        # downgrade is not possible if the app current commit in the first one:
        if commit_idx == len(commits) - 1:
            watcher.show_message(self.i18n['flatpak.downgrade.impossible.title'], self.i18n['flatpak.downgrade.impossible.body'], MessageType.WARNING)
            return False

        commit = commits[commit_idx + 1]
        watcher.change_substatus(self.i18n['flatpak.downgrade.reverting'])
        watcher.change_progress(50)
        success = ProcessHandler(watcher).handle(SystemProcess(subproc=flatpak.downgrade(pkg.ref, commit, root_password), success_phrase='Updates complete.'))
        watcher.change_progress(100)
        return success

    def clean_cache_for(self, pkg: FlatpakApplication):
        super(FlatpakManager, self).clean_cache_for(pkg)
        self.api_cache.delete(pkg.id)

    def update(self, pkg: FlatpakApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=flatpak.update(pkg.ref)))

    def uninstall(self, pkg: FlatpakApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=flatpak.uninstall(pkg.ref)))

    def get_info(self, app: FlatpakApplication) -> dict:
        app_info = flatpak.get_app_info_fields(app.id, app.branch)
        app_info['name'] = app.name
        app_info['type'] = 'runtime' if app.runtime else 'app'
        app_info['description'] = strip_html(app.description)
        return app_info

    def get_history(self, pkg: FlatpakApplication) -> PackageHistory:
        commits = flatpak.get_app_commits_data(pkg.ref, pkg.origin)
        status_idx = 0

        for idx, data in enumerate(commits):
            if data['commit'] == pkg.commit:
                status_idx = idx
                break

        return PackageHistory(pkg=pkg, history=commits, pkg_status_idx=status_idx)

    def install(self, pkg: FlatpakApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        return ProcessHandler(watcher).handle(SystemProcess(subproc=flatpak.install(pkg.id, pkg.origin)))

    def is_enabled(self):
        return flatpak.is_installed()

    def requires_root(self, action: str, pkg: FlatpakApplication):
        return action == 'downgrade'

    def prepare(self):
        pass

    def list_updates(self) -> List[PackageUpdate]:
        updates = []
        installed = flatpak.list_installed(extra_fields=False)

        if installed:
            available_updates = flatpak.list_updates_as_str()

            if available_updates:
                loaders = None

                for app_json in installed:
                    if app_json['id'] in available_updates:
                        loader = FlatpakUpdateLoader(app=app_json, http_client=self.context.http_client)
                        loader.start()

                        if loaders is None:
                            loaders = []

                        loaders.append(loader)

                if loaders:
                    for loader in loaders:
                        loader.join()
                        app = loader.app
                        updates.append(PackageUpdate(pkg_id='{}:{}'.format(app['id'], app['branch']),
                                                     pkg_type='flatpak',
                                                     version=app.get('version')))

        return updates

    def list_warnings(self) -> List[str]:
        if flatpak.is_installed():
            if not flatpak.has_remotes_set():
                return [self.i18n['flatpak.notification.no_remotes']]

    def list_suggestions(self, limit: int) -> List[PackageSuggestion]:

        res = []

        sugs = [(i, p) for i, p in suggestions.ALL.items()]
        sugs.sort(key=lambda t: t[1].value, reverse=True)

        for sug in sugs:

            if limit <= 0 or len(res) < limit:
                app_json = flatpak.search(sug[0], app_id=True)

                if app_json:
                    res.append(PackageSuggestion(self._map_to_model(app_json[0], False, None), sug[1]))
            else:
                break

        return res
