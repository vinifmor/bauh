import os.path
import shutil
import traceback
from operator import attrgetter
from pathlib import Path
from shutil import which
from subprocess import Popen
from threading import Thread
from typing import List, Optional, Tuple, Set, Type, Dict, Iterable, Generator

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SoftwareAction, TransactionResult, UpgradeRequirements, \
    SearchResult, UpgradeRequirement, SettingsView, SettingsController
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import TaskManager, ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageSuggestion, PackageUpdate, PackageHistory, \
    CustomSoftwareAction
from bauh.api.abstract.view import TextInputComponent, PanelComponent, FormComponent, MessageType, \
    SingleSelectComponent, InputOption, SelectViewType, ViewComponentAlignment
from bauh.api.paths import CONFIG_DIR
from bauh.commons.html import bold
from bauh.commons.system import ProcessHandler
from bauh.commons.util import NullLoggerFactory
from bauh.commons.view_utils import get_human_size_str
from bauh.gems.debian import DEBIAN_ICON_PATH
from bauh.gems.debian.aptitude import Aptitude, AptitudeOutputHandlerFactory, AptitudeAction
from bauh.gems.debian.common import fill_show_data
from bauh.gems.debian.config import DebianConfigManager
from bauh.gems.debian.gui import DebianViewBridge
from bauh.gems.debian.index import ApplicationIndexer, ApplicationIndexError, ApplicationsMapper
from bauh.gems.debian.model import DebianPackage, DebianApplication
from bauh.gems.debian.suggestions import DebianSuggestionsDownloader
from bauh.gems.debian.tasks import UpdateApplicationIndex, MapApplications, SynchronizePackages


class DebianPackageManager(SoftwareManager, SettingsController):

    def __init__(self, context: ApplicationContext):
        super(DebianPackageManager, self).__init__(context)
        self._i18n = context.i18n
        self._log = context.logger
        self._types: Optional[Set[Type[SoftwarePackage]]] = None
        self._enabled = True
        self._app_indexer: Optional[ApplicationIndexer] = None
        self._apps_index: Optional[Dict[str, DebianApplication]] = None
        self._configman: Optional[DebianConfigManager] = None
        self._action_launch_sources: Optional[CustomSoftwareAction] = None
        self._default_actions: Optional[Iterable[CustomSoftwareAction]] = None
        self._view: Optional[DebianViewBridge] = None
        self._app_mapper: Optional[ApplicationsMapper] = None
        self._aptitude: Optional[Aptitude] = None
        self._output_handler: Optional[AptitudeOutputHandlerFactory] = None
        self._known_sources_apps: Optional[Tuple[str, ...]] = None
        self._install_show_attrs: Optional[Set[str]] = None
        self._file_ignored_updates: Optional[str] = None
        self._suggestions_downloader: Optional[DebianSuggestionsDownloader] = None

    def _update_apps_index(self, apps: Iterable[DebianApplication]):
        self._apps_index = {app.name: app for app in apps} if apps else dict()

    def search(self, words: str, disk_loader: Optional[DiskCacheLoader], limit: int, is_url: bool) -> SearchResult:
        config_ = dict()
        fill_config = Thread(target=self._fill_config, args=(config_,))
        fill_config.start()

        res = SearchResult.empty()

        if not is_url:
            for pkg in self.aptitude.search(words):
                if fill_config.is_alive():
                    fill_config.join()
                    
                pkg.global_purge = bool(config_.get('remove.purge', False))
                if pkg.installed:
                    pkg.bind_app(self.apps_index.get(pkg.name))
                    res.installed.append(pkg)
                else:
                    res.new.append(pkg)

        return res

    def _fill_ignored_updates(self, output: Set[str]):

        try:
            with open(self.file_ignored_updates) as f:
                ignored_str = f.read()
        except FileNotFoundError:
            return

        if ignored_str:
            for line in ignored_str.split('\n'):
                line_clean = line.strip()

                if line_clean:
                    output.add(line_clean)

    def _fill_config(self, config_: dict):
        config_.update(self.configman.get_config())

    def read_installed(self, disk_loader: Optional[DiskCacheLoader], pkg_types: Optional[Set[Type[SoftwarePackage]]],
                       internet_available: bool, limit: int = -1, only_apps: bool = False,
                       names: Optional[Iterable[str]] = None) -> SearchResult:

        config_ = dict()
        fill_config = Thread(target=self._fill_config, args=(config_,))
        fill_config.start()

        ignored_updates = set()
        fill_ignored_updates = Thread(target=self._fill_ignored_updates, args=(ignored_updates,))
        fill_ignored_updates.start()

        threads = (fill_config, fill_ignored_updates)

        res = SearchResult(installed=[], new=None, total=0)

        for pkg in self.aptitude.read_installed():
            for t in threads:
                if t.is_alive():
                    t.join()

            pkg.bind_app(self.apps_index.get(pkg.name))
            pkg.global_purge = bool(config_.get('remove.purge', False))
            pkg.updates_ignored = bool(ignored_updates and pkg.name in ignored_updates)
            res.installed.append(pkg)

        return res

    def downgrade(self, pkg: SoftwarePackage, root_password: str, handler: ProcessWatcher) -> bool:
        return False

    def upgrade(self, requirements: UpgradeRequirements, root_password: str, watcher: ProcessWatcher) -> bool:
        handler = ProcessHandler(watcher)

        targets = (r.pkg.name for r in (*requirements.to_upgrade, *(requirements.to_install or ())))

        with self.output_handler.start(watcher=watcher, targets=targets, action=AptitudeAction.UPGRADE) as handle:
            to_upgrade = (r.pkg.name for r in requirements.to_upgrade)
            success, _ = handler.handle_simple(self.aptitude.upgrade(packages=to_upgrade,
                                                                     root_password=root_password),
                                               output_handler=handle)
        return success

    def _fill_updates(self, output: Dict[str, str]):
        for name, version in self.aptitude.read_updates():
            output[name] = version

    def uninstall(self, pkg: DebianPackage, root_password: str, watcher: ProcessWatcher,
                  disk_loader: Optional[DiskCacheLoader], purge: bool = False) -> TransactionResult:

        config_ = self.configman.get_config()
        purge_ = purge or config_.get('remove.purge', False)

        watcher.change_substatus(self._i18n['debian.simulate_operation'])

        transaction = self.aptitude.simulate_removal((pkg.name,), purge=purge_)

        if not transaction or not transaction.to_remove:
            return TransactionResult.fail()

        if pkg not in transaction.to_remove:
            watcher.show_message(title=self._i18n['popup.title.error'],
                                 body=self._i18n['debian.remove.impossible'].format(pkg=bold(pkg.name)),
                                 type_=MessageType.ERROR)
            return TransactionResult.fail()

        watcher.change_substatus('')

        deps = tuple(p for p in transaction.to_remove if p.name != pkg.name)

        if deps:
            # updates are required to be filled in case the dependencies are currently displayed on the view
            updates = dict()
            fill_updates = Thread(target=self._fill_updates, args=(updates,))
            fill_updates.start()

            deps_data = self.aptitude.show((p.name for p in deps), attrs=('description', 'maintainer', 'section'))

            if deps_data:
                for p in deps:
                    fill_show_data(p, deps_data.get(p.name))

            if not self.view.confirm_removal(source_pkg=pkg.name, dependencies=deps, watcher=watcher):
                return TransactionResult.fail()

            fill_updates.join()

            if updates:
                for p in deps:
                    latest_version = updates.get(p.name)

                    if latest_version is not None and p.version != latest_version:
                        p.latest_version = latest_version
                        p.update = True

        watcher.change_substatus(self._i18n['debian.uninstall.removing'])

        handler = ProcessHandler(watcher)
        to_remove = tuple(p.name for p in transaction.to_remove)
        with self.output_handler.start(watcher=watcher, targets=to_remove, action=AptitudeAction.REMOVE) as handle:
            removed, _ = handler.handle_simple(self.aptitude.remove(packages=to_remove, root_password=root_password,
                                                                    purge=purge_),
                                               output_handler=handle)

        if not removed:
            return TransactionResult.fail()

        watcher.change_substatus(self._i18n['debian.uninstall.validating'])

        current_installed_names = set(self.aptitude.read_installed_names())

        watcher.change_substatus('')

        all_removed, apps_removed, not_removed_names = [], set(), set()

        for p in transaction.to_remove:
            if p.name not in current_installed_names:
                instance = p if p != pkg else pkg

                all_removed.append(instance)

                if instance.app:
                    apps_removed.add(instance.app)

                instance.installed = False
                instance.version = instance.latest_version
                instance.update = False
                instance.bind_app(None)
            else:
                not_removed_names.add(p.name)

        if apps_removed:  # updating apps index
            watcher.print(self._i18n['debian.app_index.updating'] + ' ...')
            watcher.change_substatus(self._i18n['debian.app_index.updating'])
            indexed_apps = set(self.app_indexer.read_index())

            if indexed_apps:
                new_index = indexed_apps.difference(apps_removed)
                try:
                    self.app_indexer.update_index(new_index, update_timestamp=False)
                    self._update_apps_index(new_index)
                    self._log.info(f"Debian applications removed from the index: "
                                   f"{', '.join((a.name for a in apps_removed))}")
                except ApplicationIndexError:
                    pass

        watcher.change_substatus('')

        success = True
        if not_removed_names:
            success = pkg.name not in not_removed_names
            not_removed_str = ', '.join((bold(p) for p in sorted(not_removed_names)))
            watcher.show_message(title=self._i18n[f"popup.title.{'warning' if success else 'error'}"],
                                 body=self._i18n['debian.uninstall.failed_to_remove'].format(no=len(not_removed_names),
                                                                                             pkgs=not_removed_str),
                                 type_=MessageType.WARNING if success else MessageType.ERROR)

        return TransactionResult(success=success, installed=None, removed=all_removed)

    def _map_dependents(self, packages_data: Dict[str, Dict[str, object]]) -> Optional[Dict[str, Set[str]]]:
        if packages_data:
            dependents = None
            if packages_data:
                dependents = dict()

                for p, data in packages_data.items():
                    for attr in ('depends', 'predepends'):
                        dep_exps = data.get(attr)

                        if isinstance(dep_exps, tuple):
                            for exp in dep_exps:
                                dep = exp.split(' ')[0].strip()
                                dep_dependents = dependents.get(dep)
                                if dep_dependents is None:
                                    dep_dependents = set()
                                    dependents[dep] = dep_dependents

                                dep_dependents.add(p)

            return dependents

    def get_upgrade_requirements(self, pkgs: List[DebianPackage], root_password: str, watcher: ProcessWatcher) \
            -> UpgradeRequirements:

        transaction = self.aptitude.simulate_upgrade((p.name for p in pkgs))

        if transaction:
            size_to_query = (f'{p.name}={p.latest_version}' for p in (*transaction.to_upgrade,
                                                                      *transaction.to_install,
                                                                      *transaction.to_remove))

            update_extra_attrs = ('compressed size', *(('depends', 'predepends') if transaction.to_install else ()))
            update_data = self.aptitude.show(pkgs=size_to_query, attrs=update_extra_attrs)

            to_install = None
            if transaction.to_install:
                dependents = self._map_dependents(update_data)

                to_install = []
                for p in transaction.to_install:
                    p_data = update_data.get(p.name) if update_data else None
                    req_size = p_data.get('compressed size') if p_data else None

                    reason = None
                    if dependents:
                        p_dependents = dependents.get(p.name)

                        if p_dependents:
                            deps_str = ', '.join((bold(d) for d in p_dependents))
                            reason = self._i18n['debian.transaction.dependency_of'].format(pkgs=deps_str)

                    to_install.append(UpgradeRequirement(pkg=p, reason=reason, required_size=req_size,
                                                         extra_size=p.transaction_size))

                to_install.sort(key=attrgetter('pkg.name'))
                to_install = tuple(to_install)

            to_remove = None
            if transaction.to_remove:
                to_remove = []

                for p in transaction.to_remove:
                    to_remove.append(UpgradeRequirement(pkg=p, required_size=0, extra_size=p.transaction_size))

                to_remove.sort(key=attrgetter('pkg.name'))
                to_remove = tuple(to_remove)

            to_upgrade = None

            if transaction.to_upgrade:
                to_upgrade = []

                for p in transaction.to_upgrade:
                    p_data = update_data.get(p.name) if update_data else None

                    if p_data:
                        req_size = p_data.get('compressed size')
                    else:
                        req_size = None

                    to_upgrade.append(UpgradeRequirement(pkg=p, required_size=req_size, extra_size=p.transaction_size))

                to_upgrade.sort(key=attrgetter('pkg.name'))
                to_upgrade = tuple(to_upgrade)

            return UpgradeRequirements(to_install=to_install, to_upgrade=to_upgrade,
                                       to_remove=to_remove, cannot_upgrade=None)
        else:
            cannot_upgrade = [UpgradeRequirement(pkg=p, reason=self._i18n['error']) for p in pkgs]
            cannot_upgrade.sort(key=attrgetter('pkg.name'))
            return UpgradeRequirements(cannot_upgrade=cannot_upgrade, to_install=None, to_remove=None,
                                       to_upgrade=[])

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        if self._types is None:
            self._types = {DebianPackage}

        return self._types

    def get_info(self, pkg: DebianPackage) -> Optional[dict]:
        info = {'00.name': pkg.name, '01.version': pkg.version,
                "02.description": pkg.description}

        if pkg.installed and pkg.app:
            info['03.exec'] = pkg.app.exe_path

        extra_info = self.aptitude.show((f'{pkg.name}={pkg.version}',), verbose=True)

        if extra_info:
            extra_info = extra_info.get(pkg.name)

            if extra_info:
                ignored_fields = {'package', 'version', 'description'}

                for field, val in extra_info.items():
                    if field not in ignored_fields and not field.startswith('description'):
                        final_val = get_human_size_str(val) if field in self.aptitude.size_attrs else val
                        final_field = f'04.{field}'

                        if final_field not in self._i18n:
                            self._i18n.default[final_field] = field

                        info[final_field] = final_val  # for sorting

        return info

    def get_history(self, pkg: SoftwarePackage) -> PackageHistory:
        pass

    def install(self, pkg: SoftwarePackage, root_password: str, disk_loader: Optional[DiskCacheLoader],
                watcher: ProcessWatcher) -> TransactionResult:

        watcher.change_substatus(self._i18n['debian.simulate_operation'])
        transaction = self.aptitude.simulate_installation((pkg.name, ))

        if transaction is None or not transaction.to_install:
            return TransactionResult.fail()

        if transaction.to_remove or (transaction.to_install and len(transaction.to_install) > 1):
            watcher.change_substatus(self._i18n['debian.transaction.get_data'])

            deps = tuple(p for p in transaction.to_install or () if p.name != pkg.name)
            removal = tuple(p for p in transaction.to_remove or ())
            all_pkgs = [*deps, *removal]

            pkgs_data = self.aptitude.show(pkgs=(f'{d.name}={d.version}' for d in all_pkgs),
                                           attrs=self.install_show_attrs)

            if pkgs_data:
                for p in all_pkgs:
                    fill_show_data(p, pkgs_data.get(p.name))

            if not self.view.confirm_transaction(to_install=deps, removal=removal, watcher=watcher):
                return TransactionResult.fail()

        watcher.change_substatus(self._i18n['debian.installing_pkgs'])
        handler = ProcessHandler(watcher)

        targets = (p.name for p in transaction.to_install)
        with self.output_handler.start(watcher=watcher, targets=targets, action=AptitudeAction.INSTALL) as handle:
            installed, _ = handler.handle_simple(self.aptitude.install(packages=(pkg.name,),
                                                                       root_password=root_password),
                                                 output_handler=handle)

        if installed:
            self._refresh_apps_index(watcher)

            watcher.change_substatus(self._i18n['debian.install.validating'])

            currently_installed = set(self.aptitude.read_installed_names())

            installed_instances = []
            if currently_installed:
                for p in transaction.to_install:
                    instance = p if p != pkg else pkg
                    if instance.name in currently_installed:
                        instance.installed = True
                        instance.bind_app(self.apps_index.get(instance.name))
                        installed_instances.append(instance)

            removed = None

            if transaction.to_remove:
                removed = [p for p in transaction.to_remove if p.name not in currently_installed]

                not_removed = set(transaction.to_remove).difference(removed)

                if not_removed:
                    not_removed_str = ' '.join(p.name for p in not_removed)
                    self._log.warning(f"The following packages were not removed: {not_removed_str}")

            return TransactionResult(installed=installed_instances, removed=removed,
                                     success=bool(installed_instances and pkg in installed_instances))
        else:
            watcher.change_substatus('')
            return TransactionResult.fail()

    def _refresh_apps_index(self, watcher: ProcessWatcher):
        watcher.change_substatus(self._i18n['debian.app_index.checking'])
        self._log.info("Reading the cached Debian applications")
        indexed_apps = self.app_indexer.read_index()
        self._log.info("Mapping the Debian applications")
        current_apps = self.app_mapper.map_executable_applications()

        if current_apps != indexed_apps:
            watcher.print(self._i18n['debian.app_index.updating'] + '...')
            watcher.change_substatus(self._i18n['debian.app_index.updating'])

            try:
                self.app_indexer.update_index(current_apps)
                self._update_apps_index(current_apps)

                if indexed_apps is not None:
                    new_apps = current_apps.difference(indexed_apps)

                    if new_apps:
                        self._log.info(f"Debian applications added to the index: "
                                       f"{','.join((a.name for a in new_apps))}")

            except ApplicationIndexError:
                pass

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def can_work(self) -> Tuple[bool, Optional[str]]:
        if not which('aptitude'):
            return False, self._i18n['missing_dep'].format(dep=bold('aptitude'))

        return True, None

    def requires_root(self, action: SoftwareAction, pkg: Optional[SoftwarePackage]) -> bool:
        if action == action.PREPARE:
            deb_config = self.configman.get_config()
            return SynchronizePackages.should_synchronize(deb_config, NullLoggerFactory.logger())

        return action != SoftwareAction.SEARCH

    def prepare(self, task_manager: Optional[TaskManager], root_password: Optional[str],
                internet_available: Optional[bool]):

        deb_config = self.configman.get_config()

        if SynchronizePackages.should_synchronize(deb_config, self._log):
            sync_pkgs = SynchronizePackages(taskman=task_manager, i18n=self._i18n, logger=self._log,
                                            root_password=root_password, aptitude=self.aptitude)
            sync_pkgs.start()

        if self.suggestions_downloader.should_download(deb_config, only_positive_exp=True):
            self.suggestions_downloader.register_task(task_manager)
            self.suggestions_downloader.start()

        self.index_apps(root_password=root_password, watcher=None, taskman=task_manager,
                        deb_config=deb_config, check_expiration=True)

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        ignored_updates = set()
        fill_ignored_updates = Thread(target=self._fill_ignored_updates, args=(ignored_updates,))
        fill_ignored_updates.start()

        updates = list()
        for name, version in self.aptitude.read_updates():
            if fill_ignored_updates.is_alive():
                fill_ignored_updates.join()

            if name not in ignored_updates:
                updates.append(PackageUpdate(pkg_id=name, name=name, version=version, pkg_type='debian'))

        return updates

    def list_warnings(self, internet_available: bool) -> Optional[List[str]]:
        pass

    def _fill_installed_names(self, output: Set[str]):
        output.update(self.aptitude.read_installed_names())

    def _fill_suggestions(self, output: Dict[str, int]):
        self.suggestions_downloader.register_task(None)
        suggestions = self.suggestions_downloader.read(self.configman.read_config())

        if suggestions:
            output.update(suggestions)

    def list_suggestions(self, limit: int, filter_installed: bool) -> Optional[List[PackageSuggestion]]:
        name_priority = dict()

        fill_suggestions = Thread(target=self._fill_suggestions, args=(name_priority,))
        fill_suggestions.start()

        if filter_installed:
            installed = set()
            fill_installed = Thread(target=self._fill_installed_names, args=(installed, ))
            fill_installed.start()
        else:
            installed, fill_installed = None, None

        fill_suggestions.join()

        if fill_installed:
            fill_installed.join()

        if not name_priority:
            self._log.info("No Debian package suggestions found")
            return []

        self._log.info(f"Found {len(name_priority)} Debian package suggestions")

        to_load = tuple(name_priority.keys()) if not installed else {*name_priority.keys()}.difference(installed)

        if not to_load:
            return []

        suggestions = []

        for pkg in self.aptitude.search_by_name(to_load):
            prio = name_priority.get(pkg.name)

            if prio:
                suggestions.append(PackageSuggestion(package=pkg, priority=prio))

        return suggestions

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: SoftwarePackage):
        if isinstance(pkg, DebianPackage):
            final_cmd = pkg.app.exe_path.replace('%U', '')
            Popen(final_cmd, shell=True)

    def get_settings(self) -> Optional[Generator[SettingsView, None, None]]:
        config_ = self.configman.get_config()

        purge_opts = [InputOption(label=self._i18n['yes'].capitalize(), value=True),
                      InputOption(label=self._i18n['no'].capitalize(), value=False)]

        purge_current = tuple(o for o in purge_opts if o.value == bool(config_['remove.purge']))[0]
        sel_purge = SingleSelectComponent(id_='remove.purge',
                                          label=self._i18n['debian.config.remove.purge'],
                                          tooltip=self._i18n['debian.config.remove.purge.tip'],
                                          options=purge_opts,
                                          default_option=purge_current,
                                          type_=SelectViewType.RADIO,
                                          max_per_line=2)

        sources_app = config_.get('pkg_sources.app')

        if isinstance(sources_app, str) and sources_app not in self.known_sources_apps:
            self._log.warning(f"'pkg_sources.app' ({sources_app}) is not supported. A 'None' value will be considered")
            sources_app = None

        lb_source_auto = self._i18n['debian.config.pkg_sources.app.auto']
        source_opts = [InputOption(id_='auto', value=None, label=lb_source_auto)]

        source_opts.extend((InputOption(id_=a, value=a, label=a) for a in self.known_sources_apps if which(a)))

        source_auto_tip = self._i18n['debian.config.pkg_sources.app.tip'].format(auto=f'"{lb_source_auto}"')
        input_sources = SingleSelectComponent(id_='pkg_sources.app',
                                              label=self._i18n['debian.config.pkg_sources.app'],
                                              tooltip=source_auto_tip,
                                              options=source_opts,
                                              default_option=next(o for o in source_opts if o.value == sources_app),
                                              alignment=ViewComponentAlignment.CENTER,
                                              type_=SelectViewType.COMBO)

        try:
            app_cache_exp = int(config_.get('index_apps.exp', 0))
        except ValueError:
            self._log.error(f"Unexpected value form Debian configuration property 'index_apps.exp': "
                            f"{config_['index_apps.exp']}. Zero (0) will be considered instead.")
            app_cache_exp = 0

        ti_index_apps_exp = TextInputComponent(id_='index_apps.exp',
                                               label=self._i18n['debian.config.index_apps.exp'],
                                               tooltip=self._i18n['debian.config.index_apps.exp.tip'],
                                               value=str(app_cache_exp), only_int=True)

        try:
            sync_pkgs_time = int(config_.get('sync_pkgs.time', 0))
        except ValueError:
            self._log.error(f"Unexpected value form Debian configuration property 'sync_pkgs.time': {config_['sync_pkgs.time']}. "
                            f"Zero (0) will be considered instead.")
            sync_pkgs_time = 0

        ti_sync_pkgs = TextInputComponent(id_='sync_pkgs.time',
                                          label=self._i18n['debian.config.sync_pkgs.time'],
                                          tooltip=self._i18n['debian.config.sync_pkgs.time.tip'],
                                          value=str(sync_pkgs_time), only_int=True)

        try:
            suggestions_exp = int(config_.get('suggestions.exp', 0))
        except ValueError:
            self._log.error(f"Unexpected value form Debian configuration property 'suggestions.exp': {config_['suggestions.exp']}. "
                            f"Zero (0) will be considered instead.")
            suggestions_exp = 0

        ti_suggestions_exp = TextInputComponent(id_='suggestions.exp',
                                                label=self._i18n['debian.config.suggestions.exp'],
                                                tooltip=self._i18n['debian.config.suggestions.exp.tip'],
                                                value=str(suggestions_exp), only_int=True)

        panel = PanelComponent([FormComponent([input_sources, sel_purge, ti_sync_pkgs, ti_index_apps_exp,
                                               ti_suggestions_exp])])
        yield SettingsView(self, panel)

    def save_settings(self, component: PanelComponent) -> Tuple[bool, Optional[List[str]]]:
        config_ = self.configman.get_config()

        container = component.get_component_by_idx(0, FormComponent)

        for prop, type_ in {'remove.purge': SingleSelectComponent,
                            'pkg_sources.app': SingleSelectComponent,
                            'index_apps.exp': TextInputComponent,
                            'sync_pkgs.time': TextInputComponent,
                            'suggestions.exp': TextInputComponent}.items():
            comp = container.get_component(prop, type_)

            val = None
            if isinstance(comp, SingleSelectComponent):
                val = comp.get_selected()
            elif isinstance(comp, TextInputComponent):
                val = comp.get_int_value()

            config_[prop] = val

        try:
            self.configman.save_config(config_)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def gen_custom_actions(self) -> Generator[CustomSoftwareAction, None, None]:
        if self._default_actions is None:
            self._default_actions = (CustomSoftwareAction(i18n_label_key='debian.action.sync_pkgs',
                                                          i18n_status_key='debian.task.sync_pkgs.status',
                                                          i18n_description_key='debian.action.sync_pkgs.desc',
                                                          icon_path=DEBIAN_ICON_PATH,
                                                          manager_method='synchronize_packages',
                                                          requires_root=True),
                                     CustomSoftwareAction(i18n_label_key='debian.action.index_apps',
                                                          i18n_status_key='debian.task.app_index.status',
                                                          i18n_description_key='debian.action.index_apps.desc',
                                                          icon_path=DEBIAN_ICON_PATH,
                                                          manager_method='index_apps',
                                                          requires_root=False)
                                     )

        yield from self._default_actions

        for _ in self.get_installed_source_apps():
            yield self.action_launch_sources
            break

    def _write_ignored_updates(self, packages: Iterable[str]):
        Path(os.path.dirname(self.file_ignored_updates)).mkdir(parents=True, exist_ok=True)

        with open(self.file_ignored_updates, 'w+') as f:
            f.write('\n'.join(n for n in sorted(packages)))

    def ignore_update(self, pkg: DebianPackage):
        ignored_packages = set()
        self._fill_ignored_updates(ignored_packages)

        if pkg.name not in ignored_packages:
            pkg.updates_ignored = True
            ignored_packages.add(pkg.name)
            self._write_ignored_updates(ignored_packages)

    def revert_ignored_update(self, pkg: DebianPackage):
        ignored_packages = set()
        self._fill_ignored_updates(ignored_packages)

        if pkg.name in ignored_packages:
            pkg.updates_ignored = False
            ignored_packages.remove(pkg.name)
            self._write_ignored_updates(ignored_packages)

    def synchronize_packages(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        return SynchronizePackages(i18n=self._i18n, logger=self._log, root_password=root_password, watcher=watcher,
                                   aptitude=self.aptitude, taskman=TaskManager()).run()

    def index_apps(self, root_password: Optional[str], watcher: Optional[ProcessWatcher],
                   taskman: Optional[TaskManager] = None, deb_config: Optional[dict] = None,
                   check_expiration: bool = False) -> bool:
        _config = deb_config if deb_config else self.configman.get_config()
        _taskman = taskman if taskman else TaskManager()

        map_apps = MapApplications(taskman=_taskman, app_indexer=self.app_indexer,
                                   i18n=self._i18n, logger=self._log, deb_config=deb_config,
                                   app_mapper=self.app_mapper, check_expiration=check_expiration,
                                   watcher=watcher)
        map_apps.start()

        gen_app_index = UpdateApplicationIndex(taskman=_taskman, app_indexer=self.app_indexer,
                                               i18n=self._i18n, logger=self._log,
                                               mapping_apps=map_apps)
        gen_app_index.start()

        map_apps.join()
        self._update_apps_index(map_apps.apps)
        gen_app_index.join()
        return True

    def purge(self, pkg: DebianPackage, root_password: str, watcher: ProcessWatcher) -> bool:
        if not self.view.confirm_purge(pkg.name, watcher):
            return False

        res = self.uninstall(pkg=pkg, root_password=root_password, watcher=watcher, disk_loader=None, purge=True)
        return res.success

    def launch_sources_app(self, root_password: str, watcher: ProcessWatcher) -> bool:
        deb_config = self.configman.get_config()

        sources_app = deb_config.get('pkg_sources.app')

        if isinstance(sources_app, str) and sources_app not in self.known_sources_apps:
            watcher.show_message(title=self._i18n['popup.title.error'],
                                 body=self._i18n['debian.action.sources.unsupported'].format(app=bold(sources_app)))
            return False

        if sources_app:
            if not which(sources_app):
                watcher.show_message(title=self._i18n['popup.title.error'],
                                     body=self._i18n['debian.action.sources.not_installed'],
                                     type_=MessageType.ERROR)
                return False

            Popen(sources_app, shell=True)
            return True

        for app in self.get_installed_source_apps():
            Popen(app, shell=True)
            return True

        watcher.show_message(title=self._i18n['popup.title.error'],
                             body=self._i18n['debian.action.sources.not_installed'],
                             type_=MessageType.ERROR)
        return False

    @property
    def app_indexer(self) -> ApplicationIndexer:
        if self._app_indexer is None:
            self._app_indexer = ApplicationIndexer(self._log)

        return self._app_indexer

    @property
    def apps_index(self) -> Dict[str, DebianApplication]:
        if self._apps_index is None:
            self._update_apps_index(self.app_indexer.read_index())

        return self._apps_index

    @property
    def install_show_attrs(self) -> Set[str]:
        if self._install_show_attrs is None:
            self._install_show_attrs = {'description', 'maintainer', 'section', 'compressed size'}

        return self._install_show_attrs

    @property
    def configman(self) -> DebianConfigManager:
        if self._configman is None:
            self._configman = DebianConfigManager()

        return self._configman

    @property
    def view(self) -> DebianViewBridge:
        if self._view is None:
            self._view = DebianViewBridge(screen_width=self.context.screen_width,
                                          screen_heigth=self.context.screen_height,
                                          i18n=self._i18n)

        return self._view

    @property
    def app_mapper(self) -> ApplicationsMapper:
        if self._app_mapper is None:
            self._app_mapper = ApplicationsMapper(logger=self._log)

        return self._app_mapper

    @property
    def aptitude(self) -> Aptitude:
        if self._aptitude is None:
            self._aptitude = Aptitude(self._log)

        return self._aptitude

    @property
    def output_handler(self) -> AptitudeOutputHandlerFactory:
        if self._output_handler is None:
            self._output_handler = AptitudeOutputHandlerFactory(i18n=self._i18n)

        return self._output_handler

    @property
    def action_launch_sources(self) -> CustomSoftwareAction:
        if self._action_launch_sources is None:
            self._action_launch_sources = CustomSoftwareAction(i18n_label_key='debian.action.sources',
                                                               i18n_status_key='debian.task.sources.status',
                                                               i18n_description_key='debian.action.sources.desc',
                                                               icon_path=DEBIAN_ICON_PATH,
                                                               manager_method='launch_sources_app',
                                                               requires_confirmation=False,
                                                               requires_root=False)

        return self._action_launch_sources

    @property
    def known_sources_apps(self) -> Tuple[str, ...]:
        if self._known_sources_apps is None:
            self._known_sources_apps = ('software-properties-gtk',)

        return self._known_sources_apps

    @property
    def file_ignored_updates(self) -> str:
        if self._file_ignored_updates is None:
            self._file_ignored_updates = f'{CONFIG_DIR}/debian/updates_ignored.txt'

        return self._file_ignored_updates

    @property
    def suggestions_downloader(self) -> DebianSuggestionsDownloader:
        if not self._suggestions_downloader:
            file_url = self.context.get_suggestion_url(self.__module__)
            self._suggestions_downloader = DebianSuggestionsDownloader(i18n=self._i18n, logger=self._log,
                                                                       http_client=self.context.http_client,
                                                                       file_url=file_url)

            if self._suggestions_downloader.is_local_suggestions_file():
                self._log.info(f"Local Debian suggestions file mapped: {file_url}")

        return self._suggestions_downloader

    def get_installed_source_apps(self) -> Generator[str, None, None]:
        for app in self.known_sources_apps:
            if shutil.which(app):
                yield app
