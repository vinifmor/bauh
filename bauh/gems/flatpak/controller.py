import os
import re
import traceback
from datetime import datetime
from operator import attrgetter
from pathlib import Path
from threading import Thread
from typing import List, Set, Type, Tuple, Optional, Generator, Dict

from packaging.version import Version

from bauh.api import user
from bauh.api.abstract.controller import SearchResult, SoftwareManager, ApplicationContext, UpgradeRequirements, \
    UpgradeRequirement, TransactionResult, SoftwareAction, SettingsView, SettingsController
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import PackageHistory, PackageUpdate, SoftwarePackage, PackageSuggestion, \
    PackageStatus, CustomSoftwareAction, SuggestionPriority
from bauh.api.abstract.view import MessageType, FormComponent, SingleSelectComponent, InputOption, SelectViewType, \
    PanelComponent, ViewComponentAlignment
from bauh.commons import suggestions
from bauh.commons.boot import CreateConfigFile
from bauh.commons.html import strip_html, bold
from bauh.commons.system import ProcessHandler
from bauh.gems.flatpak import flatpak, CONFIG_FILE, UPDATES_IGNORED_FILE, FLATPAK_CONFIG_DIR, \
    EXPORTS_PATH, \
    get_icon_path, VERSION_1_5, VERSION_1_2, VERSION_1_12
from bauh.gems.flatpak.config import FlatpakConfigManager
from bauh.gems.flatpak.constants import FLATHUB_API_URL
from bauh.gems.flatpak.model import FlatpakApplication
from bauh.gems.flatpak.worker import FlatpakAsyncDataLoader

DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.000Z'
RE_INSTALL_REFS = re.compile(r'\d+\)\s+(.+)')


class FlatpakManager(SoftwareManager, SettingsController):

    def __init__(self, context: ApplicationContext):
        super(FlatpakManager, self).__init__(context=context)
        self.i18n = context.i18n
        self.api_cache = context.cache_factory.new(None)
        self.category_cache = context.cache_factory.new(None)
        context.disk_loader_factory.map(FlatpakApplication, self.api_cache)
        self.enabled = True
        self.http_client = context.http_client
        self.suggestions_cache = context.cache_factory.new(None)
        self.logger = context.logger
        self.configman = FlatpakConfigManager()
        self._action_full_update: Optional[CustomSoftwareAction] = None
        self._suggestions_file_url: Optional[str] = None

    def get_managed_types(self) -> Set["type"]:
        return {FlatpakApplication}

    def _map_to_model(self, app_json: dict, installed: bool, disk_loader: Optional[DiskCacheLoader], internet: bool = True) -> Tuple[FlatpakApplication, Optional[FlatpakAsyncDataLoader]]:

        app = FlatpakApplication(**app_json, i18n=self.i18n)
        app.installed = installed
        api_data = self.api_cache.get(app_json['id'])

        if app.runtime and app.latest_version is None:
            app.latest_version = app.version

        expired_data = api_data and api_data.get('expires_at') and api_data['expires_at'] <= datetime.utcnow()

        data_loader: Optional[FlatpakAsyncDataLoader] = None

        if not api_data or expired_data:
            if not app.runtime:
                if disk_loader:
                    disk_loader.fill(app)  # preloading cached disk data

                if internet:
                    data_loader = FlatpakAsyncDataLoader(app=app, api_cache=self.api_cache, manager=self,
                                                         context=self.context, category_cache=self.category_cache)
                    data_loader.start()

        else:
            app.fill_cached_data(api_data)
            app.status = PackageStatus.READY

        return app, data_loader

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
                        res.new.append(self._map_to_model(app_found, False, disk_loader)[0])

        res.total = len(res.installed) + len(res.new)
        return res

    def _add_updates(self, version: Version, output: list):
        output.append(flatpak.list_updates_as_str(version))

    def _fill_required_runtimes(self, installation: str, output: List[Tuple[str, str]]):
        runtimes = flatpak.list_required_runtime_updates(installation=installation)

        if runtimes:
            output.extend(runtimes)

    def _fill_required_runtime_updates(self, output: Dict[str, List[Tuple[str, str]]]):
        threads = []
        for installation in ('system', 'user'):
            runtimes = list()
            output[installation] = runtimes
            t = Thread(target=self._fill_required_runtimes, args=(installation, runtimes))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

    def read_installed(self, disk_loader: Optional[DiskCacheLoader], limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None,
                       internet_available: bool = None, wait_async_data: bool = False) -> SearchResult:
        version = flatpak.get_version()

        updates, required_runtimes = list(), dict()

        thread_updates, thread_runtimes = None, None
        if internet_available:
            thread_updates = Thread(target=self._add_updates, args=(version, updates))
            thread_updates.start()

            if version >= VERSION_1_12:
                thread_runtimes = Thread(target=self._fill_required_runtime_updates, args=(required_runtimes,))
                thread_runtimes.start()

        installed = flatpak.list_installed(version)

        update_map = None
        if thread_updates:
            thread_updates.join()
            update_map = updates[0]

        models = {}
        data_loaders: Optional[List[FlatpakAsyncDataLoader]] = [] if wait_async_data else None

        if installed:
            for app_json in installed:
                model, loader = self._map_to_model(app_json=app_json, installed=True,
                                                   disk_loader=disk_loader, internet=internet_available)
                model.update = False
                models[model.get_update_id(version)] = model

                if loader and data_loaders is not None:
                    data_loaders.append(loader)

        if update_map:
            for update_id in update_map['full']:
                model_with_update = models.get(update_id)
                if model_with_update:
                    model_with_update.update = True
                else:
                    # it is a new component that must be installed
                    update_id_split = update_id.split('/')
                    new_app = FlatpakApplication(id=update_id_split[0],
                                                 branch=update_id_split[1],
                                                 installation=update_id_split[2],
                                                 name=update_id_split[0].split('.')[-1].strip(),
                                                 version=update_id_split[1],
                                                 arch='x86_64' if self.context.is_system_x86_64() else 'x86',
                                                 origin=update_id_split[3] if len(update_id_split) == 4 else None)
                    new_app.update_component = True  # mark as "update component"
                    new_app.installed = True  # faking the "installed" status to be displayed as an update
                    new_app.update = True
                    new_app.update_ref()
                    models[update_id] = new_app

            if version >= VERSION_1_2:
                for partial_update_id in update_map['partial']:
                    partial_data = partial_update_id.split('/')

                    for model in models.values():
                        if model.installation == partial_data[2] and model.branch == partial_data[1]:
                            if model.id == partial_data[0]:
                                model.update = True
                                break
                            elif model.id in partial_data[0]:
                                partial_model = model.gen_partial(partial_data[0])
                                partial_model.update = True
                                models[partial_update_id] = partial_model
                                break

        if thread_runtimes:
            thread_runtimes.join()

        if required_runtimes:
            for installation in ('system', 'user'):
                installation_runtimes = required_runtimes.get(installation)

                if installation_runtimes:
                    for ref, origin in installation_runtimes:
                        ref_split = ref.split('/')
                        models[f'{installation}.'] = FlatpakApplication(id=ref_split[1],
                                                                        ref=ref,
                                                                        origin=origin,
                                                                        name=ref_split[1],
                                                                        version=ref_split[-1],
                                                                        latest_version=ref_split[-1],
                                                                        runtime=True,
                                                                        installation=installation,
                                                                        installed=False,
                                                                        update_component=True,
                                                                        update=True)

        if models:
            ignored = self._read_ignored_updates()

            if ignored:
                for model in models.values():
                    if model.get_update_ignore_key() in ignored:
                        model.updates_ignored = True

        if data_loaders:
            for loader in data_loaders:
                loader.join()

        return SearchResult([*models.values()], None, len(models))

    def downgrade(self, pkg: FlatpakApplication, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        if not self._make_exports_dir(watcher):
            return False

        watcher.change_progress(10)
        watcher.change_substatus(self.i18n['flatpak.downgrade.commits'])

        history = self.get_history(pkg, full_commit_str=True)

        # downgrade is not possible if the app current commit in the first one:
        if history.pkg_status_idx == len(history.history) - 1:
            watcher.show_message(self.i18n['flatpak.downgrade.impossible.title'],
                                 self.i18n['flatpak.downgrade.impossible.body'].format(bold(pkg.name)),
                                 MessageType.ERROR)
            return False

        commit = history.history[history.pkg_status_idx + 1]['commit']
        watcher.change_substatus(self.i18n['flatpak.downgrade.reverting'])
        watcher.change_progress(50)
        success, _ = ProcessHandler(watcher).handle_simple(flatpak.downgrade(app_ref=pkg.ref,
                                                                             commit=commit,
                                                                             installation=pkg.installation,
                                                                             root_password=root_password,
                                                                             version=flatpak.get_version()))
        watcher.change_progress(100)
        return success

    def clean_cache_for(self, pkg: FlatpakApplication):
        super(FlatpakManager, self).clean_cache_for(pkg)
        self.api_cache.delete(pkg.id)

    def upgrade(self, requirements: UpgradeRequirements, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        flatpak_version = flatpak.get_version()

        if not self._make_exports_dir(watcher):
            return False

        for req in requirements.to_upgrade:
            watcher.change_status("{} {} ({})...".format(self.i18n['manage_window.status.upgrading'], req.pkg.name, req.pkg.version))
            related, deps = False, False
            ref = req.pkg.ref

            if req.pkg.partial and flatpak_version < VERSION_1_5:
                related, deps = True, True
                ref = req.pkg.base_ref

            try:
                if req.pkg.update_component:
                    self.logger.info(f"Installing {req.pkg}")
                    res, _ = ProcessHandler(watcher).handle_simple(flatpak.install(app_id=ref,
                                                                                   installation=req.pkg.installation,
                                                                                   origin=req.pkg.origin,
                                                                                   version=flatpak_version))

                else:
                    self.logger.info(f"Updating {req.pkg}")
                    res, _ = ProcessHandler(watcher).handle_simple(flatpak.update(app_ref=ref,
                                                                                  installation=req.pkg.installation,
                                                                                  related=related,
                                                                                  deps=deps,
                                                                                  version=flatpak_version))

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

    def uninstall(self, pkg: FlatpakApplication, root_password: Optional[str], watcher: ProcessWatcher, disk_loader: DiskCacheLoader) -> TransactionResult:

        if not self._make_exports_dir(watcher):
            return TransactionResult.fail()

        flatpak_version = flatpak.get_version()
        uninstalled, _ = ProcessHandler(watcher).handle_simple(flatpak.uninstall(pkg.ref, pkg.installation,
                                                                                 flatpak_version))

        if uninstalled:
            if self.suggestions_cache:
                self.suggestions_cache.delete(pkg.id)

            self.revert_ignored_update(pkg)
            return TransactionResult(success=True, installed=None, removed=[pkg])

        return TransactionResult.fail()

    def get_info(self, app: FlatpakApplication) -> dict:
        if app.installed:
            if app.update_component:
                app_info = {'id': app.id,
                            'name': app.name,
                            'branch': app.branch,
                            'installation': app.installation,
                            'origin': app.origin,
                            'arch': app.arch,
                            'ref': app.ref,
                            'type': 'runtime' if app.runtime else self.i18n['unknown']}
            else:
                version = flatpak.get_version()
                id_ = app.base_id if app.partial and version < VERSION_1_5 else app.id
                app_info = flatpak.get_app_info_fields(id_, app.branch, app.installation)

                if app.partial and version < VERSION_1_5:
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

    def get_history(self, pkg: FlatpakApplication, full_commit_str: bool = False) -> PackageHistory:
        pkg.commit = flatpak.get_commit(pkg.id, pkg.branch, pkg.installation)
        pkg_commit = pkg.commit if pkg.commit else None

        if pkg_commit and not full_commit_str:
            pkg_commit = pkg_commit[0:8]

        commits = flatpak.get_app_commits_data(pkg.ref, pkg.origin, pkg.installation, full_str=full_commit_str)

        status_idx = 0
        commit_found = False

        if pkg_commit is None and len(commits) > 1 and commits[0]['commit'] == '(null)':
            del commits[0]
            pkg_commit = commits[0]
            commit_found = True

        if not commit_found:
            for idx, data in enumerate(commits):
                if data['commit'] == pkg_commit:
                    status_idx = idx
                    commit_found = True
                    break

        if not commit_found and pkg_commit and commits[0]['commit'] == '(null)':
            commits[0]['commit'] = pkg_commit

        return PackageHistory(pkg=pkg, history=commits, pkg_status_idx=status_idx)

    def _make_exports_dir(self, watcher: ProcessWatcher) -> bool:
        if not os.path.exists(EXPORTS_PATH):
            self.logger.info("Creating dir '{}'".format(EXPORTS_PATH))
            watcher.print('Creating dir {}'.format(EXPORTS_PATH))
            try:
                Path(EXPORTS_PATH).mkdir(parents=True, exist_ok=True)
            except:
                watcher.print('Error while creating the directory {}'.format(EXPORTS_PATH))
                return False

        return True

    def install(self, pkg: FlatpakApplication, root_password: Optional[str], disk_loader: DiskCacheLoader, watcher: ProcessWatcher) -> TransactionResult:
        if not self.context.root_user:
            flatpak_config = self.configman.get_config()
            install_level = flatpak_config['installation_level']
        else:
            install_level = 'system'

        if install_level is not None:
            self.logger.info("Default Flaptak installation level defined: {}".format(install_level))

            if install_level not in ('user', 'system'):
                watcher.show_message(title=self.i18n['error'].capitalize(),
                                     body=self.i18n['flatpak.install.bad_install_level.body'].format(field=bold('installation_level'),
                                                                                                     file=bold(CONFIG_FILE)),
                                     type_=MessageType.ERROR)
                return TransactionResult(success=False, installed=[], removed=[])

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
                valid, user_password = watcher.request_root_password()
                if not valid:
                    watcher.print('Operation aborted')
                    return TransactionResult(success=False, installed=[], removed=[])
                else:
                    if not handler.handle_simple(flatpak.set_default_remotes('system', user_password))[0]:
                        watcher.show_message(title=self.i18n['error'].capitalize(),
                                             body=self.i18n['flatpak.remotes.system_flathub.error'],
                                             type_=MessageType.ERROR)
                        watcher.print("Operation cancelled")
                        return TransactionResult(success=False, installed=[], removed=[])

        # retrieving all installed so it will be possible to know the additional installed runtimes after the operation succeeds
        flatpak_version = flatpak.get_version()
        installed = flatpak.list_installed(flatpak_version)
        installed_by_level = {'{}:{}:{}'.format(p['id'], p['name'], p['branch']) for p in installed if p['installation'] == pkg.installation} if installed else None

        if not self._make_exports_dir(handler.watcher):
            return TransactionResult(success=False, installed=[], removed=[])

        installed, output = handler.handle_simple(flatpak.install(str(pkg.id), pkg.origin, pkg.installation,
                                                                  flatpak_version))

        if not installed and 'error: No ref chosen to resolve matches' in output:
            ref_opts = RE_INSTALL_REFS.findall(output)

            if ref_opts and len(ref_opts) > 1:
                view_opts = [InputOption(label=o, value=o.strip()) for o in ref_opts if o]
                ref_select = SingleSelectComponent(type_=SelectViewType.RADIO, options=view_opts, default_option=view_opts[0], label='')
                if watcher.request_confirmation(title=self.i18n['flatpak.install.ref_choose.title'],
                                                body=self.i18n['flatpak.install.ref_choose.body'].format(bold(pkg.name)),
                                                components=[ref_select],
                                                confirmation_label=self.i18n['proceed'].capitalize(),
                                                deny_label=self.i18n['cancel'].capitalize()):
                    ref = ref_select.get_selected()
                    installed, output = handler.handle_simple(flatpak.install(ref, pkg.origin, pkg.installation,
                                                                              flatpak_version))
                    pkg.ref = ref
                    pkg.runtime = 'runtime' in ref
                else:
                    watcher.print('Aborted by the user')
                    return TransactionResult.fail()
            else:
                return TransactionResult.fail()

        if installed:
            try:
                fields = flatpak.get_fields(str(pkg.id), pkg.branch, ['Ref', 'Branch'])

                if fields:
                    pkg.ref = fields[0]
                    pkg.branch = fields[1]
            except:
                traceback.print_exc()

        if installed:
            new_installed = [pkg]
            current_installed = flatpak.list_installed(flatpak_version)
            current_installed_by_level = [p for p in current_installed if p['installation'] == pkg.installation] if current_installed else None

            if current_installed_by_level and (not installed_by_level or len(current_installed_by_level) > len(installed_by_level) + 1):
                pkg_key = '{}:{}:{}'.format(pkg.id, pkg.name, pkg.branch)
                net_available = self.context.is_internet_available()
                for p in current_installed_by_level:
                    current_key = '{}:{}:{}'.format(p['id'], p['name'], p['branch'])
                    if current_key != pkg_key and (not installed_by_level or current_key not in installed_by_level):
                        new_installed.append(self._map_to_model(app_json=p, installed=True,
                                                                disk_loader=disk_loader, internet=net_available)[0])

            return TransactionResult(success=installed, installed=new_installed, removed=[])
        else:
            return TransactionResult.fail()

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> Tuple[bool, Optional[str]]:
        return (True, None) if flatpak.is_installed() else (False, self.i18n['missing_dep'].format(dep=bold('flatpak')))

    def requires_root(self, action: SoftwareAction, pkg: FlatpakApplication) -> bool:
        return action == SoftwareAction.DOWNGRADE and pkg.installation == 'system'

    def prepare(self, task_manager: TaskManager, root_password: Optional[str], internet_available: bool):
        CreateConfigFile(taskman=task_manager, configman=self.configman, i18n=self.i18n,
                         task_icon_path=get_icon_path(), logger=self.logger).start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        updates = []
        installed = self.read_installed(None, internet_available=internet_available, wait_async_data=True).installed

        if installed:
            for p in installed:
                if isinstance(p, FlatpakApplication) and p.update and not p.is_update_ignored():
                    updates.append(PackageUpdate(pkg_id=f'{p.id}:{p.branch}:{p.installation}',
                                                 pkg_type='Flatpak',
                                                 name=p.name,
                                                 version=p.latest_version))

        return updates

    def list_warnings(self, internet_available: bool) -> Optional[List[str]]:
        pass

    def _read_local_suggestions_file(self) -> Optional[str]:
        try:
            with open(self.suggestions_file_url) as f:
                suggestions_str = f.read()

            return suggestions_str
        except FileNotFoundError:
            self.logger.error(f"Local Flatpak suggestions file not found: {self.suggestions_file_url}")
        except OSError:
            self.logger.error(f"Could not read local Flatpak suggestions file: {self.suggestions_file_url}")
            traceback.print_exc()

    def _download_remote_suggestions_file(self) -> Optional[str]:
        self.logger.info(f"Downloading the Flatpak suggestions from {self.suggestions_file_url}")
        file = self.http_client.get(self.suggestions_file_url)

        if file:
            return file.text

    def _fill_suggestion(self, appid: str, priority: SuggestionPriority, flatpak_version: Version, remote: str,
                         output: List[PackageSuggestion]):
        app_json = flatpak.search(flatpak_version, appid, remote, app_id=True)

        if app_json:
            model = PackageSuggestion(self._map_to_model(app_json[0], False, None)[0], priority)
            self.suggestions_cache.add(appid, model)
            output.append(model)
        else:
            self.logger.warning(f"Could not find Flatpak suggestions '{appid}'")

    def list_suggestions(self, limit: int, filter_installed: bool) -> Optional[List[PackageSuggestion]]:
        if limit == 0:
            return

        if self.is_local_suggestions_file_mapped():
            suggestions_str = self._read_local_suggestions_file()
        else:
            suggestions_str = self._download_remote_suggestions_file()

        if suggestions_str is None:
            return

        if not suggestions_str:
            self.logger.warning(f"No Flatpak suggestion found in {self.suggestions_file_url}")
            return

        ids_prios = suggestions.parse(suggestions_str, self.logger, 'Flatpak')

        if not ids_prios:
            self.logger.warning(f"No Flatpak suggestion could be parsed from {self.suggestions_file_url}")
            return

        suggestion_by_priority = suggestions.sort_by_priority(ids_prios)

        if filter_installed:
            installed = {i.id for i in self.read_installed(disk_loader=None).installed}

            if installed:
                suggestion_by_priority = tuple(id_ for id_ in suggestion_by_priority if id_ not in installed)

        if suggestion_by_priority and 0 < limit < len(suggestion_by_priority):
            suggestion_by_priority = suggestion_by_priority[0:limit]

        self.logger.info(f'Available Flatpak suggestions: {len(suggestion_by_priority)}')

        if not suggestion_by_priority:
            return

        flatpak_version = flatpak.get_version()
        remote = self._get_search_remote()

        self.logger.info("Mapping Flatpak suggestions")
        res, fill_suggestions = [], []
        cached_count = 0

        for appid in suggestion_by_priority:
            cached_instance = self.suggestions_cache.get(appid)

            if cached_instance:
                res.append(cached_instance)
                cached_count += 1
            else:
                fill = Thread(target=self._fill_suggestion, args=(appid, ids_prios[appid], flatpak_version,
                                                                  remote, res))
                fill.start()
                fill_suggestions.append(fill)

        for fill in fill_suggestions:
            fill.join()

        if cached_count > 0:
            self.logger.info(f"Returning {cached_count} cached Flatpak suggestions")

        return res

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: FlatpakApplication):
        flatpak.run(str(pkg.id))

    def get_screenshots(self, pkg: FlatpakApplication) -> Generator[str, None, None]:
        screenshots_url = f'{FLATHUB_API_URL}/apps/{pkg.id}'

        try:
            res = self.http_client.get_json(screenshots_url)

            if res and res.get('screenshots'):
                for s in res['screenshots']:
                    if s.get('imgDesktopUrl'):
                        yield s['imgDesktopUrl']

        except Exception as e:
            if e.__class__.__name__ == 'JSONDecodeError':
                self.context.logger.error("Could not decode json from '{}'".format(screenshots_url))
            else:
                traceback.print_exc()

    def get_settings(self) -> Optional[Generator[SettingsView, None, None]]:
        if not self.context.root_user:
            fields = []

            flatpak_config = self.configman.get_config()

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
                                                default_option=[o for o in install_opts if o.value == flatpak_config['installation_level']][0],
                                                max_per_line=len(install_opts),
                                                type_=SelectViewType.COMBO,
                                                alignment=ViewComponentAlignment.CENTER,
                                                id_='install'))

            yield SettingsView(self, PanelComponent([FormComponent(fields, self.i18n['installation'].capitalize())]))

    def save_settings(self, component: PanelComponent) -> Tuple[bool, Optional[List[str]]]:
        flatpak_config = self.configman.get_config()
        form = component.get_component_by_idx(0, FormComponent)
        flatpak_config['installation_level'] = form.get_component('install', SingleSelectComponent).get_selected()

        try:
            self.configman.save_config(flatpak_config)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def get_upgrade_requirements(self, pkgs: List[FlatpakApplication], root_password: Optional[str], watcher: ProcessWatcher) -> UpgradeRequirements:
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

        to_update = [UpgradeRequirement(pkg=p, extra_size=0, required_size=p.size) for p in self.sort_update_order(pkgs)]
        return UpgradeRequirements(None, None, to_update, [])

    def sort_update_order(self, pkgs: List[FlatpakApplication]) -> List[FlatpakApplication]:
        runtimes, apps = set(), set()

        for p in pkgs:
            if p.runtime:
                runtimes.add(p)
            else:
                apps.add(p)

        sorted_list = []
        for comps in (runtimes, apps):
            if comps:
                comp_list = list(comps)
                comp_list.sort(key=attrgetter('installation', 'name', 'id'))
                sorted_list.extend(comp_list)

        return sorted_list

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
        Path(FLATPAK_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
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

    def gen_custom_actions(self) -> Generator[CustomSoftwareAction, None, None]:
        yield self.action_full_update

    def full_update(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        handler = ProcessHandler(watcher)
        return handler.handle_simple(flatpak.full_update(flatpak.get_version()))[0]

    @property
    def action_full_update(self) -> CustomSoftwareAction:
        if self._action_full_update is None:
            self._action_full_update = CustomSoftwareAction(i18n_label_key='flatpak.action.full_update',
                                                            i18n_description_key='flatpak.action.full_update.description',
                                                            i18n_status_key='flatpak.action.full_update.status',
                                                            backup=True,
                                                            manager=self,
                                                            requires_internet=True,
                                                            icon_path=get_icon_path(),
                                                            manager_method='full_update',
                                                            requires_root=False)

        return self._action_full_update

    @property
    def suggestions_file_url(self) -> str:
        if self._suggestions_file_url is None:
            file_url = self.context.get_suggestion_url(self.__module__)

            if not file_url:
                file_url = 'https://raw.githubusercontent.com/vinifmor/bauh-files/master/flatpak/suggestions.txt'

            self._suggestions_file_url = file_url

            if file_url.startswith('/'):
                self.logger.info(f"Local Flatpak suggestions file mapped: {file_url}")

        return self._suggestions_file_url

    def is_local_suggestions_file_mapped(self) -> bool:
        return self.suggestions_file_url.startswith('/')
