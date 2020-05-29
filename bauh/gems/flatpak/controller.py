import os
import traceback
from datetime import datetime
from math import floor
from pathlib import Path
from threading import Thread
from typing import List, Set, Type, Tuple

from bauh.api.abstract.controller import SearchResult, SoftwareManager, ApplicationContext, UpgradeRequirements, \
    UpgradeRequirement
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import PackageHistory, PackageUpdate, SoftwarePackage, PackageSuggestion, \
    SuggestionPriority, PackageStatus
from bauh.api.abstract.view import MessageType, FormComponent, SingleSelectComponent, InputOption, SelectViewType, \
    ViewComponent, PanelComponent
from bauh.commons import user
from bauh.commons.config import save_config
from bauh.commons.html import strip_html, bold
from bauh.commons.system import SystemProcess, ProcessHandler
from bauh.gems.flatpak import flatpak, SUGGESTIONS_FILE, CONFIG_FILE, UPDATES_IGNORED_FILE, CONFIG_DIR
from bauh.gems.flatpak.config import read_config
from bauh.gems.flatpak.constants import FLATHUB_API_URL
from bauh.gems.flatpak.model import FlatpakApplication
from bauh.gems.flatpak.worker import FlatpakAsyncDataLoader, FlatpakUpdateLoader

DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.000Z'


class FlatpakManager(SoftwareManager):

    def __init__(self, context: ApplicationContext):
        super(FlatpakManager, self).__init__(context=context)
        self.i18n = context.i18n
        self.api_cache = context.cache_factory.new()
        self.category_cache = context.cache_factory.new()
        context.disk_loader_factory.map(FlatpakApplication, self.api_cache)
        self.enabled = True
        self.http_client = context.http_client
        self.suggestions_cache = context.cache_factory.new()
        self.logger = context.logger

    def get_managed_types(self) -> Set["type"]:
        return {FlatpakApplication}

    def _map_to_model(self, app_json: dict, installed: bool, disk_loader: DiskCacheLoader, internet: bool = True) -> FlatpakApplication:

        app = FlatpakApplication(**app_json, i18n=self.i18n)
        app.installed = installed
        api_data = self.api_cache.get(app_json['id'])

        expired_data = api_data and api_data.get('expires_at') and api_data['expires_at'] <= datetime.utcnow()

        if not api_data or expired_data:
            if not app.runtime:
                if disk_loader:
                    disk_loader.fill(app)  # preloading cached disk data

                if internet:
                    FlatpakAsyncDataLoader(app=app, api_cache=self.api_cache, manager=self,
                                           context=self.context, category_cache=self.category_cache).start()

        else:
            app.fill_cached_data(api_data)
            app.status = PackageStatus.READY

        return app

    def _get_search_remote(self) -> str:
        remotes = flatpak.list_remotes()

        if remotes['system']:
            remote_level = 'system'
        elif remotes['user']:
            remote_level = 'user'
        else:
            remote_level = 'user'
            ProcessHandler().handle_simple(flatpak.set_default_remotes(remote_level))

        return remote_level

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        if is_url:
            return SearchResult([], [], 0)

        remote_level = self._get_search_remote()

        res = SearchResult([], [], 0)
        apps_found = flatpak.search(flatpak.get_version(), words, remote_level)

        if apps_found:
            already_read = set()
            installed_apps = self.read_installed(disk_loader=disk_loader, internet_available=True).installed

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

    def _add_updates(self, version: str, output: list):
        output.append(flatpak.list_updates_as_str(version))

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None) -> SearchResult:
        version = flatpak.get_version()

        updates = []

        if internet_available:
            thread_updates = Thread(target=self._add_updates, args=(version, updates))
            thread_updates.start()
        else:
            thread_updates = None

        installed = flatpak.list_installed(version)
        models = []

        if installed:
            update_map = None
            if thread_updates:
                thread_updates.join()
                update_map = updates[0]

            for app_json in installed:
                model = self._map_to_model(app_json=app_json, installed=True,
                                           disk_loader=disk_loader, internet=internet_available)
                model.update = None
                models.append(model)

                if update_map and (update_map['full'] or update_map['partial']):
                    if version >= '1.4.0':
                        update_id = '{}/{}/{}'.format(app_json['id'], app_json['branch'], app_json['installation'])

                        if update_map['full'] and update_id in update_map['full']:
                            model.update = True

                        if update_map['partial']:
                            for partial in update_map['partial']:
                                partial_data = partial.split('/')
                                if app_json['id'] in partial_data[0] and\
                                        app_json['branch'] == partial_data[1] and\
                                        app_json['installation'] == partial_data[2]:
                                    partial_model = model.gen_partial(partial.split('/')[0])
                                    partial_model.update = True
                                    models.append(partial_model)
                    else:
                        model.update = '{}/{}'.format(app_json['installation'], app_json['ref']) in update_map['full']

        if models:
            ignored = self._read_ignored_updates()

            if ignored:
                for model in models:
                    if model.get_update_ignore_key() in ignored:
                        model.updates_ignored = True

        return SearchResult(models, None, len(models))

    def downgrade(self, pkg: FlatpakApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        handler = ProcessHandler(watcher)
        pkg.commit = flatpak.get_commit(pkg.id, pkg.branch, pkg.installation)

        watcher.change_progress(10)
        watcher.change_substatus(self.i18n['flatpak.downgrade.commits'])
        commits = flatpak.get_app_commits(pkg.ref, pkg.origin, pkg.installation, handler)

        if commits is None:
            return False

        commit_idx = commits.index(pkg.commit)

        # downgrade is not possible if the app current commit in the first one:
        if commit_idx == len(commits) - 1:
            watcher.show_message(self.i18n['flatpak.downgrade.impossible.title'], self.i18n['flatpak.downgrade.impossible.body'], MessageType.WARNING)
            return False

        commit = commits[commit_idx + 1]
        watcher.change_substatus(self.i18n['flatpak.downgrade.reverting'])
        watcher.change_progress(50)
        success = handler.handle(SystemProcess(subproc=flatpak.downgrade(pkg.ref, commit, pkg.installation, root_password),
                                               success_phrases=['Changes complete.', 'Updates complete.'],
                                               wrong_error_phrase='Warning'))
        watcher.change_progress(100)
        return success

    def clean_cache_for(self, pkg: FlatpakApplication):
        super(FlatpakManager, self).clean_cache_for(pkg)
        self.api_cache.delete(pkg.id)

    def upgrade(self, requirements: UpgradeRequirements, root_password: str, watcher: ProcessWatcher) -> bool:
        flatpak_version = flatpak.get_version()
        for req in requirements.to_upgrade:
            watcher.change_status("{} {} ({})...".format(self.i18n['manage_window.status.upgrading'], req.pkg.name, req.pkg.version))
            related, deps = False, False
            ref = req.pkg.ref

            if req.pkg.partial and flatpak_version < '1.5':
                related, deps = True, True
                ref = req.pkg.base_ref

            try:
                res = ProcessHandler(watcher).handle(SystemProcess(subproc=flatpak.update(app_ref=ref,
                                                                                          installation=req.pkg.installation,
                                                                                          related=related,
                                                                                          deps=deps)))

                watcher.change_substatus('')
                if not res:
                    self.logger.warning("Could not upgrade '{}'".format(req.pkg.id))
                    return False
            except:
                watcher.change_substatus('')
                self.logger.error("An error occurred while upgrading '{}'".format(req.pkg.id))
                traceback.print_exc()
                return False

        watcher.change_substatus('')
        return True

    def uninstall(self, pkg: FlatpakApplication, root_password: str, watcher: ProcessWatcher) -> bool:
        uninstalled = ProcessHandler(watcher).handle(SystemProcess(subproc=flatpak.uninstall(pkg.ref, pkg.installation)))

        if self.suggestions_cache:
            self.suggestions_cache.delete(pkg.id)

        self.revert_ignored_update(pkg)

        return uninstalled

    def get_info(self, app: FlatpakApplication) -> dict:
        if app.installed:
            version = flatpak.get_version()
            id_ = app.base_id if app.partial and version < '1.5' else app.id
            app_info = flatpak.get_app_info_fields(id_, app.branch, app.installation)

            if app.partial and version < '1.5':
                app_info['id'] = app.id
                app_info['ref'] = app.ref

            app_info['name'] = app.name
            app_info['type'] = 'runtime' if app.runtime else 'app'
            app_info['description'] = strip_html(app.description) if app.description else ''

            if app.installation:
                app_info['installation'] = app.installation

            if app_info.get('installed'):
                app_info['installed'] = app_info['installed'].replace('?', ' ')

            return app_info
        else:
            res = self.http_client.get_json('{}/apps/{}'.format(FLATHUB_API_URL, app.id))

            if res:
                if res.get('categories'):
                    res['categories'] = [c.get('name') for c in res['categories']]

                for to_del in ('screenshots', 'iconMobileUrl', 'iconDesktopUrl'):
                    if res.get(to_del):
                        del res[to_del]

                for to_strip in ('description', 'currentReleaseDescription'):
                    if res.get(to_strip):
                        res[to_strip] = strip_html(res[to_strip])

                for to_date in ('currentReleaseDate', 'inStoreSinceDate'):
                    if res.get(to_date):
                        try:
                            res[to_date] = datetime.strptime(res[to_date], DATE_FORMAT)
                        except:
                            self.context.logger.error('Could not convert date string {} as {}'.format(res[to_date], DATE_FORMAT))
                            pass

                return res
            else:
                return {}

    def get_history(self, pkg: FlatpakApplication) -> PackageHistory:
        pkg.commit = flatpak.get_commit(pkg.id, pkg.branch, pkg.installation)
        commits = flatpak.get_app_commits_data(pkg.ref, pkg.origin, pkg.installation)
        status_idx = 0

        for idx, data in enumerate(commits):
            if data['commit'] == pkg.commit:
                status_idx = idx
                break

        return PackageHistory(pkg=pkg, history=commits, pkg_status_idx=status_idx)

    def install(self, pkg: FlatpakApplication, root_password: str, watcher: ProcessWatcher) -> bool:

        config = read_config()

        install_level = config['installation_level']

        if install_level is not None:
            self.logger.info("Default Flaptak installation level defined: {}".format(install_level))

            if install_level not in ('user', 'system'):
                watcher.show_message(title=self.i18n['error'].capitalize(),
                                     body=self.i18n['flatpak.install.bad_install_level.body'].format(field=bold('installation_level'),
                                                                                                     file=bold(CONFIG_FILE)),
                                     type_=MessageType.ERROR)
                return False

            pkg.installation = install_level
        else:
            user_level = watcher.request_confirmation(title=self.i18n['flatpak.install.install_level.title'],
                                                      body=self.i18n['flatpak.install.install_level.body'].format(bold(pkg.name)),
                                                      confirmation_label=self.i18n['no'].capitalize(),
                                                      deny_label=self.i18n['yes'].capitalize())
            pkg.installation = 'user' if user_level else 'system'

        remotes = flatpak.list_remotes()

        handler = ProcessHandler(watcher)

        if pkg.installation == 'user' and not remotes['user']:
            handler.handle_simple(flatpak.set_default_remotes('user'))
        elif pkg.installation == 'system' and not remotes['system']:
            if user.is_root():
                handler.handle_simple(flatpak.set_default_remotes('system'))
            else:
                user_password, valid = watcher.request_root_password()
                if not valid:
                    watcher.print('Operation aborted')
                    return False
                else:
                    if not handler.handle_simple(flatpak.set_default_remotes('system', user_password)):
                        watcher.show_message(title=self.i18n['error'].capitalize(),
                                             body=self.i18n['flatpak.remotes.system_flathub.error'],
                                             type_=MessageType.ERROR)
                        watcher.print("Operation cancelled")
                        return False

        res = handler.handle(SystemProcess(subproc=flatpak.install(str(pkg.id), pkg.origin, pkg.installation), wrong_error_phrase='Warning'))

        if res:
            try:
                fields = flatpak.get_fields(str(pkg.id), pkg.branch, ['Ref', 'Branch'])

                if fields:
                    pkg.ref = fields[0]
                    pkg.branch = fields[1]
            except:
                traceback.print_exc()

        return res

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> bool:
        return flatpak.is_installed()

    def requires_root(self, action: str, pkg: FlatpakApplication):
        return action == 'downgrade' and pkg.installation == 'system'

    def prepare(self, task_manager: TaskManager, root_password: str, internet_available: bool):
        Thread(target=read_config, args=(True,), daemon=True).start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        updates = []
        installed = self.read_installed(None, internet_available=internet_available).installed

        to_update = [p for p in installed if p.update and not p.is_update_ignored()]

        if to_update:
            loaders = []

            for app in to_update:
                if app.is_application():
                    loader = FlatpakUpdateLoader(app=app, http_client=self.context.http_client)
                    loader.start()
                    loaders.append(loader)

            for loader in loaders:
                loader.join()

            for app in to_update:
                updates.append(PackageUpdate(pkg_id='{}:{}:{}'.format(app.id, app.branch, app.installation),
                                             pkg_type='Flatpak',
                                             name=app.name,
                                             version=app.version))

        return updates

    def list_warnings(self, internet_available: bool) -> List[str]:
        return []

    def list_suggestions(self, limit: int, filter_installed: bool) -> List[PackageSuggestion]:
        cli_version = flatpak.get_version()
        res = []

        self.logger.info("Downloading the suggestions file {}".format(SUGGESTIONS_FILE))
        file = self.http_client.get(SUGGESTIONS_FILE)

        if not file or not file.text:
            self.logger.warning("No suggestion found in {}".format(SUGGESTIONS_FILE))
            return res
        else:
            self.logger.info("Mapping suggestions")
            remote_level = self._get_search_remote()
            installed = {i.id for i in self.read_installed(disk_loader=None).installed} if filter_installed else None

            for line in file.text.split('\n'):
                if line:
                    if limit <= 0 or len(res) < limit:
                        sug = line.split('=')
                        appid = sug[1].strip()

                        if installed and appid in installed:
                            continue

                        priority = SuggestionPriority(int(sug[0]))

                        cached_sug = self.suggestions_cache.get(appid)

                        if cached_sug:
                            res.append(cached_sug)
                        else:
                            app_json = flatpak.search(cli_version, appid, remote_level, app_id=True)

                            if app_json:
                                model = PackageSuggestion(self._map_to_model(app_json[0], False, None), priority)
                                self.suggestions_cache.add(appid, model)
                                res.append(model)
                    else:
                        break

            res.sort(key=lambda s: s.priority.value, reverse=True)
        return res

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: FlatpakApplication):
        flatpak.run(str(pkg.id))

    def get_screenshots(self, pkg: SoftwarePackage) -> List[str]:
        screenshots_url = '{}/apps/{}'.format(FLATHUB_API_URL, pkg.id)
        urls = []
        try:
            res = self.http_client.get_json(screenshots_url)

            if res and res.get('screenshots'):
                for s in res['screenshots']:
                    if s.get('imgDesktopUrl'):
                        urls.append(s['imgDesktopUrl'])

        except Exception as e:
            if e.__class__.__name__ == 'JSONDecodeError':
                self.context.logger.error("Could not decode json from '{}'".format(screenshots_url))
            else:
                traceback.print_exc()

        return urls

    def get_settings(self, screen_width: int, screen_height: int) -> ViewComponent:
        fields = []

        config = read_config()

        install_opts = [InputOption(label=self.i18n['flatpak.config.install_level.system'].capitalize(),
                                    value='system',
                                    tooltip=self.i18n['flatpak.config.install_level.system.tip']),
                        InputOption(label=self.i18n['flatpak.config.install_level.user'].capitalize(),
                                    value='user',
                                    tooltip=self.i18n['flatpak.config.install_level.user.tip']),
                        InputOption(label=self.i18n['ask'].capitalize(),
                                    value=None,
                                    tooltip=self.i18n['flatpak.config.install_level.ask.tip'].format(app=self.context.app_name))]
        fields.append(SingleSelectComponent(label=self.i18n['flatpak.config.install_level'],
                                            options=install_opts,
                                            default_option=[o for o in install_opts if o.value == config['installation_level']][0],
                                            max_per_line=len(install_opts),
                                            max_width=floor(screen_width * 0.22),
                                            type_=SelectViewType.RADIO))

        return PanelComponent([FormComponent(fields, self.i18n['installation'].capitalize())])

    def save_settings(self, component: PanelComponent) -> Tuple[bool, List[str]]:
        config = read_config()
        config['installation_level'] = component.components[0].components[0].get_selected()

        try:
            save_config(config, CONFIG_FILE)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def get_upgrade_requirements(self, pkgs: List[FlatpakApplication], root_password: str, watcher: ProcessWatcher) -> UpgradeRequirements:
        flatpak_version = flatpak.get_version()

        user_pkgs, system_pkgs = [], []

        for pkg in pkgs:
            if pkg.installation == 'user':
                user_pkgs.append(pkg)
            else:
                system_pkgs.append(pkg)

        for apps_by_install in ((user_pkgs, 'user'), (system_pkgs, 'system')):
            if apps_by_install[0]:
                sizes = flatpak.map_update_download_size([str(p.id) for p in apps_by_install[0]], apps_by_install[1], flatpak_version)

                if sizes:
                    for p in apps_by_install[0]:
                        p.size = sizes.get(str(p.id))

        to_update = [UpgradeRequirement(pkg=p, extra_size=p.size, required_size=p.size) for p in self.sort_update_order(pkgs)]
        return UpgradeRequirements(None, None, to_update, [])

    def sort_update_order(self, pkgs: List[FlatpakApplication]) -> List[FlatpakApplication]:
        partials, runtimes, apps = [], [], []

        for p in pkgs:
            if p.runtime:
                if p.partial:
                    partials.append(p)
                else:
                    runtimes.append(p)
            else:
                apps.append(p)

        if not runtimes:
            return [*partials, *apps]
        elif partials:
            all_runtimes = []
            for runtime in runtimes:
                for partial in partials:
                    if partial.base_id == runtime.id:
                        all_runtimes.append(partial)

                all_runtimes.append(runtime)
            return [*all_runtimes, *apps]
        else:
            return [*runtimes, *apps]

    def _read_ignored_updates(self) -> Set[str]:
        ignored = set()
        if os.path.exists(UPDATES_IGNORED_FILE):
            with open(UPDATES_IGNORED_FILE) as f:
                ignored_txt = f.read()

            for l in ignored_txt.split('\n'):
                if l:
                    line_clean = l.strip()

                    if line_clean:
                        ignored.add(line_clean)

        return ignored

    def _write_ignored_updates(self, keys: Set[str]):
        Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        ignored_list = [*keys]
        ignored_list.sort()

        with open(UPDATES_IGNORED_FILE, 'w+') as f:
            if ignored_list:
                for ignored in ignored_list:
                    f.write('{}\n'.format(ignored))
            else:
                f.write('')

    def ignore_update(self, pkg: FlatpakApplication):
        ignored_keys = self._read_ignored_updates()

        pkg_key = pkg.get_update_ignore_key()

        if pkg_key not in ignored_keys:
            ignored_keys.add(pkg_key)
            self._write_ignored_updates(ignored_keys)

        pkg.updates_ignored = True

    def revert_ignored_update(self, pkg: FlatpakApplication):
        ignored_keys = self._read_ignored_updates()

        if ignored_keys:
            pkg_key = pkg.get_update_ignore_key()

            if pkg_key in ignored_keys:
                ignored_keys.remove(pkg_key)
                self._write_ignored_updates(ignored_keys)

        pkg.updates_ignored = False
