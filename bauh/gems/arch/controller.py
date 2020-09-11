import glob
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import traceback
from datetime import datetime
from math import floor
from pathlib import Path
from threading import Thread
from typing import List, Set, Type, Tuple, Dict, Iterable, Optional

import requests

from bauh.api.abstract.controller import SearchResult, SoftwareManager, ApplicationContext, UpgradeRequirements, \
    TransactionResult
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import PackageUpdate, PackageHistory, SoftwarePackage, PackageSuggestion, PackageStatus, \
    SuggestionPriority, CustomSoftwareAction
from bauh.api.abstract.view import MessageType, FormComponent, InputOption, SingleSelectComponent, SelectViewType, \
    ViewComponent, PanelComponent, MultipleSelectComponent, TextInputComponent, TextInputType, \
    FileChooserComponent, TextComponent
from bauh.api.constants import TEMP_DIR
from bauh.commons import user, internet, system
from bauh.commons.category import CategoriesDownloader
from bauh.commons.config import save_config
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, ProcessHandler, new_subprocess, run_cmd, SimpleProcess
from bauh.commons.view_utils import new_select
from bauh.gems.arch import aur, pacman, makepkg, message, confirmation, disk, git, \
    gpg, URL_CATEGORIES_FILE, CATEGORIES_FILE_PATH, CUSTOM_MAKEPKG_FILE, SUGGESTIONS_FILE, \
    CONFIG_FILE, get_icon_path, database, mirrors, sorting, cpu_manager, ARCH_CACHE_PATH, UPDATES_IGNORED_FILE, \
    CONFIG_DIR, EDITABLE_PKGBUILDS_FILE, URL_GPG_SERVERS, BUILD_DIR
from bauh.gems.arch.aur import AURClient
from bauh.gems.arch.config import read_config, get_build_dir
from bauh.gems.arch.dependencies import DependenciesAnalyser
from bauh.gems.arch.download import MultithreadedDownloadService, ArchDownloadException
from bauh.gems.arch.exceptions import PackageNotFoundException, PackageInHoldException
from bauh.gems.arch.mapper import ArchDataMapper
from bauh.gems.arch.model import ArchPackage
from bauh.gems.arch.output import TransactionStatusHandler
from bauh.gems.arch.pacman import RE_DEP_OPERATORS
from bauh.gems.arch.updates import UpdatesSummarizer
from bauh.gems.arch.worker import AURIndexUpdater, ArchDiskCacheUpdater, ArchCompilationOptimizer, SyncDatabases, \
    RefreshMirrors

URL_GIT = 'https://aur.archlinux.org/{}.git'
URL_PKG_DOWNLOAD = 'https://aur.archlinux.org/cgit/aur.git/snapshot/{}.tar.gz'
URL_SRC_INFO = 'https://aur.archlinux.org/cgit/aur.git/plain/.SRCINFO?h='

RE_SPLIT_VERSION = re.compile(r'([=><]+)')

SOURCE_FIELDS = ('source', 'source_x86_64')
RE_PRE_DOWNLOAD_WL_PROTOCOLS = re.compile(r'^(.+::)?(https?|ftp)://.+')
RE_PRE_DOWNLOAD_BL_EXT = re.compile(r'.+\.(git|gpg)$')
RE_PKGBUILD_PKGNAME = re.compile(r'pkgname\s*=.+')
RE_CONFLICT_DETECTED = re.compile(r'\n::\s*(.+)\s+are in conflict\s*.')
RE_DEPENDENCY_BREAKAGE = re.compile(r'\n?::\s+installing\s+(.+\s\(.+\))\sbreaks\sdependency\s\'(.+)\'\srequired\sby\s(.+)\s*', flags=re.IGNORECASE)


class TransactionContext:

    def __init__(self, name: str = None, base: str = None, maintainer: str = None, watcher: ProcessWatcher = None,
                 handler: ProcessHandler = None, dependency: bool = None, skip_opt_deps: bool = False, root_password: str = None,
                 build_dir: str = None, project_dir: str = None, change_progress: bool = False, arch_config: dict = None,
                 install_files: Set[str] = None, repository: str = None, pkg: ArchPackage = None,
                 remote_repo_map: Dict[str, str] = None, provided_map: Dict[str, Set[str]] = None,
                 remote_provided_map: Dict[str, Set[str]] = None, aur_idx: Set[str] = None,
                 missing_deps: List[Tuple[str, str]] = None, installed: Set[str] = None, removed: Dict[str, SoftwarePackage] = None,
                 disk_loader: DiskCacheLoader = None, disk_cache_updater: Thread = None,
                 new_pkg: bool = False, custom_pkgbuild_path: str = None,
                 pkgs_to_build: Set[str] = None):
        self.name = name
        self.base = base
        self.maintainer = maintainer
        self.watcher = watcher
        self.handler = handler
        self.dependency = dependency
        self.skip_opt_deps = skip_opt_deps
        self.build_dir = build_dir
        self.project_dir = project_dir
        self.root_password = root_password
        self.change_progress = change_progress
        self.repository = repository
        self.config = arch_config
        self.install_files = install_files
        self.pkg = pkg
        self.provided_map = provided_map
        self.remote_repo_map = remote_repo_map
        self.remote_provided_map = remote_provided_map
        self.aur_idx = aur_idx
        self.missing_deps = missing_deps
        self.installed = installed
        self.removed = removed
        self.disk_loader = disk_loader
        self.disk_cache_updater = disk_cache_updater
        self.pkgbuild_edited = False
        self.new_pkg = new_pkg
        self.custom_pkgbuild_path = custom_pkgbuild_path
        self.pkgs_to_build = pkgs_to_build
        self.previous_change_progress = change_progress

    @classmethod
    def gen_context_from(cls, pkg: ArchPackage, arch_config: dict, root_password: str, handler: ProcessHandler) -> "TransactionContext":
        return cls(name=pkg.name, base=pkg.get_base_name(), maintainer=pkg.maintainer, repository=pkg.repository,
                   arch_config=arch_config, watcher=handler.watcher, handler=handler, skip_opt_deps=True,
                   change_progress=True, root_password=root_password, dependency=False,
                   installed=set(), removed={}, new_pkg=not pkg.installed)

    def get_base_name(self):
        return self.base if self.base else self.name

    def get_project_dir(self):
        return self.project_dir or '.'

    def clone_base(self):
        return TransactionContext(watcher=self.watcher, handler=self.handler, root_password=self.root_password,
                                  arch_config=self.config, installed=set(), removed={})

    def gen_dep_context(self, name: str, repository: str):
        dep_context = self.clone_base()
        dep_context.name = name
        dep_context.repository = repository
        dep_context.dependency = True
        dep_context.change_progress = False
        dep_context.installed = set()
        dep_context.removed = {}
        return dep_context

    def has_install_files(self) -> bool:
        return bool(self.install_files)

    def get_packages_paths(self) -> Set[str]:
        return self.install_files if self.install_files else {self.name}

    def get_package_names(self) -> Set[str]:
        return self.pkgs_to_build if (self.pkgs_to_build and self.install_files) else {self.name}

    def get_version(self) -> str:
        return self.pkg.version if self.pkg else None

    def get_aur_idx(self, aur_client: AURClient) -> Set[str]:
        if self.aur_idx is None:
            if self.config['aur']:
                self.aur_idx = aur_client.read_index()
            else:
                self.aur_idx = set()

        return self.aur_idx

    def get_provided_map(self) -> Dict[str, Set[str]]:
        if self.provided_map is None:
            self.provided_map = pacman.map_provided()

        return self.provided_map

    def get_remote_provided_map(self) -> Dict[str, Set[str]]:
        if self.remote_provided_map is None:
            self.remote_provided_map = pacman.map_provided(remote=True)

        return self.remote_provided_map

    def get_remote_repo_map(self) -> Dict[str, str]:
        if self.remote_repo_map is None:
            self.remote_repo_map = pacman.map_repositories()

        return self.remote_repo_map

    def disable_progress_if_changing(self):
        if self.change_progress:
            self.previous_change_progress = True
            self.change_progress = False

    def restabilish_progress(self):
        if self.previous_change_progress is not None:
            self.change_progress = self.previous_change_progress

        self.previous_change_progress = self.change_progress


class ArchManager(SoftwareManager):

    def __init__(self, context: ApplicationContext, disk_cache_updater: ArchDiskCacheUpdater = None):
        super(ArchManager, self).__init__(context=context)
        self.aur_cache = context.cache_factory.new()
        # context.disk_loader_factory.map(ArchPackage, self.aur_cache) TODO

        self.mapper = ArchDataMapper(http_client=context.http_client, i18n=context.i18n)
        self.i18n = context.i18n
        self.aur_client = AURClient(http_client=context.http_client, logger=context.logger, x86_64=context.is_system_x86_64())
        self.dcache_updater = None
        self.logger = context.logger
        self.enabled = True
        self.arch_distro = context.distro == 'arch'
        self.categories = {}
        self.deps_analyser = DependenciesAnalyser(self.aur_client, self.i18n)
        self.http_client = context.http_client
        self.custom_actions = {
            'sys_up': CustomSoftwareAction(i18n_label_key='arch.custom_action.upgrade_system',
                                           i18n_status_key='arch.custom_action.upgrade_system.status',
                                           manager_method='upgrade_system',
                                           icon_path=get_icon_path(),
                                           requires_root=True,
                                           backup=True,
                                           manager=self),
            'ref_dbs': CustomSoftwareAction(i18n_label_key='arch.custom_action.refresh_dbs',
                                            i18n_status_key='arch.sync_databases.substatus',
                                            manager_method='sync_databases',
                                            icon_path=get_icon_path(),
                                            requires_root=True,
                                            manager=self),
            'ref_mirrors': CustomSoftwareAction(i18n_label_key='arch.custom_action.refresh_mirrors',
                                                i18n_status_key='arch.task.mirrors',
                                                manager_method='refresh_mirrors',
                                                icon_path=get_icon_path(),
                                                requires_root=True,
                                                manager=self),
            'clean_cache': CustomSoftwareAction(i18n_label_key='arch.custom_action.clean_cache',
                                                i18n_status_key='arch.custom_action.clean_cache.status',
                                                manager_method='clean_cache',
                                                icon_path=get_icon_path(),
                                                requires_root=True,
                                                refresh=False,
                                                manager=self),
            'setup_snapd': CustomSoftwareAction(i18n_label_key='arch.custom_action.setup_snapd',
                                                i18n_status_key='arch.custom_action.setup_snapd.status',
                                                manager_method='setup_snapd',
                                                icon_path=get_icon_path(),
                                                requires_root=False,
                                                refresh=False,
                                                manager=self),
        }
        self.index_aur = None
        self.re_file_conflict = re.compile(r'[\w\d\-_.]+:')
        self.disk_cache_updater = disk_cache_updater

    @staticmethod
    def get_semantic_search_map() -> Dict[str, str]:
        return {'google chrome': 'google-chrome',
                'chrome google': 'google-chrome',
                'googlechrome': 'google-chrome'}

    def refresh_mirrors(self, root_password: str, watcher: ProcessWatcher) -> bool:
        handler = ProcessHandler(watcher)

        if self._is_database_locked(handler, root_password):
            return False

        available_countries = pacman.list_mirror_countries()
        current_countries = pacman.get_current_mirror_countries()

        if not available_countries:
            self.logger.warning("No country available")
            countries = current_countries
        else:
            country_opts = [InputOption(label=self.i18n['arch.custom_action.refresh_mirrors.location.all'], value='all',
                                        tooltip=self.i18n['arch.custom_action.refresh_mirrors.location.all.tip'])]
            mapped_opts = [InputOption(label=' '.join((w.capitalize() for w in self.i18n[' '.join(c.split('_'))].split(' '))),
                                       value=c) for c in available_countries]
            mapped_opts.sort(key=lambda o: o.label)

            if len(current_countries) == 1 and current_countries[0] == 'all':
                default_opts = {country_opts[0]}
            else:
                default_opts = {o for o in mapped_opts if o.value in current_countries}
                country_opts.extend(default_opts)

            country_opts.extend((o for o in mapped_opts if o not in default_opts))

            select = MultipleSelectComponent(options=country_opts,
                                             default_options=default_opts,
                                             max_per_line=3,
                                             label=self.i18n['arch.custom_action.refresh_mirrors.select_label'])

            if watcher.request_confirmation(title=self.i18n['arch.custom_action.refresh_mirrors'],
                                            body=None,
                                            components=[select],
                                            confirmation_label=self.i18n['continue'].capitalize(),
                                            deny_label=self.i18n["cancel"].capitalize()):
                countries = select.get_selected_values()

                if 'all' in countries or len(countries) == len(available_countries):
                    countries = ['all']
            else:
                watcher.print("Aborted by the user")
                return False

        watcher.change_substatus(self.i18n['arch.custom_action.refresh_mirrors.status.updating'])

        if current_countries == countries:
            success, output = handler.handle_simple(pacman.refresh_mirrors(root_password))
        else:
            success, output = handler.handle_simple(pacman.update_mirrors(root_password, countries))

        if not success:
            watcher.show_message(title=self.i18n["action.failed"].capitalize(),
                                 body=self.i18n['arch.custom_action.refresh_mirrors.failed'],
                                 type_=MessageType.ERROR)
            return False

        sort_limit = read_config()['mirrors_sort_limit']

        if sort_limit is not None and isinstance(sort_limit, int) and sort_limit >= 0:
            watcher.change_substatus(self.i18n['arch.custom_action.refresh_mirrors.status.sorting'])
            handler.handle_simple(pacman.sort_fastest_mirrors(root_password, sort_limit))

        mirrors.register_sync(self.logger)

        watcher.change_substatus(self.i18n['arch.sync_databases.substatus'])
        return self.sync_databases(root_password=root_password, watcher=watcher)

    def sync_databases(self, root_password: str, watcher: ProcessWatcher) -> bool:
        handler = ProcessHandler(watcher)

        if self._is_database_locked(handler, root_password):
            return False

        success, output = handler.handle_simple(pacman.sync_databases(root_password, force=True))

        if not success:
            watcher.show_message(title=self.i18n["action.failed"].capitalize(),
                                 body=self.i18n['arch.custom_action.refresh_mirrors.failed'],
                                 type_=MessageType.ERROR)
            return False

        database.register_sync(self.logger)
        return True

    def _upgrade_search_result(self, apidata: dict, installed_pkgs: Dict[str, ArchPackage], downgrade_enabled: bool, res: SearchResult, disk_loader: DiskCacheLoader):
        pkg = installed_pkgs.get(apidata['Name'])

        if not pkg:
            pkg = self.mapper.map_api_data(apidata, None, self.categories)
            pkg.downgrade_enabled = downgrade_enabled

        if pkg.installed:
            res.installed.append(pkg)
        else:
            res.new.append(pkg)

        Thread(target=self.mapper.fill_package_build, args=(pkg,), daemon=True).start()

    def _search_in_repos_and_fill(self, words: str, disk_loader: DiskCacheLoader, read_installed: Thread, installed: List[ArchPackage], res: SearchResult):
        repo_search = pacman.search(words)

        if not repo_search:  # the package may not be mapped on the databases anymore
            pkgname = words.split(' ')[0].strip()
            pkg_found = pacman.get_info_dict(pkgname, remote=False)

            if pkg_found and pkg_found['validated by']:
                repo_search = {pkgname: {'version': pkg_found.get('version'),
                                         'repository': 'unknown',
                                         'description': pkg_found.get('description')}}

        if repo_search:
            repo_pkgs = []
            for name, data in repo_search.items():
                pkg = ArchPackage(name=name, i18n=self.i18n, **data)
                pkg.downgrade_enabled = True
                repo_pkgs.append(pkg)

            if repo_pkgs:
                read_installed.join()

                repo_installed = {p.name: p for p in installed if p.repository != 'aur'} if installed else {}

                for pkg in repo_pkgs:
                    pkg_installed = repo_installed.get(pkg.name)
                    if pkg_installed:
                        res.installed.append(pkg_installed)
                    else:
                        pkg.installed = False
                        res.new.append(pkg)

    def _search_in_aur_and_fill(self, words: str, disk_loader: DiskCacheLoader, read_installed: Thread, installed: List[ArchPackage], res: SearchResult):
        api_res = self.aur_client.search(words)

        if api_res and api_res.get('results'):
            read_installed.join()
            aur_installed = {p.name: p for p in installed if p.repository == 'aur'}

            downgrade_enabled = git.is_enabled()
            for pkgdata in api_res['results']:
                self._upgrade_search_result(pkgdata, aur_installed, downgrade_enabled, res, disk_loader)

        else:  # if there are no results from the API (it could be because there were too many), tries the names index:
            if self.index_aur:
                self.index_aur.join()

            aur_index = self.aur_client.read_local_index()
            if aur_index:
                self.logger.info("Querying through the local AUR index")
                to_query = set()
                for norm_name, real_name in aur_index.items():
                    if words in norm_name:
                        to_query.add(real_name)

                    if len(to_query) == 25:
                        break

                pkgsinfo = self.aur_client.get_info(to_query)

                if pkgsinfo:
                    read_installed.join()
                    aur_installed = {p.name: p for p in installed if p.repository == 'aur'}
                    downgrade_enabled = git.is_enabled()

                    for pkgdata in pkgsinfo:
                        self._upgrade_search_result(pkgdata, aur_installed, downgrade_enabled, res, disk_loader)

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        if is_url:
            return SearchResult([], [], 0)

        arch_config = read_config()

        if not any([arch_config['repositories'], arch_config['aur']]):
            return SearchResult([], [], 0)

        installed = []
        read_installed = Thread(target=lambda: installed.extend(self.read_installed(disk_loader=disk_loader,
                                                                                    only_apps=False,
                                                                                    limit=-1,
                                                                                    internet_available=True).installed), daemon=True)
        read_installed.start()

        res = SearchResult([], [], 0)

        if not any((arch_config['aur'], arch_config['repositories'])):
            return res

        mapped_words = self.get_semantic_search_map().get(words)
        final_words = mapped_words or words

        aur_search = None
        if arch_config['aur']:
            aur_search = Thread(target=self._search_in_aur_and_fill, args=(final_words, disk_loader, read_installed, installed, res), daemon=True)
            aur_search.start()

        if arch_config['repositories']:
            self._search_in_repos_and_fill(final_words, disk_loader, read_installed, installed, res)

        if aur_search:
            aur_search.join()

        res.total = len(res.installed) + len(res.new)
        return res

    def _fill_aur_pkgs(self, aur_pkgs: dict, output: List[ArchPackage], disk_loader: DiskCacheLoader, internet_available: bool,
                       arch_config: dict):
        downgrade_enabled = git.is_enabled()

        if internet_available:
            try:
                pkgsinfo = self.aur_client.get_info(aur_pkgs.keys())

                if pkgsinfo:
                    editable_pkgbuilds = self._read_editable_pkgbuilds() if arch_config['edit_aur_pkgbuild'] is not False else None
                    for pkgdata in pkgsinfo:
                        pkg = self.mapper.map_api_data(pkgdata, aur_pkgs, self.categories)
                        pkg.downgrade_enabled = downgrade_enabled
                        pkg.pkgbuild_editable = pkg.name in editable_pkgbuilds if editable_pkgbuilds is not None else None

                        if disk_loader:
                            disk_loader.fill(pkg)
                            pkg.status = PackageStatus.READY

                        output.append(pkg)

                    return

            except requests.exceptions.ConnectionError:
                self.logger.warning('Could not retrieve installed AUR packages API data. It seems the internet connection is off.')
                self.logger.info("Reading only local AUR packages data")

        editable_pkgbuilds = self._read_editable_pkgbuilds() if arch_config['edit_aur_pkgbuild'] is not False else None
        for name, data in aur_pkgs.items():
            pkg = ArchPackage(name=name, version=data.get('version'),
                              latest_version=data.get('version'), description=data.get('description'),
                              installed=True, repository='aur', i18n=self.i18n)

            pkg.categories = self.categories.get(pkg.name)
            pkg.downgrade_enabled = downgrade_enabled
            pkg.pkgbuild_editable = pkg.name in editable_pkgbuilds if editable_pkgbuilds is not None else None

            if disk_loader:
                disk_loader.fill(pkg)
                pkg.status = PackageStatus.READY

            output.append(pkg)

    def _fill_repo_updates(self, updates: dict):
        updates.update(pacman.list_repository_updates())

    def _fill_repo_pkgs(self, repo_pkgs: dict, pkgs: list, disk_loader: DiskCacheLoader):
        updates = {}

        thread_updates = Thread(target=self._fill_repo_updates, args=(updates,), daemon=True)
        thread_updates.start()

        repo_map = pacman.map_repositories(repo_pkgs)
        if len(repo_map) != len(repo_pkgs):
            self.logger.warning("Not mapped all signed packages repositories. Mapped: {}. Total: {}".format(len(repo_map), len(repo_pkgs)))

        thread_updates.join()

        self.logger.info("Repository updates found" if updates else "No repository updates found")

        for name, data in repo_pkgs.items():
            pkgversion = data.get('version')
            pkgrepo = repo_map.get(name)
            pkg = ArchPackage(name=name,
                              version=pkgversion,
                              latest_version=pkgversion,
                              description=data.get('description'),
                              maintainer=pkgrepo,
                              i18n=self.i18n,
                              installed=True,
                              repository=pkgrepo,
                              categories=self.categories.get(name))
            pkg.downgrade_enabled = False

            if updates:
                update_version = updates.get(pkg.name)

                if update_version:
                    pkg.latest_version = update_version
                    pkg.update = True

            if disk_loader:
                disk_loader.fill(pkg)

            pkgs.append(pkg)

    def _wait_for_disk_cache(self):
        if self.disk_cache_updater and self.disk_cache_updater.is_alive():
            self.logger.info("Waiting for disk cache to be ready")
            self.disk_cache_updater.join()
            self.logger.info("Disk cache ready")

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None, names: Iterable[str] = None, wait_disk_cache: bool = True) -> SearchResult:
        self.aur_client.clean_caches()
        arch_config = read_config()

        installed = pacman.map_installed(names=names)

        aur_pkgs, repo_pkgs = None, None

        if arch_config['repositories'] and installed['signed']:
            repo_pkgs = installed['signed']

        if installed['not_signed']:
            if self.index_aur:
                self.index_aur.join()

            aur_index = self.aur_client.read_index()

            for pkg in {*installed['not_signed']}:
                if pkg not in aur_index:
                    if repo_pkgs is not None:
                        repo_pkgs[pkg] = installed['not_signed'][pkg]

                    if arch_config['aur']:
                        del installed['not_signed'][pkg]

            if arch_config['aur']:
                aur_pkgs = installed['not_signed']

        pkgs = []
        if repo_pkgs or aur_pkgs:
            if wait_disk_cache:
                self._wait_for_disk_cache()

            map_threads = []

            if aur_pkgs:
                t = Thread(target=self._fill_aur_pkgs, args=(aur_pkgs, pkgs, disk_loader, internet_available, arch_config), daemon=True)
                t.start()
                map_threads.append(t)

            if repo_pkgs:
                t = Thread(target=self._fill_repo_pkgs, args=(repo_pkgs, pkgs, disk_loader), daemon=True)
                t.start()
                map_threads.append(t)

            for t in map_threads:
                t.join()

        if pkgs:
            ignored = self._list_ignored_updates()

            if ignored:
                for p in pkgs:
                    if p.name in ignored:
                        p.update_ignored = True

        return SearchResult(pkgs, None, len(pkgs))

    def _downgrade_aur_pkg(self, context: TransactionContext):
        context.build_dir = '{}/build_{}'.format(get_build_dir(context.config), int(time.time()))

        try:
            if not os.path.exists(context.build_dir):
                build_dir = context.handler.handle(SystemProcess(new_subprocess(['mkdir', '-p', context.build_dir])))

                if build_dir:
                    context.handler.watcher.change_progress(10)
                    base_name = context.get_base_name()
                    context.watcher.change_substatus(self.i18n['arch.clone'].format(bold(context.name)))
                    clone = context.handler.handle(SystemProcess(subproc=new_subprocess(['git', 'clone', URL_GIT.format(base_name)],
                                                                 cwd=context.build_dir), check_error_output=False))
                    context.watcher.change_progress(30)
                    if clone:
                        context.watcher.change_substatus(self.i18n['arch.downgrade.reading_commits'])
                        clone_path = '{}/{}'.format(context.build_dir, base_name)
                        context.project_dir = clone_path
                        srcinfo_path = '{}/.SRCINFO'.format(clone_path)

                        commits = run_cmd("git log", cwd=clone_path)
                        context.watcher.change_progress(40)

                        if commits:
                            commit_list = re.findall(r'commit (.+)\n', commits)
                            if commit_list:
                                if len(commit_list) > 1:
                                    srcfields = {'pkgver', 'pkgrel'}

                                    commit_found = None
                                    for idx in range(1, len(commit_list)):
                                        commit = commit_list[idx]
                                        with open(srcinfo_path) as f:
                                            pkgsrc = aur.map_srcinfo(string=f.read(), pkgname=context.name ,fields=srcfields)

                                        reset_proc = new_subprocess(['git', 'reset', '--hard', commit], cwd=clone_path)
                                        if not context.handler.handle(SystemProcess(reset_proc, check_error_output=False)):
                                            context.handler.watcher.print('Could not downgrade anymore. Aborting...')
                                            return False

                                        if '{}-{}'.format(pkgsrc.get('pkgver'), pkgsrc.get('pkgrel')) == context.get_version():
                                            # current version found
                                            commit_found = commit
                                        elif commit_found:
                                            context.watcher.change_substatus(self.i18n['arch.downgrade.version_found'])
                                            checkout_proc = new_subprocess(['git', 'checkout', commit_found], cwd=clone_path)
                                            if not context.handler.handle(SystemProcess(checkout_proc, check_error_output=False)):
                                                context.watcher.print("Could not rollback to current version's commit")
                                                return False

                                            reset_proc = new_subprocess(['git', 'reset', '--hard', commit_found], cwd=clone_path)
                                            if not context.handler.handle(SystemProcess(reset_proc, check_error_output=False)):
                                                context.watcher.print("Could not downgrade to previous commit of '{}'. Aborting...".format(commit_found))
                                                return False

                                            break

                                    context.watcher.change_substatus(self.i18n['arch.downgrade.install_older'])
                                    return self._build(context)
                                else:
                                    context.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                                                 body=self.i18n['arch.downgrade.impossible'].format(context.name),
                                                                 type_=MessageType.ERROR)
                                    return False

                        context.watcher.show_message(title=self.i18n['error'],
                                                     body=self.i18n['arch.downgrade.no_commits'],
                                                     type_=MessageType.ERROR)
                        return False

        finally:
            if os.path.exists(context.build_dir) and context.config['aur_remove_build_dir']:
                context.handler.handle(SystemProcess(subproc=new_subprocess(['rm', '-rf', context.build_dir])))

        return False

    def _downgrade_repo_pkg(self, context: TransactionContext):
        context.watcher.change_substatus(self.i18n['arch.downgrade.searching_stored'])
        if not os.path.isdir('/var/cache/pacman/pkg'):
            context.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                         body=self.i18n['arch.downgrade.repo_pkg.no_versions'],
                                         type_=MessageType.ERROR)
            return False

        available_files = glob.glob("/var/cache/pacman/pkg/{}-*.pkg.tar.*".format(context.name))

        if not available_files:
            context.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                         body=self.i18n['arch.downgrade.repo_pkg.no_versions'],
                                         type_=MessageType.ERROR)
            return False

        reg = re.compile(r'{}-([\w.\-]+)-(x86_64|any|i686).pkg'.format(context.name))

        versions, version_files = [], {}
        for file_path in available_files:
            found = reg.findall(os.path.basename(file_path))

            if found:
                ver = found[0][0]
                if ver not in versions and ver < context.get_version():
                    versions.append(ver)
                    version_files[ver] = file_path

        context.watcher.change_progress(40)
        if not versions:
            context.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                         body=self.i18n['arch.downgrade.repo_pkg.no_versions'],
                                         type_=MessageType.ERROR)
            return False

        versions.sort(reverse=True)

        context.watcher.change_progress(50)

        context.install_files = version_files[versions[0]]  # TODO verify
        if not self._handle_missing_deps(context=context):
            return False

        context.watcher.change_substatus(self.i18n['arch.downgrade.install_older'])
        context.watcher.change_progress(60)

        return self._install(context)

    def downgrade(self, pkg: ArchPackage, root_password: str, watcher: ProcessWatcher) -> bool:
        self.aur_client.clean_caches()
        if not self._check_action_allowed(pkg, watcher):
            return False

        handler = ProcessHandler(watcher)

        if self._is_database_locked(handler, root_password):
            return False

        context = TransactionContext(name=pkg.name, base=pkg.get_base_name(), skip_opt_deps=True,
                                     change_progress=True, dependency=False, repository=pkg.repository, pkg=pkg,
                                     arch_config=read_config(), watcher=watcher, handler=handler, root_password=root_password,
                                     installed=set(), removed={})

        self._sync_databases(context.config, root_password, handler)

        watcher.change_progress(5)

        if pkg.repository == 'aur':
            return self._downgrade_aur_pkg(context)
        else:
            return self._downgrade_repo_pkg(context)

    def clean_cache_for(self, pkg: ArchPackage):
        if os.path.exists(pkg.get_disk_cache_path()):
            shutil.rmtree(pkg.get_disk_cache_path())

    def _check_action_allowed(self, pkg: ArchPackage, watcher: ProcessWatcher) -> bool:
        if user.is_root() and pkg.repository == 'aur':
            watcher.show_message(title=self.i18n['arch.install.aur.root_error.title'],
                                 body=self.i18n['arch.install.aur.root_error.body'],
                                 type_=MessageType.ERROR)
            return False
        return True

    def _is_database_locked(self, handler: ProcessHandler, root_password: str) -> bool:
        if os.path.exists('/var/lib/pacman/db.lck'):
            handler.watcher.print('pacman database is locked')
            msg = '<p>{}</p><p>{}</p><br/>'.format(self.i18n['arch.action.db_locked.body.l1'],
                                                   self.i18n['arch.action.db_locked.body.l2'])
            if handler.watcher.request_confirmation(title=self.i18n['arch.action.db_locked.title'].capitalize(),
                                                    body=msg,
                                                    confirmation_label=self.i18n['arch.action.db_locked.confirmation'].capitalize(),
                                                    deny_label=self.i18n['cancel'].capitalize()):

                try:
                    if not handler.handle_simple(SimpleProcess(['rm', '-rf', '/var/lib/pacman/db.lck'], root_password=root_password)):
                        handler.watcher.show_message(title=self.i18n['error'].capitalize(),
                                                     body=self.i18n['arch.action.db_locked.error'],
                                                     type_=MessageType.ERROR)
                        return True
                except:
                    self.logger.error("An error occurred while removing the pacman database lock")
                    traceback.print_exc()
                    handler.watcher.show_message(title=self.i18n['error'].capitalize(),
                                                 body=self.i18n['arch.action.db_locked.error'],
                                                 type_=MessageType.ERROR)
                    return True
            else:
                handler.watcher.print('Action cancelled by the user. Aborting...')
                return True

        return False

    def _map_conflicting_file(self, output: str) -> List[MultipleSelectComponent]:
        error_idx = None
        lines = output.split('\n')
        for idx, l in enumerate(lines):
            if l and l.strip().lower().startswith('error: failed to commit transaction (conflicting files)'):
                error_idx = idx
                break

        files = []

        if error_idx and error_idx + 1 < len(lines):
            for idx in range(error_idx + 1, len(lines)):
                line = lines[idx].strip()

                if line and self.re_file_conflict.match(line):
                    files.append(InputOption(label=line, value=idx, read_only=True))

        return [MultipleSelectComponent(options=files, default_options={*files}, label='')]

    def _map_dependencies_breakage(self, output: str) -> List[ViewComponent]:
        errors = RE_DEPENDENCY_BREAKAGE.findall(output)

        if errors:
            opts = []

            for idx, err in enumerate(errors):
                opts.append(InputOption(label=self.i18n['arch.upgrade.error.dep_breakage.item'].format(*err), value=idx, read_only=True))

            return [MultipleSelectComponent(label='',
                                            options=opts,
                                            default_options={*opts})]
        else:
            return [TextComponent(output)]

    def list_related(self, pkgs: Iterable[str], all_pkgs: Iterable[str], data: Dict[str, dict], related: Set[str], provided_map: Dict[str, Set[str]]) -> Set[str]:
        related.update(pkgs)

        deps = set()

        for pkg in pkgs:
            pkg_deps = data[pkg]['d']

            if pkg_deps:
                deps.update({d for d in pkg_deps if d not in related})

        if deps:
            if not provided_map:
                for p in all_pkgs:
                    for provided in data[p].get('p', {p}):
                        sources = provided_map.get(provided, set())
                        provided_map[provided] = sources
                        sources.add(p)

            added_sources = set()
            for dep in deps:
                sources = provided_map.get(dep)

                if sources:
                    for source in sources:
                        if source not in related:
                            related.add(source)
                            added_sources.add(source)

            if added_sources:
                self.list_related(added_sources, all_pkgs, data, related, provided_map)

        return related

    def _upgrade_repo_pkgs(self, to_upgrade: List[str], to_remove: Optional[Set[str]], handler: ProcessHandler, root_password: str,
                           multithread_download: bool, pkgs_data: Dict[str, dict], overwrite_files: bool = False,
                           status_handler: TransactionStatusHandler = None, sizes: Dict[str, int] = None, download: bool = True,
                           check_syncfirst: bool = True, skip_dependency_checks: bool = False) -> bool:
        self.logger.info("Total packages to upgrade: {}".format(len(to_upgrade)))

        to_sync_first = None
        if check_syncfirst:
            to_sync_first = [p for p in pacman.get_packages_to_sync_first() if p.endswith('-keyring') and p in to_upgrade]
            self.logger.info("Packages detected to upgrade firstly: {}".format(len(to_sync_first)))

            if to_sync_first:
                self.logger.info("Upgrading keyrings marked as 'SyncFirst'")
                if not self._upgrade_repo_pkgs(to_upgrade=to_sync_first,
                                               to_remove=None,
                                               handler=handler,
                                               root_password=root_password,
                                               sizes=sizes,
                                               download=True,
                                               multithread_download=multithread_download,
                                               pkgs_data=pkgs_data,
                                               check_syncfirst=False):
                    return False

        to_upgrade_remaining = [p for p in to_upgrade if p not in to_sync_first] if to_sync_first else to_upgrade
        self.logger.info("Packages remaining to upgrade: {}".format(len(to_upgrade_remaining)))

        # pre-downloading all packages before removing any
        if download and to_upgrade_remaining:
            try:
                downloaded = self._download_packages(pkgnames=to_upgrade_remaining,
                                                     handler=handler,
                                                     root_password=root_password,
                                                     sizes=sizes,
                                                     multithreaded=multithread_download)

                if downloaded < len(to_upgrade_remaining):
                    self._show_upgrade_download_failed(handler.watcher)
                    return False

            except ArchDownloadException:
                self._show_upgrade_download_failed(handler.watcher)
                return False

        if to_remove and not self._remove_transaction_packages(to_remove, handler, root_password):
            return False

        if not to_upgrade_remaining:
            return True

        try:
            if status_handler:
                output_handler = status_handler
            else:
                output_handler = TransactionStatusHandler(handler.watcher, self.i18n, {*to_upgrade_remaining}, self.logger, downloading=len(to_upgrade_remaining))
                output_handler.start()

            self.logger.info("Upgrading {} repository packages: {}".format(len(to_upgrade_remaining), ', '.join(to_upgrade_remaining)))
            success, upgrade_output = handler.handle_simple(pacman.upgrade_several(pkgnames=to_upgrade_remaining,
                                                                                   root_password=root_password,
                                                                                   overwrite_conflicting_files=overwrite_files,
                                                                                   skip_dependency_checks=skip_dependency_checks),
                                                            output_handler=output_handler.handle)
            handler.watcher.change_substatus('')

            if success:
                output_handler.stop_working()
                output_handler.join()
                handler.watcher.print("Repository packages successfully upgraded")
                handler.watcher.change_substatus(self.i18n['arch.upgrade.caching_pkgs_data'])
                repo_map = pacman.map_repositories(to_upgrade_remaining)

                pkg_map = {}
                for name in to_upgrade_remaining:
                    repo = repo_map.get(name)
                    pkg_map[name] = ArchPackage(name=name,
                                                repository=repo,
                                                maintainer=repo,
                                                categories=self.categories.get(name))

                disk.write_several(pkgs=pkg_map, overwrite=True, maintainer=None)
                return True
            elif 'conflicting files' in upgrade_output:
                if not handler.watcher.request_confirmation(title=self.i18n['warning'].capitalize(),
                                                            body=self.i18n['arch.upgrade.error.conflicting_files'] + ':',
                                                            deny_label=self.i18n['arch.upgrade.conflicting_files.proceed'],
                                                            confirmation_label=self.i18n['arch.upgrade.conflicting_files.stop'],
                                                            components=self._map_conflicting_file(upgrade_output)):

                    return self._upgrade_repo_pkgs(to_upgrade=to_upgrade_remaining,
                                                   handler=handler,
                                                   root_password=root_password,
                                                   overwrite_files=True,
                                                   status_handler=output_handler,
                                                   multithread_download=multithread_download,
                                                   download=False,
                                                   check_syncfirst=False,
                                                   pkgs_data=pkgs_data,
                                                   to_remove=None,
                                                   sizes=sizes,
                                                   skip_dependency_checks=skip_dependency_checks)
                else:
                    output_handler.stop_working()
                    output_handler.join()
                    handler.watcher.print("Aborted by the user")
                    return False
            elif ' breaks dependency ' in upgrade_output:
                if not handler.watcher.request_confirmation(title=self.i18n['warning'].capitalize(),
                                                            body=self.i18n['arch.upgrade.error.dep_breakage'] + ':',
                                                            deny_label=self.i18n['arch.upgrade.error.dep_breakage.proceed'],
                                                            confirmation_label=self.i18n['arch.upgrade.error.dep_breakage.stop'],
                                                            components=self._map_dependencies_breakage(upgrade_output)):
                    return self._upgrade_repo_pkgs(to_upgrade=to_upgrade_remaining,
                                                   handler=handler,
                                                   root_password=root_password,
                                                   overwrite_files=overwrite_files,
                                                   status_handler=output_handler,
                                                   multithread_download=multithread_download,
                                                   download=False,
                                                   check_syncfirst=False,
                                                   pkgs_data=pkgs_data,
                                                   to_remove=None,
                                                   sizes=sizes,
                                                   skip_dependency_checks=True)
                else:
                    output_handler.stop_working()
                    output_handler.join()
                    handler.watcher.print("Aborted by the user")
                    return False
            else:
                output_handler.stop_working()
                output_handler.join()
                self.logger.error("'pacman' returned an unexpected response or error phrase after upgrading the repository packages")
                return False
        except:
            handler.watcher.change_substatus('')
            handler.watcher.print("An error occurred while upgrading repository packages")
            self.logger.error("An error occurred while upgrading repository packages")
            traceback.print_exc()
            return False

    def _remove_transaction_packages(self, to_remove: Set[str], handler: ProcessHandler, root_password: str) -> bool:
        output_handler = TransactionStatusHandler(watcher=handler.watcher,
                                                  i18n=self.i18n,
                                                  names=set(),
                                                  logger=self.logger,
                                                  pkgs_to_remove=len(to_remove))
        output_handler.start()
        try:
            success, _ = handler.handle_simple(pacman.remove_several(pkgnames=to_remove,
                                                                     root_password=root_password,
                                                                     skip_checks=True),
                                               output_handler=output_handler.handle)

            if not success:
                self.logger.error("Could not remove packages: {}".format(', '.join(to_remove)))
                output_handler.stop_working()
                output_handler.join()
                return False

            return True
        except:
            self.logger.error("An error occured while removing packages: {}".format(', '.join(to_remove)))
            traceback.print_exc()
            output_handler.stop_working()
            output_handler.join()
            return False

    def _show_upgrade_download_failed(self, watcher: ProcessWatcher):
        watcher.show_message(title=self.i18n['error'].capitalize(),
                             body=self.i18n['arch.upgrade.mthreaddownload.fail'],
                             type_=MessageType.ERROR)

    def upgrade(self, requirements: UpgradeRequirements, root_password: str, watcher: ProcessWatcher) -> bool:
        self.aur_client.clean_caches()
        watcher.change_status("{}...".format(self.i18n['manage_window.status.upgrading']))

        handler = ProcessHandler(watcher)

        if self._is_database_locked(handler, root_password):
            watcher.change_substatus('')
            return False

        aur_pkgs, repo_pkgs, pkg_sizes = [], [], {}

        for req in (*requirements.to_install, *requirements.to_upgrade):
            if req.pkg.repository == 'aur':
                aur_pkgs.append(req.pkg)
            else:
                repo_pkgs.append(req.pkg)

            pkg_sizes[req.pkg.name] = req.required_size

        if aur_pkgs and not self._check_action_allowed(aur_pkgs[0], watcher):
            return False

        arch_config = read_config()
        self._sync_databases(arch_config=arch_config, root_password=root_password, handler=handler)

        if repo_pkgs:
            if not self._upgrade_repo_pkgs(to_upgrade=[p.name for p in repo_pkgs],
                                           to_remove={r.pkg.name for r in requirements.to_remove} if requirements.to_remove else None,
                                           handler=handler,
                                           root_password=root_password,
                                           multithread_download=self._multithreaded_download_enabled(arch_config),
                                           pkgs_data=requirements.context['data'],
                                           sizes=pkg_sizes):
                return False

        elif requirements.to_remove and not self._remove_transaction_packages({r.pkg.name for r in requirements.to_remove}, handler, root_password):
            return False

        if aur_pkgs:
            watcher.change_status('{}...'.format(self.i18n['arch.upgrade.upgrade_aur_pkgs']))
            for pkg in aur_pkgs:
                watcher.change_substatus("{} {} ({})...".format(self.i18n['manage_window.status.upgrading'], pkg.name, pkg.version))
                context = TransactionContext.gen_context_from(pkg=pkg, arch_config=arch_config,
                                                              root_password=root_password, handler=handler)
                context.change_progress = False

                try:
                    if not self.install(pkg=pkg, root_password=root_password, watcher=watcher, disk_loader=None, context=context).success:
                        watcher.print(self.i18n['arch.upgrade.fail'].format('"{}"'.format(pkg.name)))
                        self.logger.error("Could not upgrade AUR package '{}'".format(pkg.name))
                        watcher.change_substatus('')
                        return False
                    else:
                        watcher.print(self.i18n['arch.upgrade.success'].format('"{}"'.format(pkg.name)))
                except:
                    watcher.print(self.i18n['arch.upgrade.fail'].format('"{}"'.format(pkg.name)))
                    watcher.change_substatus('')
                    self.logger.error("An error occurred when upgrading AUR package '{}'".format(pkg.name))
                    traceback.print_exc()
                    return False

        watcher.change_substatus('')
        return True

    def _uninstall_pkgs(self, pkgs: Iterable[str], root_password: str, handler: ProcessHandler) -> bool:
        status_handler = TransactionStatusHandler(watcher=handler.watcher,
                                                  i18n=self.i18n,
                                                  names={*pkgs},
                                                  logger=self.logger,
                                                  pkgs_to_remove=len(pkgs))

        status_handler.start()
        all_uninstalled, _ = handler.handle_simple(SimpleProcess(cmd=['pacman', '-R', *pkgs, '--noconfirm'],
                                                                 root_password=root_password,
                                                                 error_phrases={'error: failed to prepare transaction',
                                                                                'error: failed to commit transaction'},
                                                                 shell=True),
                                                   output_handler=status_handler.handle)
        status_handler.stop_working()
        status_handler.join()

        installed = pacman.list_installed_names()

        for p in pkgs:
            if p not in installed:
                cache_path = ArchPackage.disk_cache_path(p)
                if os.path.exists(cache_path):
                    shutil.rmtree(cache_path)

        return all_uninstalled

    def _request_uninstall_confirmation(self, to_uninstall: Iterable[str], required: Iterable[str], watcher: ProcessWatcher) -> bool:
        reqs = [InputOption(label=p, value=p, icon_path=get_icon_path(), read_only=True) for p in required]
        reqs_select = MultipleSelectComponent(options=reqs, default_options=set(reqs), label="", max_per_line=1 if len(reqs) < 4 else 3)

        msg = '<p>{}</p><p>{}</p>'.format(self.i18n['arch.uninstall.required_by'].format(bold(str(len(required))), ', '.join(bold(n)for n in to_uninstall)) + '.',
                                          self.i18n['arch.uninstall.required_by.advice'] + '.')

        if not watcher.request_confirmation(title=self.i18n['warning'].capitalize(),
                                            body=msg,
                                            components=[reqs_select],
                                            confirmation_label=self.i18n['proceed'].capitalize(),
                                            deny_label=self.i18n['cancel'].capitalize(),
                                            window_cancel=False):
            watcher.print("Aborted")
            return False

        return True

    def _request_unncessary_uninstall_confirmation(self, unnecessary: Iterable[str], watcher: ProcessWatcher) -> Optional[Set[str]]:
        reqs = [InputOption(label=p, value=p, icon_path=get_icon_path(), read_only=False) for p in unnecessary]
        reqs_select = MultipleSelectComponent(options=reqs, default_options=set(reqs), label="", max_per_line=3 if len(reqs) > 9 else 1)

        if not watcher.request_confirmation(title=self.i18n['arch.uninstall.unnecessary.l1'].capitalize(),
                                            body='<p>{}</p>'.format(self.i18n['arch.uninstall.unnecessary.l2'] + ':'),
                                            components=[reqs_select],
                                            deny_label=self.i18n['arch.uninstall.unnecessary.proceed'].capitalize(),
                                            confirmation_label=self.i18n['arch.uninstall.unnecessary.cancel'].capitalize(),
                                            window_cancel=False):
            return {*reqs_select.get_selected_values()}

    def _request_all_unncessary_uninstall_confirmation(self, pkgs: Iterable[str], context: TransactionContext):
        reqs = [InputOption(label=p, value=p, icon_path=get_icon_path(), read_only=True) for p in pkgs]
        reqs_select = MultipleSelectComponent(options=reqs, default_options=set(reqs), label="", max_per_line=1)

        if not context.watcher.request_confirmation(title=self.i18n['confirmation'].capitalize(),
                                                    body=self.i18n['arch.uninstall.unnecessary.all'].format(bold(str(len(pkgs)))),
                                                    components=[reqs_select],
                                                    confirmation_label=self.i18n['proceed'].capitalize(),
                                                    deny_label=self.i18n['cancel'].capitalize(),
                                                    window_cancel=False):
            context.watcher.print("Aborted")
            return False

        return True

    def _uninstall(self, context: TransactionContext, names: Set[str], remove_unneeded: bool = False, disk_loader: DiskCacheLoader = None):
        self._update_progress(context, 10)

        net_available = internet.is_available() if disk_loader else True

        hard_requirements = set()

        for n in names:
            try:
                pkg_reqs = pacman.list_hard_requirements(n, self.logger)

                if pkg_reqs:
                    hard_requirements.update(pkg_reqs)
            except PackageInHoldException:
                context.watcher.show_message(title=self.i18n['error'].capitalize(),
                                             body=self.i18n['arch.uninstall.error.hard_dep_in_hold'].format(bold(n)),
                                             type_=MessageType.ERROR)
                return False

        self._update_progress(context, 25)

        to_uninstall = set()
        to_uninstall.update(names)

        if hard_requirements:
            to_uninstall.update(hard_requirements)

            if not self._request_uninstall_confirmation(to_uninstall=names,
                                                        required=hard_requirements,
                                                        watcher=context.watcher):
                return False

        if remove_unneeded:
            unnecessary_packages = pacman.list_post_uninstall_unneeded_packages(to_uninstall)
            self.logger.info("Checking unnecessary optdeps")

            if context.config['suggest_optdep_uninstall']:
                unnecessary_packages.update(self._list_opt_deps_with_no_hard_requirements(source_pkgs=to_uninstall))

            self.logger.info("Packages no longer needed found: {}".format(len(unnecessary_packages)))
        else:
            unnecessary_packages = None

        self._update_progress(context, 50)

        if disk_loader and to_uninstall:  # loading package instances in case the uninstall succeeds
            instances = self.read_installed(disk_loader=disk_loader,
                                            names={n for n in to_uninstall},
                                            internet_available=net_available).installed

            if len(instances) != len(to_uninstall):
                self.logger.warning("Not all packages to be uninstalled could be read")
        else:
            instances = None

        uninstalled = self._uninstall_pkgs(to_uninstall, context.root_password, context.handler)

        if uninstalled:
            if disk_loader:  # loading package instances in case the uninstall succeeds
                if instances:
                    for p in instances:
                        context.removed[p.name] = p

            self._update_progress(context, 70)

            if unnecessary_packages:
                unnecessary_to_uninstall = self._request_unncessary_uninstall_confirmation(unnecessary=unnecessary_packages,
                                                                                           watcher=context.watcher)

                if unnecessary_to_uninstall:
                    context.watcher.change_substatus(self.i18n['arch.checking_unnecessary_deps'])
                    unnecessary_requirements = set()

                    for pkg in unnecessary_to_uninstall:
                        try:
                            pkg_reqs = pacman.list_hard_requirements(pkg)

                            if pkg_reqs:
                                unnecessary_requirements.update(pkg_reqs)

                        except PackageInHoldException:
                            context.watcher.show_message(title=self.i18n['warning'].capitalize(),
                                                         body=self.i18n['arch.uninstall.error.hard_dep_in_hold'].format(bold(p)),
                                                         type_=MessageType.WARNING)

                    all_unnecessary_to_uninstall = {*unnecessary_to_uninstall, *unnecessary_requirements}

                    if not unnecessary_requirements or self._request_all_unncessary_uninstall_confirmation(all_unnecessary_to_uninstall, context):
                        if disk_loader:  # loading package instances in case the uninstall succeeds
                            unnecessary_instances = self.read_installed(disk_loader=disk_loader,
                                                                        internet_available=net_available,
                                                                        names=all_unnecessary_to_uninstall).installed
                        else:
                            unnecessary_instances = None

                        unneded_uninstalled = self._uninstall_pkgs(all_unnecessary_to_uninstall, context.root_password, context.handler)

                        if unneded_uninstalled:
                            to_uninstall.update(all_unnecessary_to_uninstall)

                            if disk_loader and unnecessary_instances:  # loading package instances in case the uninstall succeeds
                                for p in unnecessary_instances:
                                    context.removed[p.name] = p
                            else:
                                self.logger.error("Could not uninstall some unnecessary packages")
                                context.watcher.print("Could not uninstall some unnecessary packages")

            self._update_progress(context, 90)

            if bool(context.config['clean_cached']):  # cleaning old versions
                context.watcher.change_substatus(self.i18n['arch.uninstall.clean_cached.substatus'])
                if os.path.isdir('/var/cache/pacman/pkg'):
                    for p in to_uninstall:
                        available_files = glob.glob("/var/cache/pacman/pkg/{}-*.pkg.tar.*".format(p))

                        if available_files and not context.handler.handle_simple(SimpleProcess(cmd=['rm', '-rf', *available_files],
                                                                                 root_password=context.root_password)):
                            context.watcher.show_message(title=self.i18n['error'],
                                                         body=self.i18n['arch.uninstall.clean_cached.error'].format(bold(p)),
                                                         type_=MessageType.WARNING)

                self._revert_ignored_updates(to_uninstall)

            self._remove_from_editable_pkgbuilds(context.name)

        self._update_progress(context, 100)
        return uninstalled

    def uninstall(self, pkg: ArchPackage, root_password: str, watcher: ProcessWatcher, disk_loader: DiskCacheLoader) -> TransactionResult:
        self.aur_client.clean_caches()
        handler = ProcessHandler(watcher)

        if self._is_database_locked(handler, root_password):
            return TransactionResult.fail()

        removed = {}
        arch_config = read_config()
        success = self._uninstall(TransactionContext(change_progress=True,
                                                     arch_config=arch_config,
                                                     watcher=watcher,
                                                     root_password=root_password,
                                                     handler=handler,
                                                     removed=removed),
                                  remove_unneeded=arch_config['suggest_unneeded_uninstall'],
                                  names={pkg.name},
                                  disk_loader=disk_loader)  # to be able to return all uninstalled packages
        if success:
            return TransactionResult(success=True, installed=None, removed=[*removed.values()] if removed else [])
        else:
            return TransactionResult.fail()

    def get_managed_types(self) -> Set["type"]:
        return {ArchPackage}

    def _get_info_aur_pkg(self, pkg: ArchPackage) -> dict:
        if pkg.installed:
            t = Thread(target=self.mapper.fill_package_build, args=(pkg,), daemon=True)
            t.start()

            info = pacman.get_info_dict(pkg.name)

            t.join()

            if pkg.pkgbuild:
                info['13_pkg_build'] = pkg.pkgbuild

            info['14_installed_files'] = pacman.list_installed_files(pkg.name)

            return info
        else:
            info = {
                '01_id': pkg.id,
                '02_name': pkg.name,
                '03_description': pkg.description,
                '03_version': pkg.version,
                '04_popularity': pkg.popularity,
                '05_votes': pkg.votes,
                '06_package_base': pkg.package_base,
                '07_maintainer': pkg.maintainer,
                '08_first_submitted': pkg.first_submitted,
                '09_last_modified': pkg.last_modified,
                '10_url': pkg.url_download
            }

            srcinfo = self.aur_client.get_src_info(pkg.name)

            if srcinfo:
                arch_str = 'x86_64' if self.context.is_system_x86_64() else 'i686'
                for info_attr, src_attr in {'12_makedepends': 'makedepends',
                                            '13_dependson': 'depends',
                                            '14_optdepends': 'optdepends',
                                            'checkdepends': '15_checkdepends'}.items():
                    if srcinfo.get(src_attr):
                        info[info_attr] = [*srcinfo[src_attr]]

                    arch_attr = '{}_{}'.format(src_attr, arch_str)

                    if srcinfo.get(arch_attr):
                        if not info.get(info_attr):
                            info[info_attr] = [*srcinfo[arch_attr]]
                        else:
                            info[info_attr].extend(srcinfo[arch_attr])

            if pkg.pkgbuild:
                info['00_pkg_build'] = pkg.pkgbuild
            else:
                info['11_pkg_build_url'] = pkg.get_pkg_build_url()

            return info

    def _get_info_repo_pkg(self, pkg: ArchPackage) -> dict:
        info = pacman.get_info_dict(pkg.name, remote=not pkg.installed)
        if pkg.installed:
            info['installed files'] = pacman.list_installed_files(pkg.name)

        return info

    def get_info(self, pkg: ArchPackage) -> dict:
        if pkg.repository == 'aur':
            return self._get_info_aur_pkg(pkg)
        else:
            return self._get_info_repo_pkg(pkg)

    def _get_history_aur_pkg(self, pkg: ArchPackage) -> PackageHistory:
        arch_config = read_config()
        temp_dir = '{}/build_{}'.format(get_build_dir(arch_config), int(time.time()))

        try:
            Path(temp_dir).mkdir(parents=True)
            base_name = pkg.get_base_name()
            run_cmd('git clone ' + URL_GIT.format(base_name), print_error=False, cwd=temp_dir)

            clone_path = '{}/{}'.format(temp_dir, base_name)

            srcinfo_path = '{}/.SRCINFO'.format(clone_path)

            if not os.path.exists(srcinfo_path):
                return PackageHistory.empyt(pkg)

            commits = git.list_commits(clone_path)

            if commits:
                srcfields = {'pkgver', 'pkgrel'}
                history, status_idx = [], -1

                for idx, commit in enumerate(commits):
                    with open(srcinfo_path) as f:
                        pkgsrc = aur.map_srcinfo(string=f.read(), pkgname=pkg.name, fields=srcfields)

                    if status_idx < 0 and '{}-{}'.format(pkgsrc.get('pkgver'), pkgsrc.get('pkgrel')) == pkg.version:
                        status_idx = idx

                    history.append({'1_version': pkgsrc['pkgver'], '2_release': pkgsrc['pkgrel'],
                                    '3_date': commit['date']})  # the number prefix is to ensure the rendering order

                    if idx + 1 < len(commits):
                        if not run_cmd('git reset --hard ' + commits[idx + 1]['commit'], cwd=clone_path):
                            break

                return PackageHistory(pkg=pkg, history=history, pkg_status_idx=status_idx)
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def _get_history_repo_pkg(self, pkg: ArchPackage) -> PackageHistory:
        data = PackageHistory(pkg=pkg, history=[], pkg_status_idx=-1)

        versions = [pkg.latest_version]
        version_files = {}  # maps the version and tar file

        if pkg.update:
            versions.append(pkg.version)

        if os.path.isdir('/var/cache/pacman/pkg'):
            available_files = glob.glob("/var/cache/pacman/pkg/{}-*.pkg.tar.*".format(pkg.name))

            if available_files:
                reg = re.compile(r'{}-([\w.\-]+)-(x86_64|any|i686).pkg'.format(pkg.name))

                for file_path in available_files:
                    found = reg.findall(os.path.basename(file_path))

                    if found:
                        ver = found[0][0]
                        if ver not in versions:
                            versions.append(ver)

                        version_files[ver] = file_path

        versions.sort(reverse=True)
        extract_path = '{}/arch/history'.format(TEMP_DIR)

        try:
            Path(extract_path).mkdir(parents=True, exist_ok=True)
        except:
            self.logger.error("Could not create temp dir {} to extract previous versions data".format(extract_path))
            traceback.print_exc()
            return data

        try:
            for idx, v in enumerate(versions):
                cur_version = v.split('-')
                cur_data = {'1_version': ''.join(cur_version[0:-1]),
                            '2_release': cur_version[-1],
                            '3_date': ''}

                if pkg.version == v:
                    data.pkg_status_idx = idx

                version_file = version_files.get(v)

                if not version_file:
                    if v == pkg.version:
                        cur_data['3_date'] = pacman.get_build_date(pkg.name)
                else:
                    extracted_dir = '{}/{}'.format(extract_path, v)
                    Path(extracted_dir).mkdir(parents=True, exist_ok=True)

                    try:
                        filext = version_file.split('.')[-1]
                        run_cmd('tar -C {} -I {} -xvf {} .PKGINFO'.format(extracted_dir, 'zstd' if filext == 'zst' else filext, version_file))
                    except tarfile.ReadError:
                        if v == pkg.version:
                            cur_data['3_date'] = pacman.get_build_date(pkg.name)
                        else:
                            self.logger.error("Could not read file {}. Skipping version {}".format(version_file, v))
                            continue

                    info_file = '{}/.PKGINFO'.format(extracted_dir)
                    if os.path.isfile(info_file):
                        with open(info_file) as f:
                            for l in f.readlines():
                                if l and l.startswith('builddate'):
                                    cur_data['3_date'] = datetime.fromtimestamp(int(l.split('=')[1].strip()))
                                    break

                data.history.append(cur_data)
            return data

        finally:
            if os.path.exists(extract_path):
                try:
                    self.logger.info("Removing temporary history dir {}".format(extract_path))
                    shutil.rmtree(extract_path)
                except:
                    self.logger.error("Could not remove temp path '{}'".format(extract_path))
                    raise

    def get_history(self, pkg: ArchPackage) -> PackageHistory:
        if pkg.repository == 'aur':
            return self._get_history_aur_pkg(pkg)
        else:
            return self._get_history_repo_pkg(pkg)

    def _request_conflict_resolution(self, pkg: str, conflicting_pkg: str, context: TransactionContext) -> bool:
        conflict_msg = '{} {} {}'.format(bold(pkg), self.i18n['and'], bold(conflicting_pkg))
        if not context.watcher.request_confirmation(title=self.i18n['arch.install.conflict.popup.title'],
                                                    body=self.i18n['arch.install.conflict.popup.body'].format(conflict_msg)):
            context.watcher.print(self.i18n['action.cancelled'])
            return False
        else:
            context.watcher.change_substatus(self.i18n['arch.uninstalling.conflict'].format(bold(conflicting_pkg)))
            context.disable_progress_if_changing()

            if context.removed is None:
                context.removed = {}

            res = self._uninstall(context=context, names={conflicting_pkg}, disk_loader=context.disk_loader, remove_unneeded=False)
            context.restabilish_progress()
            return res

    def _install_deps(self, context: TransactionContext, deps: List[Tuple[str, str]]) -> Iterable[str]:
        """
        :param pkgs_repos:
        :param root_password:
        :param handler:
        :return: not installed dependency
        """
        progress_increment = int(100 / len(deps))
        progress = 0
        self._update_progress(context, 1)

        repo_deps, repo_dep_names, aur_deps_context = [], None, []

        for dep in deps:
            context.watcher.change_substatus(self.i18n['arch.install.dependency.install'].format(bold('{} ({})'.format(dep[0], dep[1]))))

            if dep[1] == 'aur':
                dep_context = context.gen_dep_context(dep[0], dep[1])
                dep_src = self.aur_client.get_src_info(dep[0])
                dep_context.base = dep_src['pkgbase']
                aur_deps_context.append(dep_context)
            else:
                repo_deps.append(dep)

        if repo_deps:
            repo_dep_names = [d[0] for d in repo_deps]

            if context.dependency:
                context.watcher.change_substatus(self.i18n['arch.substatus.conflicts'])
            else:
                context.watcher.change_substatus(self.i18n['arch.checking.conflicts'].format(bold(context.name)))

            all_provided = context.get_provided_map()

            for dep, conflicts in pacman.map_conflicts_with(repo_dep_names, remote=True).items():
                if conflicts:
                    for c in conflicts:
                        source_conflict = all_provided.get(c)

                        if source_conflict:
                            conflict_pkg = [*source_conflict][0]

                            if dep != conflict_pkg:
                                if not self._request_conflict_resolution(dep, conflict_pkg , context):
                                    return {dep}

            downloaded = 0
            if self._multithreaded_download_enabled(context.config):
                try:
                    pkg_sizes = pacman.map_download_sizes(repo_dep_names)
                    downloaded = self._download_packages(repo_dep_names, context.handler, context.root_password, pkg_sizes, multithreaded=True)
                except ArchDownloadException:
                    return False

            status_handler = TransactionStatusHandler(watcher=context.watcher, i18n=self.i18n, names=repo_dep_names,
                                                      logger=self.logger, percentage=len(repo_deps) > 1, downloading=downloaded)
            status_handler.start()
            installed, _ = context.handler.handle_simple(pacman.install_as_process(pkgpaths=repo_dep_names,
                                                                                   root_password=context.root_password,
                                                                                   file=False),
                                                         output_handler=status_handler.handle)

            if installed:
                pkg_map = {d[0]: ArchPackage(name=d[0], repository=d[1], maintainer=d[1],
                                             categories=self.categories.get(d[0])) for d in repo_deps}
                disk.write_several(pkg_map, overwrite=True, maintainer=None)
                progress += len(repo_deps) * progress_increment
                self._update_progress(context, progress)
            else:
                return repo_dep_names

        for aur_context in aur_deps_context:
            installed = self._install_from_aur(aur_context)

            if not installed:
                return {aur_context.name}
            else:
                progress += progress_increment
                self._update_progress(context, progress)

        self._update_progress(context, 100)

    def _map_repos(self, pkgnames: Iterable[str]) -> dict:
        pkg_repos = pacman.get_repositories(pkgnames)  # getting repositories set

        if len(pkgnames) != len(pkg_repos):  # checking if any dep not found in the distro repos are from AUR
            norepos = {p for p in pkgnames if p not in pkg_repos}
            for pkginfo in self.aur_client.get_info(norepos):
                if pkginfo.get('Name') in norepos:
                    pkg_repos[pkginfo['Name']] = 'aur'

        return pkg_repos

    def _pre_download_source(self, pkgname: str, project_dir: str, watcher: ProcessWatcher) -> bool:
        if self.context.file_downloader.is_multithreaded():
            with open('{}/.SRCINFO'.format(project_dir)) as f:
                srcinfo = aur.map_srcinfo(string=f.read(), pkgname=pkgname)

            pre_download_files = []

            for attr in SOURCE_FIELDS:
                if srcinfo.get(attr):
                    if attr == 'source_x86_x64' and not self.context.is_system_x86_64():
                        continue
                    else:
                        for f in srcinfo[attr]:
                             if RE_PRE_DOWNLOAD_WL_PROTOCOLS.match(f) and not RE_PRE_DOWNLOAD_BL_EXT.match(f):
                                pre_download_files.append(f)

            if pre_download_files:
                for f in pre_download_files:
                    fdata = f.split('::')

                    args = {'watcher': watcher, 'cwd': project_dir}
                    if len(fdata) > 1:
                        args.update({'file_url': fdata[1], 'output_path': fdata[0]})
                    else:
                        args.update({'file_url': fdata[0], 'output_path': fdata[0].split('/')[-1]})

                    if not self.context.file_downloader.download(**args):
                        watcher.print('Could not download source file {}'.format(args['file_url']))
                        return False

        return True

    def _display_pkgbuild_for_editing(self, pkgname: str, watcher: ProcessWatcher, pkgbuild_path: str) -> bool:
        with open(pkgbuild_path) as f:
            pkgbuild = f.read()

        pkgbuild_input = TextInputComponent(label='', value=pkgbuild, type_=TextInputType.MULTIPLE_LINES,
                                            min_width=500, min_height=350)

        watcher.request_confirmation(title='PKGBUILD ({})'.format(pkgname),
                                     body='',
                                     components=[pkgbuild_input],
                                     confirmation_label=self.i18n['proceed'].capitalize(),
                                     deny_button=False)

        if pkgbuild_input.get_value() != pkgbuild:
            with open(pkgbuild_path, 'w+') as f:
                f.write(pkgbuild_input.get_value())

            return makepkg.update_srcinfo('/'.join(pkgbuild_path.split('/')[0:-1]))

        return False

    def _ask_for_pkgbuild_edition(self, pkgname: str, arch_config: dict, watcher: ProcessWatcher, pkgbuild_path: str) -> bool:
        if pkgbuild_path:
            if arch_config['edit_aur_pkgbuild'] is None:
                if not watcher.request_confirmation(title=self.i18n['confirmation'].capitalize(),
                                                    body=self.i18n['arch.aur.action.edit_pkgbuild.body'].format(bold(pkgname)),
                                                    confirmation_label=self.i18n['no'].capitalize(),
                                                    deny_label=self.i18n['yes'].capitalize()):
                    return self._display_pkgbuild_for_editing(pkgname, watcher, pkgbuild_path)
            elif arch_config['edit_aur_pkgbuild']:
                return self._display_pkgbuild_for_editing(pkgname, watcher, pkgbuild_path)

        return False

    def _edit_pkgbuild_and_update_context(self, context: TransactionContext):
        if context.new_pkg or context.name in self._read_editable_pkgbuilds():
            if self._ask_for_pkgbuild_edition(pkgname=context.name,
                                              arch_config=context.config,
                                              watcher=context.watcher,
                                              pkgbuild_path='{}/PKGBUILD'.format(context.project_dir)):
                context.pkgbuild_edited = True
                srcinfo = aur.map_srcinfo(string=makepkg.gen_srcinfo(context.project_dir), pkgname=context.name)

                if srcinfo:
                    context.name = srcinfo['pkgname']
                    context.base = srcinfo['pkgbase']

                    if context.pkg:
                        for pkgattr, srcattr in {'name': 'pkgname',
                                                 'package_base': 'pkgbase',
                                                 'version': 'pkgversion',
                                                 'latest_version': 'pkgversion',
                                                 'license': 'license',
                                                 'description': 'pkgdesc'}.items():
                            setattr(context.pkg, pkgattr, srcinfo.get(srcattr, getattr(context.pkg, pkgattr)))

    def _read_srcinfo(self, context: TransactionContext) -> str:
        src_path = '{}/.SRCINFO'.format(context.project_dir)
        if not os.path.exists(src_path):
            srcinfo = makepkg.gen_srcinfo(context.project_dir, context.custom_pkgbuild_path)

            with open(src_path, 'w+') as f:
                f.write(srcinfo)
        else:
            with open(src_path) as f:
                srcinfo = f.read()

        return srcinfo

    def _build(self, context: TransactionContext) -> bool:
        self._edit_pkgbuild_and_update_context(context)
        self._pre_download_source(context.name, context.project_dir, context.watcher)
        self._update_progress(context, 50)

        context.custom_pkgbuild_path = self._gen_custom_pkgbuild_if_required(context)

        if not self._handle_aur_package_deps_and_keys(context):
            return False

        # building main package
        context.watcher.change_substatus(self.i18n['arch.building.package'].format(bold(context.name)))
        optimize = bool(context.config['optimize']) and cpu_manager.supports_performance_mode() and not cpu_manager.all_in_performance()

        cpu_optimized = False
        if optimize:
            self.logger.info("Setting cpus to performance mode")
            cpu_manager.set_mode('performance', context.root_password)
            cpu_optimized = True

        try:
            pkgbuilt, output = makepkg.make(pkgdir=context.project_dir,
                                            optimize=optimize,
                                            handler=context.handler,
                                            custom_pkgbuild=context.custom_pkgbuild_path)
        finally:
            if cpu_optimized:
                self.logger.info("Setting cpus to powersave mode")
                cpu_manager.set_mode('powersave', context.root_password)

        self._update_progress(context, 65)

        if pkgbuilt:
            self.__fill_aur_output_files(context)

            if self._install(context=context):
                self._save_pkgbuild(context)

                if context.dependency or context.skip_opt_deps:
                    return True

                context.watcher.change_substatus(self.i18n['arch.optdeps.checking'].format(bold(context.name)))

                self._update_progress(context, 100)

                if self._install_optdeps(context):
                    return True

        return False

    def __fill_aur_output_files(self, context: TransactionContext):
        self.logger.info("Determining output files of '{}'".format(context.name))
        context.watcher.change_substatus(self.i18n['arch.aur.build.list_output'])
        output_files = {f for f in makepkg.list_output_files(context.project_dir, context.custom_pkgbuild_path) if os.path.isfile(f)}

        if output_files:
            context.install_files = output_files
        else:
            gen_file = [fname for root, dirs, files in os.walk(context.build_dir) for fname in files if
                        re.match(r'^{}-.+\.tar\.(xz|zst)'.format(context.name), fname)]

            if not gen_file:
                context.watcher.print('Could not find the built package. Aborting...')
                return False

            file_to_install = gen_file[0]

            if len(gen_file) > 1:
                srcinfo = aur.map_srcinfo(string=makepkg.gen_srcinfo(context.project_dir), pkgname=context.name)
                pkgver = '-{}'.format(srcinfo['pkgver']) if srcinfo.get('pkgver') else ''
                pkgrel = '-{}'.format(srcinfo['pkgrel']) if srcinfo.get('pkgrel') else ''
                arch = '-{}'.format(srcinfo['arch']) if srcinfo.get('arch') else ''
                name_start = '{}{}{}{}'.format(context.name, pkgver, pkgrel, arch)

                perfect_match = [f for f in gen_file if f.startswith(name_start)]

                if perfect_match:
                    file_to_install = perfect_match[0]

            context.install_files = {'{}/{}'.format(context.project_dir, file_to_install)}

        context.watcher.change_substatus('')

    def _save_pkgbuild(self, context: TransactionContext):
        cache_path = ArchPackage.disk_cache_path(context.name)
        if not os.path.exists(cache_path):
            try:
                os.mkdir(cache_path)
            except:
                print("Could not create cache directory '{}'".format(cache_path))
                traceback.print_exc()
                return

        src_pkgbuild = '{}/PKGBUILD'.format(context.project_dir)
        dest_pkgbuild = '{}/PKGBUILD'.format(cache_path)
        try:
            shutil.copy(src_pkgbuild, dest_pkgbuild)
        except:
            context.watcher.print("Could not copy '{}' to '{}'".format(src_pkgbuild, dest_pkgbuild))
            traceback.print_exc()

    def _ask_and_install_missing_deps(self, context: TransactionContext,  missing_deps: List[Tuple[str, str]]) -> bool:
        context.watcher.change_substatus(self.i18n['arch.missing_deps_found'].format(bold(context.name)))

        if not confirmation.request_install_missing_deps(context.name, missing_deps, context.watcher, self.i18n):
            context.watcher.print(self.i18n['action.cancelled'])
            return False

        old_progress_behavior = context.change_progress
        context.change_progress = False
        deps_not_installed = self._install_deps(context, missing_deps)
        context.change_progress = old_progress_behavior

        if deps_not_installed:
            message.show_deps_not_installed(context.watcher, context.name, deps_not_installed, self.i18n)
            return False

        context.installed.update({d[0] for d in missing_deps})

        return True

    def _list_missing_deps(self, context: TransactionContext) -> List[Tuple[str, str]]:
        context.watcher.change_substatus(self.i18n['arch.checking.deps'].format(bold(context.name)))
        ti = time.time()

        if context.repository == 'aur':
            srcinfo = aur.map_srcinfo(string=self._read_srcinfo(context),
                                      pkgname=context.name if (not context.pkgs_to_build or len(context.pkgs_to_build) == 1) else None)

            if context.pkgs_to_build and len(context.pkgs_to_build) > 1:  # removing self dependencies from srcinfo
                for attr in ('depends', 'makedepends', 'optdepends'):
                    dep_list = srcinfo.get(attr)

                    if dep_list and isinstance(dep_list, list):
                        to_remove = set()
                        for dep in dep_list:
                            dep_name = RE_DEP_OPERATORS.split(dep.split(':')[0])[0].strip()

                            if dep_name and dep_name in context.pkgs_to_build:
                                to_remove.add(dep)

                        for dep in to_remove:
                            dep_list.remove(dep)

            pkgs_data = {context.name: self.aur_client.map_update_data(context.name, context.get_version(), srcinfo)}
        else:
            pkgs_data = pacman.map_updates_data(context.get_packages_paths(), files=bool(context.install_files))

        deps_data, alread_checked_deps = {}, set()

        missing_deps = self.deps_analyser.map_missing_deps(pkgs_data=pkgs_data,
                                                           provided_map=context.get_provided_map(),
                                                           aur_index=context.get_aur_idx(self.aur_client),
                                                           deps_checked=alread_checked_deps,
                                                           deps_data=deps_data,
                                                           sort=True,
                                                           remote_provided_map=context.get_remote_provided_map(),
                                                           remote_repo_map=context.get_remote_repo_map(),
                                                           automatch_providers=context.config['automatch_providers'],
                                                           watcher=context.watcher)

        tf = time.time()
        self.logger.info("Took {0:.2f} seconds to check for missing dependencies".format(tf - ti))
        return missing_deps

    def _handle_missing_deps(self, context: TransactionContext) -> bool:
        try:
            missing_deps = self._list_missing_deps(context)
        except PackageNotFoundException:
            return False
        except:
            traceback.print_exc()
            return False

        if missing_deps is None:
            return False  # called off by the user

        if not missing_deps:
            return True
        elif not self._ask_and_install_missing_deps(context=context, missing_deps=missing_deps):
            return False  # called off by the user or something went wrong
        else:
            return True

    def _handle_aur_package_deps_and_keys(self, context: TransactionContext) -> bool:
        handled_deps = self._handle_missing_deps(context)
        if not handled_deps:
            return False

        check_res = makepkg.check(context.project_dir,
                                  optimize=bool(context.config['optimize']),
                                  missing_deps=False,
                                  handler=context.handler,
                                  custom_pkgbuild=context.custom_pkgbuild_path)

        if check_res:
            if check_res.get('gpg_key'):
                if context.watcher.request_confirmation(title=self.i18n['arch.install.aur.unknown_key.title'],
                                                        body=self.i18n['arch.install.aur.unknown_key.body'].format(bold(context.name), bold(check_res['gpg_key']))):
                    context.watcher.change_substatus(self.i18n['arch.aur.install.unknown_key.status'].format(bold(check_res['gpg_key'])))
                    self.logger.info("Importing GPG key {}".format(check_res['gpg_key']))

                    gpg_res = self.context.http_client.get(URL_GPG_SERVERS)
                    gpg_server = gpg_res.text.split('\n')[0] if gpg_res else None

                    if not context.handler.handle(gpg.receive_key(check_res['gpg_key'], gpg_server)):
                        self.logger.error("An error occurred while importing the GPG key {}".format(check_res['gpg_key']))
                        context.watcher.show_message(title=self.i18n['error'].capitalize(),
                                                     body=self.i18n['arch.aur.install.unknown_key.receive_error'].format(bold(check_res['gpg_key'])))

                        return False
                else:
                    context.watcher.print(self.i18n['action.cancelled'])
                    return False

            if check_res.get('validity_check'):
                body = "<p>{}</p><p>{}</p>".format(self.i18n['arch.aur.install.validity_check.body'].format(bold(context.name)),
                                                   self.i18n['arch.aur.install.validity_check.proceed'])
                return not context.watcher.request_confirmation(title=self.i18n['arch.aur.install.validity_check.title'].format('( checksum )'),
                                                                body=body,
                                                                confirmation_label=self.i18n['no'].capitalize(),
                                                                deny_label=self.i18n['yes'].capitalize())

        return True

    def _install_optdeps(self, context: TransactionContext) -> bool:
        odeps = pacman.map_optional_deps({context.name}, remote=False, not_installed=True).get(context.name)

        if not odeps:
            return True

        repo_mapping = self._map_repos(odeps.keys())

        if repo_mapping:
            final_optdeps = {dep: {'desc': odeps.get(dep), 'repository': repo_mapping.get(dep)} for dep, repository in repo_mapping.items() if repo_mapping.get(dep)}

            deps_to_install = confirmation.request_optional_deps(context.name, final_optdeps, context.watcher, self.i18n)

            if not deps_to_install:
                return True
            else:
                deps_data = {}
                opt_repo_deps, aur_threads = [], []

                for dep in deps_to_install:
                    if repo_mapping[dep] == 'aur':
                        t = Thread(target=self.aur_client.fill_update_data, args=(deps_data, dep, None, None), daemon=True)
                        t.start()
                        aur_threads.append(t)
                    else:
                        opt_repo_deps.append(dep)

                if opt_repo_deps:
                    deps_data.update(pacman.map_updates_data(opt_repo_deps))

                for t in aur_threads:
                    t.join()

                provided_map = pacman.map_provided()
                remote_provided_map = pacman.map_provided(remote=True)
                remote_repo_map = pacman.map_repositories()
                aur_index = self.aur_client.read_index() if aur_threads else None
                subdeps_data = {}
                missing_deps = self.deps_analyser.map_missing_deps(pkgs_data=deps_data,
                                                                   provided_map=provided_map,
                                                                   aur_index=aur_index,
                                                                   deps_checked=set(),
                                                                   deps_data=subdeps_data,
                                                                   watcher=context.watcher,
                                                                   remote_provided_map=remote_provided_map,
                                                                   remote_repo_map=remote_repo_map,
                                                                   automatch_providers=context.config['automatch_providers'],
                                                                   sort=False)

                if missing_deps is None:
                    return False  # called of by the user

                to_sort = []
                if missing_deps:
                    for dep in missing_deps:
                        # TODO handle multiple providers for a missing dep
                        if dep[0] not in deps_to_install and dep[1] != '__several__':
                            to_sort.append(dep[0])

                display_deps_dialog = bool(to_sort)  # it means there are subdeps to be installed so a new dialog should be displayed

                to_sort.extend(deps_data.keys())

                sorted_deps = sorting.sort(to_sort, {**deps_data, **subdeps_data}, provided_map)

                if display_deps_dialog and not confirmation.request_install_missing_deps(None, sorted_deps, context.watcher, self.i18n):
                    context.watcher.print(self.i18n['action.cancelled'])
                    return True  # because the main package installation was successful

                old_progress_behavior = context.change_progress
                context.change_progress = True
                context.dependency = True
                deps_not_installed = self._install_deps(context, sorted_deps)
                context.change_progress = old_progress_behavior

                if deps_not_installed:
                    message.show_optdeps_not_installed(deps_not_installed, context.watcher, self.i18n)
                else:
                    context.installed.update({dep[0] for dep in sorted_deps})

        return True

    def _multithreaded_download_enabled(self, arch_config: dict) -> bool:
        return bool(arch_config['repositories_mthread_download']) \
               and self.context.file_downloader.is_multithreaded() \
               and pacman.is_mirrors_available()

    def _download_packages(self, pkgnames: List[str], handler: ProcessHandler, root_password: str, sizes: Dict[str, int] = None, multithreaded: bool = True) -> int:
        if multithreaded:
            download_service = MultithreadedDownloadService(file_downloader=self.context.file_downloader,
                                                            http_client=self.http_client,
                                                            logger=self.context.logger,
                                                            i18n=self.i18n)
            self.logger.info("Initializing multi-threaded download for {} repository package(s)".format(len(pkgnames)))
            return download_service.download_packages(pkgs=pkgnames,
                                                      handler=handler,
                                                      sizes=sizes,
                                                      root_password=root_password)
        else:
            self.logger.info("Downloading {} repository package(s)".format(len(pkgnames)))
            output_handler = TransactionStatusHandler(handler.watcher, self.i18n, pkgnames, self.logger)
            output_handler.start()
            try:
                success, _ = handler.handle_simple(pacman.download(root_password, *pkgnames), output_handler=output_handler.handle)

                if success:
                    return len(pkgnames)
                else:
                    raise ArchDownloadException()
            except:
                traceback.print_exc()
                raise ArchDownloadException()

    def _install(self, context: TransactionContext) -> bool:
        pkgpaths = context.get_packages_paths()

        context.watcher.change_substatus(self.i18n['arch.checking.conflicts'].format(bold(context.name)))
        self.logger.info("Checking for possible conflicts with '{}'".format(context.name))

        _, output = context.handler.handle_simple(pacman.install_as_process(pkgpaths=pkgpaths,
                                                                            root_password=context.root_password,
                                                                            pkgdir=context.project_dir or '.',
                                                                            file=bool(context.install_files),
                                                                            simulate=True),
                                                  notify_watcher=False)

        self._update_progress(context, 70)

        if 'unresolvable package conflicts detected' in output:
            self.logger.info("Conflicts detected for '{}'".format(context.name))
            conflict_msgs = RE_CONFLICT_DETECTED.findall(output)
            conflicting_apps = {n.strip() for m in conflict_msgs for n in m.split(' and ')}
            conflict_msg = ' {} '.format(self.i18n['and']).join([bold(c) for c in conflicting_apps])
            if not context.watcher.request_confirmation(title=self.i18n['arch.install.conflict.popup.title'],
                                                        body=self.i18n['arch.install.conflict.popup.body'].format(conflict_msg)):
                context.watcher.print(self.i18n['action.cancelled'])
                return False
            else:  # uninstall conflicts
                self._update_progress(context, 75)
                names_to_install = context.get_package_names()
                to_uninstall = {conflict for conflict in conflicting_apps if conflict not in names_to_install}

                if to_uninstall:
                    self.logger.info("Preparing to uninstall conflicting packages: {}".format(to_uninstall))
                    context.watcher.change_substatus(self.i18n['arch.uninstalling.conflict'])

                    if context.removed is None:
                        context.removed = {}

                    context.disable_progress_if_changing()
                    if not self._uninstall(names=to_uninstall, context=context, remove_unneeded=False, disk_loader=context.disk_loader):
                        context.watcher.show_message(title=self.i18n['error'],
                                                     body=self.i18n['arch.uninstalling.conflict.fail'].format(', '.join((bold(p) for p in to_uninstall))),
                                                     type_=MessageType.ERROR)
                        return False
                    else:
                        context.restabilish_progress()

        else:
            self.logger.info("No conflict detected for '{}'".format(context.name))

        self._update_progress(context, 80)

        to_install = []

        if context.missing_deps:
            to_install.extend((d[0] for d in context.missing_deps))

        to_install.extend(pkgpaths)

        downloaded = 0
        if self._multithreaded_download_enabled(context.config):
            to_download = [p for p in to_install if not p.startswith('/')]

            if to_download:
                try:
                    pkg_sizes = pacman.map_download_sizes(to_download)
                    downloaded = self._download_packages(to_download, context.handler, context.root_password, pkg_sizes, multithreaded=True)
                except ArchDownloadException:
                    return False

        if not context.dependency:
            status_handler = TransactionStatusHandler(context.watcher, self.i18n, to_install, self.logger,
                                                      percentage=len(to_install) > 1,
                                                      downloading=downloaded) if not context.dependency else None
            status_handler.start()
        else:
            status_handler = None

        installed_with_same_name = self.read_installed(disk_loader=context.disk_loader, internet_available=True, names=context.get_package_names()).installed
        context.watcher.change_substatus(self.i18n['arch.installing.package'].format(bold(context.name)))
        installed = self._handle_install_call(context=context, to_install=to_install, status_handler=status_handler)

        if status_handler:
            status_handler.stop_working()
            status_handler.join()

        self._update_progress(context, 95)

        if installed:
            context.installed.update(context.get_package_names())
            context.installed.update((p for p in to_install if not p.startswith('/')))

            if installed_with_same_name:
                for p in installed_with_same_name:
                    context.removed[p.name] = p

            context.watcher.change_substatus(self.i18n['status.caching_data'].format(bold(context.name)))

            if not context.maintainer:
                if context.pkg and context.pkg.maintainer:
                    pkg_maintainer = context.pkg.maintainer
                elif context.repository == 'aur':
                    aur_infos = self.aur_client.get_info({context.name})
                    pkg_maintainer = aur_infos[0].get('Maintainer') if aur_infos else None
                else:
                    pkg_maintainer = context.repository
            else:
                pkg_maintainer = context.maintainer

            cache_map = {context.name: ArchPackage(name=context.name,
                                                   repository=context.repository,
                                                   maintainer=pkg_maintainer,
                                                   categories=self.categories.get(context.name))}
            if context.missing_deps:
                aur_deps = {dep[0] for dep in context.missing_deps if dep[1] == 'aur'}

                if aur_deps:
                    aur_data = self.aur_client.get_info(aur_deps)

                    if aur_data:
                        aur_data = {info['Name']: info for info in aur_data}
                    else:
                        aur_data = {n: {} for n in aur_deps}
                else:
                    aur_data = None

                for dep in context.missing_deps:
                    cache_map[dep[0]] = ArchPackage(name=dep[0],
                                                    repository=dep[1],
                                                    maintainer=dep[1] if dep[1] != 'aur' else (aur_data[dep[0]].get('Maintainer') if aur_data else None),
                                                    categories=self.categories.get(context.name))

            disk.write_several(pkgs=cache_map, maintainer=None, overwrite=True)

            context.watcher.change_substatus('')
            self._update_progress(context, 100)

        return installed

    def _call_pacman_install(self, context: TransactionContext, to_install: List[str], overwrite_files: bool, status_handler: Optional[object] = None) -> Tuple[bool, str]:
        return context.handler.handle_simple(pacman.install_as_process(pkgpaths=to_install,
                                                                       root_password=context.root_password,
                                                                       file=context.has_install_files(),
                                                                       pkgdir=context.project_dir,
                                                                       overwrite_conflicting_files=overwrite_files),
                                             output_handler=status_handler.handle if status_handler else None)

    def _handle_install_call(self, context: TransactionContext, to_install: List[str], status_handler) -> bool:
        installed, output = self._call_pacman_install(context=context, to_install=to_install,
                                                      overwrite_files=False, status_handler=status_handler)

        if not installed and 'conflicting files' in output:
            if not context.handler.watcher.request_confirmation(title=self.i18n['warning'].capitalize(),
                                                                body=self.i18n['arch.install.error.conflicting_files'].format(bold(context.name)) + ':',
                                                                deny_label=self.i18n['arch.install.error.conflicting_files.proceed'],
                                                                confirmation_label=self.i18n['arch.install.error.conflicting_files.stop'],
                                                                components=self._map_conflicting_file(output)):
                installed, output = self._call_pacman_install(context=context, to_install=to_install,
                                                              overwrite_files=True, status_handler=status_handler)

        return installed

    def _update_progress(self, context: TransactionContext, val: int):
        if context.change_progress:
            context.watcher.change_progress(val)

    def _import_pgp_keys(self, pkgname: str, root_password: str, handler: ProcessHandler):
        srcinfo = self.aur_client.get_src_info(pkgname)

        if srcinfo.get('validpgpkeys'):
            handler.watcher.print(self.i18n['arch.aur.install.verifying_pgp'])
            keys_to_download = [key for key in srcinfo['validpgpkeys'] if not pacman.verify_pgp_key(key)]

            if keys_to_download:
                keys_str = ''.join(
                    ['<br/><span style="font-weight:bold">  - {}</span>'.format(k) for k in keys_to_download])
                msg_body = '{}:<br/>{}<br/><br/>{}'.format(self.i18n['arch.aur.install.pgp.body'].format(bold(pkgname)),
                                                           keys_str, self.i18n['ask.continue'])

                if handler.watcher.request_confirmation(title=self.i18n['arch.aur.install.pgp.title'], body=msg_body):
                    for key in keys_to_download:
                        handler.watcher.change_substatus(self.i18n['arch.aur.install.pgp.substatus'].format(bold(key)))
                        if not handler.handle(pacman.receive_key(key, root_password)):
                            handler.watcher.show_message(title=self.i18n['error'],
                                                         body=self.i18n['arch.aur.install.pgp.receive_fail'].format(
                                                             bold(key)),
                                                         type_=MessageType.ERROR)
                            return False

                        if not handler.handle(pacman.sign_key(key, root_password)):
                            handler.watcher.show_message(title=self.i18n['error'],
                                                         body=self.i18n['arch.aur.install.pgp.sign_fail'].format(
                                                             bold(key)),
                                                         type_=MessageType.ERROR)
                            return False

                        handler.watcher.change_substatus(self.i18n['arch.aur.install.pgp.success'])
                else:
                    handler.watcher.print(self.i18n['action.cancelled'])
                    return False

    def _install_from_aur(self, context: TransactionContext) -> bool:
        self._optimize_makepkg(context.config, context.watcher)

        context.build_dir = '{}/build_{}'.format(get_build_dir(context.config), int(time.time()))

        try:
            if not os.path.exists(context.build_dir):
                build_dir = context.handler.handle(SystemProcess(new_subprocess(['mkdir', '-p', context.build_dir])))
                self._update_progress(context, 10)

                if build_dir:
                    base_name = context.get_base_name()
                    file_url = URL_PKG_DOWNLOAD.format(base_name)
                    file_name = file_url.split('/')[-1]
                    context.watcher.change_substatus('{} {}'.format(self.i18n['arch.downloading.package'], bold(file_name)))
                    download = context.handler.handle(SystemProcess(new_subprocess(['wget', file_url], cwd=context.build_dir), check_error_output=False))

                    if download:
                        self._update_progress(context, 30)
                        context.watcher.change_substatus('{} {}'.format(self.i18n['arch.uncompressing.package'], bold(base_name)))
                        uncompress = context.handler.handle(SystemProcess(new_subprocess(['tar', 'xvzf', '{}.tar.gz'.format(base_name)], cwd=context.build_dir)))
                        self._update_progress(context, 40)

                        if uncompress:
                            context.project_dir = '{}/{}'.format(context.build_dir, base_name)

                            return self._build(context)
        finally:
            if os.path.exists(context.build_dir) and context.config['aur_remove_build_dir']:
                context.handler.handle(SystemProcess(new_subprocess(['rm', '-rf', context.build_dir])))

        return False

    def _sync_databases(self, arch_config: dict, root_password: str, handler: ProcessHandler, change_substatus: bool = True):
        if bool(arch_config['sync_databases']) and database.should_sync(arch_config, handler, self.logger):
            if change_substatus:
                handler.watcher.change_substatus(self.i18n['arch.sync_databases.substatus'])

            synced, output = handler.handle_simple(pacman.sync_databases(root_password=root_password, force=True))
            if synced:
                database.register_sync(self.logger)
            else:
                self.logger.warning("It was not possible to synchronized the package databases")
                handler.watcher.change_substatus(self.i18n['arch.sync_databases.substatus.error'])

    def _optimize_makepkg(self, arch_config: dict, watcher: ProcessWatcher):
        if arch_config['optimize'] and not os.path.exists(CUSTOM_MAKEPKG_FILE):
            watcher.change_substatus(self.i18n['arch.makepkg.optimizing'])
            ArchCompilationOptimizer(arch_config, self.i18n, self.context.logger).optimize()

    def install(self, pkg: ArchPackage, root_password: str, disk_loader: DiskCacheLoader, watcher: ProcessWatcher, context: TransactionContext = None) -> TransactionResult:
        self.aur_client.clean_caches()

        if not self._check_action_allowed(pkg, watcher):
            return TransactionResult(success=False, installed=[], removed=[])

        handler = ProcessHandler(watcher) if not context else context.handler

        if self._is_database_locked(handler, root_password):
            return TransactionResult(success=False, installed=[], removed=[])

        if context:
            install_context = context
        else:
            install_context = TransactionContext.gen_context_from(pkg=pkg, handler=handler, arch_config=read_config(),
                                                                  root_password=root_password)
            install_context.skip_opt_deps = False
            install_context.disk_loader = disk_loader

        self._sync_databases(arch_config=install_context.config, root_password=root_password, handler=handler)

        if pkg.repository == 'aur':
            res = self._install_from_aur(install_context)
        else:
            res = self._install_from_repository(install_context)

        if res:
            pkg.name = install_context.name  # changes the package name in case the PKGBUILD was edited


            if os.path.exists(pkg.get_disk_data_path()):
                with open(pkg.get_disk_data_path()) as f:
                    data = f.read()
                    if data:
                        data = json.loads(data)
                        pkg.fill_cached_data(data)

            if install_context.new_pkg and install_context.config['edit_aur_pkgbuild'] is not False and pkg.repository == 'aur':
                if install_context.pkgbuild_edited:
                    pkg.pkgbuild_editable = self._add_as_editable_pkgbuild(pkg.name)
                else:
                    pkg.pkgbuild_editable = not self._remove_from_editable_pkgbuilds(pkg.name)

        installed = []

        if res and disk_loader and install_context.installed:
            installed.append(pkg)

            installed_to_load = []

            if len(install_context.installed) > 1:
                installed_to_load.extend({i for i in install_context.installed if i != pkg.name})

            if installed_to_load:
                installed_loaded = self.read_installed(disk_loader=disk_loader,
                                                       names=installed_to_load,
                                                       internet_available=True).installed

                if installed_loaded:
                    installed.extend(installed_loaded)

                    if len(installed_loaded) + 1 != len(install_context.installed):
                        missing = ','.join({p for p in installed_loaded if p.name not in install_context.installed})
                        self.logger.warning("Could not load all installed packages. Missing: {}".format(missing))

        removed = [*install_context.removed.values()] if install_context.removed else []

        if installed:
            downgrade_enabled = self.is_downgrade_enabled()
            for p in installed:
                p.downgrade_enabled = downgrade_enabled

        return TransactionResult(success=res, installed=installed, removed=removed)

    def _install_from_repository(self, context: TransactionContext) -> bool:
        try:
            missing_deps = self._list_missing_deps(context)
        except PackageNotFoundException:
            self.logger.error("Package '{}' was not found")
            return False

        if missing_deps is None:
            return False  # called off by the user

        if missing_deps:
            if any((dep for dep in missing_deps if dep[1] == 'aur')):
                context.watcher.show_message(title=self.i18n['error'].capitalize(),
                                             body=self.i18n['arch.install.repo_pkg.error.aur_deps'],
                                             type_=MessageType.ERROR)
                return False

            context.missing_deps = missing_deps
            context.watcher.change_substatus(self.i18n['arch.missing_deps_found'].format(bold(context.name)))

            if not confirmation.request_install_missing_deps(context.name, missing_deps, context.watcher, self.i18n):
                context.watcher.print(self.i18n['action.cancelled'])
                return False

        res = self._install(context)

        if res and not context.skip_opt_deps:
            self._update_progress(context, 100)
            return self._install_optdeps(context)

        return res

    def _is_wget_available(self):
        res = run_cmd('which wget')
        return res and not res.strip().startswith('which ')

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> bool:
        try:
            return self.arch_distro and pacman.is_available() and self._is_wget_available()
        except FileNotFoundError:
            return False

    def is_downgrade_enabled(self) -> bool:
        try:
            new_subprocess(['git', '--version'])
            return True
        except FileNotFoundError:
            return False

    def cache_to_disk(self, pkg: ArchPackage, icon_bytes: bytes, only_icon: bool):
        pass

    def requires_root(self, action: str, pkg: ArchPackage):
        if action == 'prepare':
            arch_config = read_config()

            if arch_config['refresh_mirrors_startup'] and mirrors.should_sync(self.logger):
                return True

            return arch_config['sync_databases_startup'] and database.should_sync(arch_config, None, self.logger)

        return action != 'search'

    def _start_category_task(self, task_man: TaskManager):
        task_man.register_task('arch_aur_cats', self.i18n['task.download_categories'].format('Arch'), get_icon_path())
        task_man.update_progress('arch_aur_cats', 50, None)

    def _finish_category_task(self, task_man: TaskManager):
        task_man.update_progress('arch_aur_cats', 100, None)
        task_man.finish_task('arch_aur_cats')

    def prepare(self, task_manager: TaskManager, root_password: str, internet_available: bool):
        arch_config = read_config(update_file=True)

        if arch_config['aur'] or arch_config['repositories']:
            self.disk_cache_updater = ArchDiskCacheUpdater(task_man=task_manager,
                                                           arch_config=arch_config,
                                                           i18n=self.i18n,
                                                           logger=self.context.logger,
                                                           controller=self,
                                                           internet_available=internet_available)
            self.disk_cache_updater.start()

        if arch_config['aur']:
            ArchCompilationOptimizer(arch_config, self.i18n, self.context.logger, task_manager).start()

        CategoriesDownloader(id_='Arch', http_client=self.context.http_client, logger=self.context.logger,
                             manager=self, url_categories_file=URL_CATEGORIES_FILE, disk_cache_dir=ARCH_CACHE_PATH,
                             categories_path=CATEGORIES_FILE_PATH,
                             before=lambda: self._start_category_task(task_manager),
                             after=lambda: self._finish_category_task(task_manager)).start()

        if arch_config['aur'] and internet_available:
            self.index_aur = AURIndexUpdater(self.context)
            self.index_aur.start()

        refresh_mirrors = None
        if internet_available and arch_config['repositories'] and arch_config['refresh_mirrors_startup'] \
                and pacman.is_mirrors_available() and mirrors.should_sync(self.logger):

            refresh_mirrors = RefreshMirrors(taskman=task_manager, i18n=self.i18n,
                                             root_password=root_password, logger=self.logger,
                                             sort_limit=arch_config['mirrors_sort_limit'])
            refresh_mirrors.start()

        if internet_available and (refresh_mirrors or (arch_config['sync_databases_startup'] and database.should_sync(arch_config, None, self.logger))):
            SyncDatabases(taskman=task_manager, root_password=root_password, i18n=self.i18n,
                          logger=self.logger, refresh_mirrors=refresh_mirrors).start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        installed = self.read_installed(disk_loader=None, internet_available=internet_available).installed

        aur_type, repo_type = self.i18n['gem.arch.type.aur.label'], self.i18n['gem.arch.type.arch_repo.label']

        return [PackageUpdate(p.name, p.latest_version, aur_type if p.repository == 'aur' else repo_type, p.name) for p in installed if p.update and not p.is_update_ignored()]

    def list_warnings(self, internet_available: bool) -> List[str]:
        warnings = []

        if self.arch_distro:
            if not pacman.is_available():
                warnings.append(self.i18n['arch.warning.disabled'].format(bold('pacman')))

            if not self._is_wget_available():
                warnings.append(self.i18n['arch.warning.disabled'].format(bold('wget')))

            if not git.is_enabled():
                warnings.append(self.i18n['arch.warning.git'].format(bold('git')))

        return warnings

    def list_suggestions(self, limit: int, filter_installed: bool) -> List[PackageSuggestion]:
        self.logger.info("Downloading suggestions file {}".format(SUGGESTIONS_FILE))
        file = self.http_client.get(SUGGESTIONS_FILE)

        if not file or not file.text:
            self.logger.warning("No suggestion could be read from {}".format(SUGGESTIONS_FILE))
        else:
            self.logger.info("Mapping suggestions")
            suggestions = {}

            for l in file.text.split('\n'):
                if l:
                    if limit <= 0 or len(suggestions) < limit:
                        lsplit = l.split('=')
                        name = lsplit[1].strip()

                        if not filter_installed or not pacman.check_installed(name):
                            suggestions[name] = SuggestionPriority(int(lsplit[0]))

            api_res = self.aur_client.get_info(suggestions.keys())

            if api_res:
                res = []
                for pkg in api_res:
                    if pkg.get('Name') in suggestions:
                        res.append(PackageSuggestion(self.mapper.map_api_data(pkg, {}, self.categories), suggestions[pkg['Name']]))

                self.logger.info("Mapped {} suggestions".format(len(suggestions)))
                return res

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: ArchPackage):
        if pkg.command:
            subprocess.Popen(args=[pkg.command], shell=True, env={**os.environ})

    def get_screenshots(self, pkg: SoftwarePackage) -> List[str]:
        pass

    def _gen_bool_selector(self, id_: str, label_key: str, tooltip_key: str, value: bool, max_width: int,
                           capitalize_label: bool = True, label_params: Optional[list] = None, tooltip_params: Optional[list] = None) -> SingleSelectComponent:
        opts = [InputOption(label=self.i18n['yes'].capitalize(), value=True),
                InputOption(label=self.i18n['no'].capitalize(), value=False)]

        lb = self.i18n[label_key]

        if label_params:
            lb = lb.format(*label_params)

        tip = self.i18n[tooltip_key]

        if tooltip_params:
            tip = tip.format(*tooltip_params)

        return SingleSelectComponent(label=lb,
                                     options=opts,
                                     default_option=[o for o in opts if o.value == value][0],
                                     max_per_line=len(opts),
                                     type_=SelectViewType.RADIO,
                                     tooltip=tip,
                                     max_width=max_width,
                                     id_=id_,
                                     capitalize_label=capitalize_label)

    def get_settings(self, screen_width: int, screen_height: int) -> ViewComponent:
        local_config = read_config()
        max_width = floor(screen_width * 0.25)

        db_sync_start = self._gen_bool_selector(id_='sync_dbs_start',
                                                label_key='arch.config.sync_dbs',
                                                tooltip_key='arch.config.sync_dbs_start.tip',
                                                value=bool(local_config['sync_databases_startup']),
                                                max_width=max_width)

        db_sync_start.label += ' ( {} )'.format(self.i18n['initialization'].capitalize())

        fields = [
            self._gen_bool_selector(id_='repos',
                                    label_key='arch.config.repos',
                                    tooltip_key='arch.config.repos.tip',
                                    value=bool(local_config['repositories']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='aur',
                                    label_key='arch.config.aur',
                                    tooltip_key='arch.config.aur.tip',
                                    value=local_config['aur'],
                                    max_width=max_width,
                                    capitalize_label=False),
            self._gen_bool_selector(id_='opts',
                                    label_key='arch.config.optimize',
                                    tooltip_key='arch.config.optimize.tip',
                                    value=bool(local_config['optimize']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='autoprovs',
                                    label_key='arch.config.automatch_providers',
                                    tooltip_key='arch.config.automatch_providers.tip',
                                    value=bool(local_config['automatch_providers']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='check_dependency_breakage',
                                    label_key='arch.config.check_dependency_breakage',
                                    tooltip_key='arch.config.check_dependency_breakage.tip',
                                    value=bool(local_config['check_dependency_breakage']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='mthread_download',
                                    label_key='arch.config.pacman_mthread_download',
                                    tooltip_key='arch.config.pacman_mthread_download.tip',
                                    value=local_config['repositories_mthread_download'],
                                    max_width=max_width,
                                    capitalize_label=True),
            self._gen_bool_selector(id_='sync_dbs',
                                    label_key='arch.config.sync_dbs',
                                    tooltip_key='arch.config.sync_dbs.tip',
                                    value=bool(local_config['sync_databases']),
                                    max_width=max_width),
            db_sync_start,
            self._gen_bool_selector(id_='clean_cached',
                                    label_key='arch.config.clean_cache',
                                    tooltip_key='arch.config.clean_cache.tip',
                                    value=bool(local_config['clean_cached']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='suggest_unneeded_uninstall',
                                    label_key='arch.config.suggest_unneeded_uninstall',
                                    tooltip_params=['"{}"'.format(self.i18n['arch.config.suggest_optdep_uninstall'])],
                                    tooltip_key='arch.config.suggest_unneeded_uninstall.tip',
                                    value=bool(local_config['suggest_unneeded_uninstall']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='suggest_optdep_uninstall',
                                    label_key='arch.config.suggest_optdep_uninstall',
                                    tooltip_key='arch.config.suggest_optdep_uninstall.tip',
                                    value=bool(local_config['suggest_optdep_uninstall']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='ref_mirs',
                                    label_key='arch.config.refresh_mirrors',
                                    tooltip_key='arch.config.refresh_mirrors.tip',
                                    value=bool(local_config['refresh_mirrors_startup']),
                                    max_width=max_width),
            TextInputComponent(id_='mirrors_sort_limit',
                               label=self.i18n['arch.config.mirrors_sort_limit'],
                               tooltip=self.i18n['arch.config.mirrors_sort_limit.tip'],
                               only_int=True,
                               max_width=max_width,
                               value=local_config['mirrors_sort_limit'] if isinstance(local_config['mirrors_sort_limit'], int) else ''),
            new_select(id_='aur_build_only_chosen',
                       label=self.i18n['arch.config.aur_build_only_chosen'],
                       tip=self.i18n['arch.config.aur_build_only_chosen.tip'],
                       opts=[(self.i18n['yes'].capitalize(), True, None),
                             (self.i18n['no'].capitalize(), False, None),
                             (self.i18n['ask'].capitalize(), None, None),
                             ],
                       value=local_config['aur_build_only_chosen'],
                       max_width=max_width,
                       type_=SelectViewType.RADIO,
                       capitalize_label=False),
            new_select(label=self.i18n['arch.config.edit_aur_pkgbuild'],
                       tip=self.i18n['arch.config.edit_aur_pkgbuild.tip'],
                       id_='edit_aur_pkgbuild',
                       opts=[(self.i18n['yes'].capitalize(), True, None),
                             (self.i18n['no'].capitalize(), False, None),
                             (self.i18n['ask'].capitalize(), None, None),
                             ],
                       value=local_config['edit_aur_pkgbuild'],
                       max_width=max_width,
                       type_=SelectViewType.RADIO,
                       capitalize_label=False),
            self._gen_bool_selector(id_='aur_remove_build_dir',
                                    label_key='arch.config.aur_remove_build_dir',
                                    tooltip_key='arch.config.aur_remove_build_dir.tip',
                                    value=bool(local_config['aur_remove_build_dir']),
                                    max_width=max_width,
                                    capitalize_label=False),
            FileChooserComponent(id_='aur_build_dir',
                                 label=self.i18n['arch.config.aur_build_dir'],
                                 tooltip=self.i18n['arch.config.aur_build_dir.tip'].format(BUILD_DIR),
                                 max_width=max_width,
                                 file_path=local_config['aur_build_dir'],
                                 capitalize_label=False,
                                 directory=True)
        ]

        return PanelComponent([FormComponent(fields, spaces=False)])

    def save_settings(self, component: PanelComponent) -> Tuple[bool, Optional[List[str]]]:
        config = read_config()

        form_install = component.components[0]
        config['repositories'] = form_install.get_component('repos').get_selected()
        config['aur'] = form_install.get_component('aur').get_selected()
        config['optimize'] = form_install.get_component('opts').get_selected()
        config['sync_databases'] = form_install.get_component('sync_dbs').get_selected()
        config['sync_databases_startup'] = form_install.get_component('sync_dbs_start').get_selected()
        config['clean_cached'] = form_install.get_component('clean_cached').get_selected()
        config['refresh_mirrors_startup'] = form_install.get_component('ref_mirs').get_selected()
        config['mirrors_sort_limit'] = form_install.get_component('mirrors_sort_limit').get_int_value()
        config['repositories_mthread_download'] = form_install.get_component('mthread_download').get_selected()
        config['automatch_providers'] = form_install.get_component('autoprovs').get_selected()
        config['edit_aur_pkgbuild'] = form_install.get_component('edit_aur_pkgbuild').get_selected()
        config['aur_remove_build_dir'] = form_install.get_component('aur_remove_build_dir').get_selected()
        config['aur_build_dir'] = form_install.get_component('aur_build_dir').file_path
        config['aur_build_only_chosen'] = form_install.get_component('aur_build_only_chosen').get_selected()
        config['check_dependency_breakage'] = form_install.get_component('check_dependency_breakage').get_selected()
        config['suggest_optdep_uninstall'] = form_install.get_component('suggest_optdep_uninstall').get_selected()
        config['suggest_unneeded_uninstall'] = form_install.get_component('suggest_unneeded_uninstall').get_selected()

        if not config['aur_build_dir']:
            config['aur_build_dir'] = None

        try:
            save_config(config, CONFIG_FILE)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def get_upgrade_requirements(self, pkgs: List[ArchPackage], root_password: str, watcher: ProcessWatcher) -> UpgradeRequirements:
        self.aur_client.clean_caches()
        arch_config = read_config()
        self._sync_databases(arch_config=arch_config, root_password=root_password, handler=ProcessHandler(watcher), change_substatus=False)
        self.aur_client.clean_caches()
        try:
            return UpdatesSummarizer(self.aur_client, self.i18n, self.logger, self.deps_analyser, watcher).summarize(pkgs, root_password, arch_config)
        except PackageNotFoundException:
            pass  # when nothing is returned, the upgrade is called off by the UI

    def get_custom_actions(self) -> List[CustomSoftwareAction]:
        actions = []

        arch_config = read_config()

        if pacman.is_mirrors_available():
            actions.append(self.custom_actions['ref_mirrors'])

        actions.append(self.custom_actions['ref_dbs'])
        actions.append(self.custom_actions['clean_cache'])

        if bool(arch_config['repositories']):
            actions.append(self.custom_actions['sys_up'])

        if pacman.is_snapd_installed():
            actions.append(self.custom_actions['setup_snapd'])

        return actions

    def fill_sizes(self, pkgs: List[ArchPackage]):
        installed, new, all_names, installed_names = [], [], [], []

        for p in pkgs:
            if p.repository != 'aur':
                all_names.append(p.name)
                if p.installed:
                    installed.append(p)
                    installed_names.append(p.name)
                else:
                    new.append(p)

        new_sizes = pacman.map_update_sizes(all_names)

        if new_sizes:
            if new:
                for p in new:
                    p.size = new_sizes.get(p.name)

            if installed:
                installed_sizes = pacman.get_installed_size(installed_names)

                for p in installed:
                    p.size = installed_sizes.get(p.name)
                    new_size = new_sizes.get(p.name)

                    if p.size is None:
                        p.size = new_size
                    elif new_size is not None:
                        p.size = new_size - p.size

    def upgrade_system(self, root_password: str, watcher: ProcessWatcher) -> bool:
        # repo_map = pacman.map_repositories()
        installed = self.read_installed(limit=-1, only_apps=False, pkg_types=None, internet_available=internet.is_available(), disk_loader=None).installed

        if not installed:
            watcher.show_message(title=self.i18n['arch.custom_action.upgrade_system'],
                                 body=self.i18n['arch.custom_action.upgrade_system.no_updates'],
                                 type_=MessageType.INFO)
            return False

        to_update = [p for p in installed if p.repository != 'aur' and p.update]

        if not to_update:
            watcher.show_message(title=self.i18n['arch.custom_action.upgrade_system'],
                                 body=self.i18n['arch.custom_action.upgrade_system.no_updates'],
                                 type_=MessageType.INFO)
            return False

        # icon_path = get_repo_icon_path()

        # pkg_opts, size = [], 0

        # self.fill_sizes(to_update)
        #
        # for pkg in to_update:
        #     lb = '{} ( {} > {} ) - {}: {}'.format(pkg.name,
        #                                           pkg.version,
        #                                           pkg.latest_version,
        #                                           self.i18n['size'].capitalize(),
        #                                           '?' if pkg.size is None else get_human_size_str(pkg.size))
        #     pkg_opts.append(InputOption(label=lb,
        #                                 value=pkg.name,
        #                                 read_only=True,
        #                                 icon_path=icon_path))
        #
        #     if pkg.size is not None:
        #         size += pkg.size
        #
        # pkg_opts.sort(key=lambda o: o.label)

        # select = MultipleSelectComponent(label='',
        #                                  options=pkg_opts,
        #                                  default_options=set(pkg_opts))

        # if watcher.request_confirmation(title=self.i18n['arch.custom_action.upgrade_system'],
        #                                 body="{}. {}: {}".format(self.i18n['arch.custom_action.upgrade_system.pkgs'],
        #                                                          self.i18n['size'].capitalize(),
        #                                                          get_human_size_str(size)),
        #                                 confirmation_label=self.i18n['proceed'].capitalize(),
        #                                 deny_label=self.i18n['cancel'].capitalize(),
        #                                 components=[select]):

            # watcher.change_substatus(self.i18n['arch.custom_action.upgrade_system.substatus'])
        handler = ProcessHandler(watcher)

        if self._is_database_locked(handler, root_password):
            return False

        success, output = handler.handle_simple(pacman.upgrade_system(root_password))

        if not success or 'error:' in output:
            watcher.show_message(title=self.i18n['arch.custom_action.upgrade_system'],
                                 body="An error occurred during the upgrade process. Check out the {}".format(
                                     bold('Details')),
                                 type_=MessageType.ERROR)
            return False
        else:
            database.register_sync(self.logger)
            msg = '<p>{}</p><br/>{}</p><p>{}</p>'.format(self.i18n['action.update.success.reboot.line1'],
                                                         self.i18n['action.update.success.reboot.line2'],
                                                         self.i18n['action.update.success.reboot.line3'])
            watcher.request_reboot(msg)
            return True

    def clean_cache(self, root_password: str, watcher: ProcessWatcher) -> bool:

        cache_dir = pacman.get_cache_dir()

        if not cache_dir or not os.path.isdir(cache_dir):
            watcher.show_message(title=self.i18n['arch.custom_action.clean_cache'].capitalize(),
                                 body=self.i18n['arch.custom_action.clean_cache.no_dir'.format(bold(cache_dir))].capitalize(),
                                 type_=MessageType.WARNING)
            return True

        text = '<p>{}.</p><p>{}.</p><p>{}.</p>'.format(self.i18n['arch.custom_action.clean_cache.msg1'],
                                                       self.i18n['arch.custom_action.clean_cache.msg2'],
                                                       self.i18n['arch.custom_action.clean_cache.msg3'])

        if watcher.request_confirmation(title=self.i18n['arch.custom_action.clean_cache'].capitalize(),
                                        body=text,
                                        confirmation_label=self.i18n['clean'].capitalize(),
                                        deny_label=self.i18n['cancel'].capitalize()):

            handler = ProcessHandler(watcher)
            rm = SimpleProcess(cmd=['rm', '-rf', cache_dir], root_password=root_password)
            success, _ = handler.handle_simple(rm)

            if success:
                watcher.show_message(title=self.i18n['arch.custom_action.clean_cache'].capitalize(),
                                     body=self.i18n['arch.custom_action.clean_cache.success'],
                                     type_=MessageType.INFO)

                mkcache = SimpleProcess(cmd=['mkdir', '-p', cache_dir], root_password=root_password)
                handler.handle_simple(mkcache)
                return True
            else:
                watcher.show_message(title=self.i18n['arch.custom_action.clean_cache'].capitalize(),
                                     body=self.i18n['arch.custom_action.clean_cache.fail'],
                                     type_=MessageType.ERROR)
                return False

        return True

    def _list_ignored_updates(self) -> Set[str]:
        ignored = set()
        if os.path.exists(UPDATES_IGNORED_FILE):
            with open(UPDATES_IGNORED_FILE) as f:
                ignored_lines = f.readlines()

            for line in ignored_lines:
                if line:
                    line_clean = line.strip()

                    if line_clean:
                        ignored.add(line_clean)

        return ignored

    def _write_ignored(self, names: Set[str]):
        Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        ignored_list = [*names]
        ignored_list.sort()

        with open(UPDATES_IGNORED_FILE, 'w+') as f:
            if ignored_list:
                for pkg in ignored_list:
                    f.write('{}\n'.format(pkg))
            else:
                f.write('')

    def ignore_update(self, pkg: ArchPackage):
        ignored = self._list_ignored_updates()

        if pkg.name not in ignored:
            ignored.add(pkg.name)
            self._write_ignored(ignored)

        pkg.update_ignored = True

    def _revert_ignored_updates(self, pkgs: Iterable[str]):
        ignored = self._list_ignored_updates()

        for p in pkgs:
            if p in ignored:
                ignored.remove(p)

        self._write_ignored(ignored)

    def revert_ignored_update(self, pkg: ArchPackage):
        self._revert_ignored_updates({pkg.name})
        pkg.update_ignored = False

    def _add_as_editable_pkgbuild(self, pkgname: str):
        try:
            Path('/'.join(EDITABLE_PKGBUILDS_FILE.split('/')[0:-1])).mkdir(parents=True, exist_ok=True)

            editable = self._read_editable_pkgbuilds()

            if pkgname not in editable:
                editable.add(pkgname)

            self._write_editable_pkgbuilds(editable)
            return True
        except:
            traceback.print_exc()
            return False

    def _write_editable_pkgbuilds(self, editable: Set[str]):
        if editable:
            with open(EDITABLE_PKGBUILDS_FILE, 'w+') as f:
                for name in sorted([*editable]):
                    f.write('{}\n'.format(name))
        else:
            os.remove(EDITABLE_PKGBUILDS_FILE)

    def _remove_from_editable_pkgbuilds(self, pkgname: str):
        if os.path.exists(EDITABLE_PKGBUILDS_FILE):
            try:
                editable = self._read_editable_pkgbuilds()

                if pkgname in editable:
                    editable.remove(pkgname)

                self._write_editable_pkgbuilds(editable)
            except:
                traceback.print_exc()
                return False

        return True

    def _read_editable_pkgbuilds(self) -> Set[str]:
        if os.path.exists(EDITABLE_PKGBUILDS_FILE):
            with open(EDITABLE_PKGBUILDS_FILE) as f:
                return {l.strip() for l in f.readlines() if l and l.strip()}

        return set()

    def enable_pkgbuild_edition(self, pkg: ArchPackage, root_password: str, watcher: ProcessWatcher):
        if self._add_as_editable_pkgbuild(pkg.name):
            pkg.pkgbuild_editable = True

    def disable_pkgbuild_edition(self, pkg: ArchPackage, root_password: str, watcher: ProcessWatcher):
        if self._remove_from_editable_pkgbuilds(pkg.name):
            pkg.pkgbuild_editable = False

    def setup_snapd(self, root_password: str, watcher: ProcessWatcher) -> bool:
        # checking services
        missing_items = []
        for serv, active in system.check_enabled_services('snapd.service', 'snapd.socket').items():
            if not active:
                missing_items.append(InputOption(label=self.i18n['snap.custom_action.setup_snapd.service_disabled'].format("'{}'".format(serv)),
                                                 value='enable:{}'.format(serv),
                                                 read_only=True))

        for serv, active in system.check_active_services('snapd.service', 'snapd.socket').items():
            if not active:
                missing_items.append(InputOption(label=self.i18n['snap.custom_action.setup_snapd.service_inactive'].format("'{}'".format(serv)),
                                                 value='start:{}'.format(serv),
                                                 read_only=True))

        link = '/snap'
        link_dest = '/var/lib/snapd/snap'
        if not os.path.exists('/snap'):
            missing_items.append(InputOption(label=self.i18n['snap.custom_action.setup_snapd.missing_link'].format("'{}'".format(link), "'{}'".format(link_dest)),
                                             value='link:{}:{}'.format(link, link_dest),
                                             read_only=True))

        if missing_items:
            actions = MultipleSelectComponent(label=self.i18n['snap.custom_action.setup_snapd.required_actions'],
                                              options=missing_items,
                                              default_options=set(missing_items),
                                              max_per_line=1,
                                              spaces=False)
            if watcher.request_confirmation(title=self.i18n['confirmation'].capitalize(),
                                            body='',
                                            components=[actions],
                                            confirmation_label=self.i18n['proceed'].capitalize(),
                                            deny_label=self.i18n['cancel'].capitalize()):

                pwd, valid_pwd = watcher.request_root_password()

                if valid_pwd:
                    handler = ProcessHandler(watcher)
                    for a in missing_items:
                        action = a.value.split(':')

                        if action[0] == 'enable':
                            msg = 'Enabling service {}'.format(action[1])
                            watcher.print(msg)
                            self.logger.info(msg)
                            proc = SimpleProcess(['systemctl', 'enable', '--now', action[1]], root_password=pwd)
                        elif action[0] == 'start':
                            msg = 'Starting service {}'.format(action[1])
                            watcher.print(msg)
                            self.logger.info(msg)
                            proc = SimpleProcess(['systemctl', 'start', action[1]], root_password=pwd)
                        elif action[0] == 'link':
                            msg = 'Creating symbolic link {} for {}'.format(action[1], action[2])
                            watcher.print(msg)
                            self.logger.info(msg)
                            proc = SimpleProcess(['ln', '-s', action[2], action[1]], root_password=pwd)
                        else:
                            msg = "Wrong action '{}'".format(action)
                            watcher.print(msg)
                            self.logger.warning(msg)
                            proc = None

                        if not proc:
                            return False

                        success, output = handler.handle_simple(proc)

                        if not success:
                            watcher.show_message(title=self.i18n['error'].capitalize(),
                                                 body=output,
                                                 type_=MessageType.ERROR)
                            return False

                    watcher.show_message(title=self.i18n['snap.custom_action.setup_snapd.ready'],
                                         body=self.i18n['snap.custom_action.setup_snapd.ready.body'],
                                         type_=MessageType.INFO)
            return True
        else:
            watcher.show_message(title=self.i18n['snap.custom_action.setup_snapd.ready'],
                                 body=self.i18n['snap.custom_action.setup_snapd.ready.body'],
                                 type_=MessageType.INFO)
            return True

    def _gen_custom_pkgbuild_if_required(self, context: TransactionContext) -> Optional[str]:
        build_only_chosen = context.config.get('aur_build_only_chosen')

        pkgs_to_build = aur.map_srcinfo(string=self._read_srcinfo(context), pkgname=None, fields={'pkgname'}).get('pkgname')

        if isinstance(pkgs_to_build, str):
            pkgs_to_build = {pkgs_to_build}
        else:
            pkgs_to_build = {*pkgs_to_build}

        if build_only_chosen is False:
            context.pkgs_to_build = pkgs_to_build
            return

        # checking if more than one package is mapped for this pkgbuild

        if not pkgs_to_build or not isinstance(pkgs_to_build, set) or len(pkgs_to_build) == 1 or context.name not in pkgs_to_build:
            context.pkgs_to_build = pkgs_to_build
            return

        if build_only_chosen is None:
            if not context.dependency:
                pkgnames = [InputOption(label=n, value=n, read_only=False) for n in pkgs_to_build if n != context.name]
                select = MultipleSelectComponent(label='',
                                                 options=pkgnames,
                                                 default_options={*pkgnames},
                                                 max_per_line=1)

                if not context.watcher.request_confirmation(title=self.i18n['warning'].capitalize(),
                                                            body=self.i18n['arch.aur.sync.several_names.popup.body'].format(bold(context.name)) + ':',
                                                            components=[select],
                                                            confirmation_label=self.i18n['arch.aur.sync.several_names.popup.bt_only_chosen'].format(context.name),
                                                            deny_label=self.i18n['arch.aur.sync.several_names.popup.bt_selected']):
                    context.pkgs_to_build = {context.name, *select.get_selected_values()}

        pkgbuild_path = '{}/PKGBUILD'.format(context.project_dir)
        with open(pkgbuild_path) as f:
            current_pkgbuild = f.read()

        if context.pkgs_to_build:
            names = '({})'.format(' '.join(("'{}'".format(p) for p in context.pkgs_to_build)))
        else:
            names = context.name
            context.pkgs_to_build = {context.name}

        new_pkgbuild = RE_PKGBUILD_PKGNAME.sub("pkgname={}".format(names), current_pkgbuild)
        custom_pkgbuild_path = pkgbuild_path + '_CUSTOM'

        with open(custom_pkgbuild_path, 'w+') as f:
            f.write(new_pkgbuild)

        new_srcinfo = makepkg.gen_srcinfo(context.project_dir, custom_pkgbuild_path)

        with open('{}/.SRCINFO'.format(context.project_dir), 'w+') as f:
            f.write(new_srcinfo)

        return custom_pkgbuild_path

    def _list_opt_deps_with_no_hard_requirements(self, source_pkgs: Set[str], installed_provided: Optional[Dict[str, Set[str]]] = None) -> Set[str]:
        optdeps = set()

        for deps in pacman.map_optional_deps(names=source_pkgs, remote=False).values():
            optdeps.update(deps.keys())

        res = set()
        if optdeps:
            all_provided = pacman.map_provided() if not installed_provided else installed_provided

            real_optdeps = set()
            for o in optdeps:
                dep_providers = all_provided.get(o)

                if dep_providers:
                    for p in dep_providers:
                        if p not in source_pkgs:
                            real_optdeps.add(p)

            if real_optdeps:
                for p in real_optdeps:
                    try:
                        reqs = pacman.list_hard_requirements(p, self.logger)

                        if reqs is not None and (not reqs or reqs.issubset(source_pkgs)):
                            res.add(p)
                    except PackageInHoldException:
                        self.logger.warning("There is a requirement in hold for opt dep '{}'".format(p))
                        continue

        return res
