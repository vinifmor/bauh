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
from pathlib import Path
from pwd import getpwnam
from threading import Thread
from typing import List, Set, Type, Tuple, Dict, Iterable, Optional, Collection, Generator

from dateutil.parser import parse as parse_date

from bauh import __app_name__
from bauh.api.abstract.controller import SearchResult, SoftwareManager, ApplicationContext, UpgradeRequirements, \
    TransactionResult, SoftwareAction, SettingsView, SettingsController
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import PackageUpdate, PackageHistory, SoftwarePackage, PackageStatus, \
    CustomSoftwareAction, PackageSuggestion
from bauh.api.abstract.view import MessageType, FormComponent, InputOption, SingleSelectComponent, SelectViewType, \
    ViewComponent, PanelComponent, MultipleSelectComponent, TextInputComponent, TextInputType, \
    FileChooserComponent, TextComponent
from bauh.api.exception import NoInternetException
from bauh.api.paths import TEMP_DIR
from bauh.commons import system
from bauh.commons.boot import CreateConfigFile
from bauh.commons.category import CategoriesDownloader
from bauh.commons.html import bold
from bauh.commons.suggestions import sort_by_priority
from bauh.commons.system import SystemProcess, ProcessHandler, new_subprocess, run_cmd, SimpleProcess
from bauh.commons.util import datetime_as_milis
from bauh.commons.view_utils import new_select
from bauh.gems.arch import aur, pacman, message, confirmation, disk, git, \
    gpg, URL_CATEGORIES_FILE, CATEGORIES_FILE_PATH, CUSTOM_MAKEPKG_FILE, \
    get_icon_path, database, mirrors, sorting, cpu_manager, UPDATES_IGNORED_FILE, \
    ARCH_CONFIG_DIR, EDITABLE_PKGBUILDS_FILE, URL_GPG_SERVERS, rebuild_detector, makepkg, sshell, get_repo_icon_path
from bauh.gems.arch.aur import AURClient
from bauh.gems.arch.config import get_build_dir, ArchConfigManager
from bauh.gems.arch.confirmation import confirm_missing_deps
from bauh.gems.arch.dependencies import DependenciesAnalyser
from bauh.gems.arch.download import MultithreadedDownloadService, ArchDownloadException
from bauh.gems.arch.exceptions import PackageNotFoundException, PackageInHoldException
from bauh.gems.arch.mapper import AURDataMapper
from bauh.gems.arch.model import ArchPackage
from bauh.gems.arch.output import TransactionStatusHandler
from bauh.gems.arch.pacman import RE_DEP_OPERATORS
from bauh.gems.arch.proc_util import write_as_user
from bauh.gems.arch.suggestions import RepositorySuggestionsDownloader
from bauh.gems.arch.updates import UpdatesSummarizer
from bauh.gems.arch.worker import AURIndexUpdater, ArchDiskCacheUpdater, ArchCompilationOptimizer, RefreshMirrors, \
    SyncDatabases

URL_GIT = 'https://aur.archlinux.org/{}.git'
URL_SRC_INFO = 'https://aur.archlinux.org/cgit/aur.git/plain/.SRCINFO?h='

RE_SPLIT_VERSION = re.compile(r'([=><]+)')

SOURCE_FIELDS = ('source', 'source_x86_64')
RE_PRE_DOWNLOAD_WL_PROTOCOLS = re.compile(r'^(.+::)?(https?|ftp)://.+')
RE_PRE_DOWNLOAD_BL_EXT = re.compile(r'.+\.(git|gpg)$')
RE_PKGBUILD_PKGNAME = re.compile(r'pkgname\s*=.+')
RE_CONFLICT_DETECTED = re.compile(r'\n::\s*(.+)\s+are in conflict\s*.')
RE_DEPENDENCY_BREAKAGE = re.compile(r'\n?::\s+installing\s+(.+\s\(.+\))\sbreaks\sdependency\s\'(.+)\'\srequired\sby\s(.+)\s*', flags=re.IGNORECASE)
RE_PKG_ENDS_WITH_BIN = re.compile(r'.+[\-_]bin$')


class TransactionContext:

    def __init__(self, aur_supported: bool, name: str = None, base: str = None, maintainer: str = None, watcher: ProcessWatcher = None,
                 handler: ProcessHandler = None, dependency: bool = None, skip_opt_deps: bool = False, root_password: Optional[str] = None,
                 build_dir: str = None, project_dir: str = None, change_progress: bool = False, arch_config: dict = None,
                 install_files: Set[str] = None, repository: str = None, pkg: ArchPackage = None,
                 remote_repo_map: Dict[str, str] = None, provided_map: Dict[str, Set[str]] = None,
                 remote_provided_map: Dict[str, Set[str]] = None, aur_idx: Set[str] = None,
                 missing_deps: List[Tuple[str, str]] = None, installed: Set[str] = None, removed: Dict[str, SoftwarePackage] = None,
                 disk_loader: DiskCacheLoader = None, disk_cache_updater: Thread = None,
                 new_pkg: bool = False, custom_pkgbuild_path: str = None,
                 pkgs_to_build: Set[str] = None, last_modified: Optional[int] = None,
                 commit: Optional[str] = None, update_aur_index: bool = False):
        self.aur_supported = aur_supported
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
        self.last_modified = last_modified
        self.commit = commit
        self.update_aur_index = update_aur_index

    @classmethod
    def gen_context_from(cls, pkg: ArchPackage, arch_config: dict, root_password: Optional[str], handler: ProcessHandler, aur_supported: Optional[bool] = None) -> "TransactionContext":
        return cls(name=pkg.name, base=pkg.get_base_name(), maintainer=pkg.maintainer, repository=pkg.repository,
                   arch_config=arch_config, watcher=handler.watcher, handler=handler, skip_opt_deps=True,
                   change_progress=True, root_password=root_password, dependency=False,
                   installed=set(), removed={}, new_pkg=not pkg.installed, last_modified=pkg.last_modified,
                   aur_supported=aur_supported if aur_supported is not None else (pkg.repository == 'aur' or aur.is_supported(arch_config)))

    def get_base_name(self):
        return self.base if self.base else self.name

    def get_project_dir(self):
        return self.project_dir or '.'

    def clone_base(self):
        return TransactionContext(watcher=self.watcher, handler=self.handler, root_password=self.root_password,
                                  arch_config=self.config, installed=set(), removed={}, aur_supported=self.aur_supported)

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
            if self.aur_supported:
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


class ArchManager(SoftwareManager, SettingsController):

    def __init__(self, context: ApplicationContext, disk_cache_updater: Optional[ArchDiskCacheUpdater] = None):
        super(ArchManager, self).__init__(context=context)
        self.aur_cache = context.cache_factory.new()
        # context.disk_loader_factory.map(ArchPackage, self.aur_cache) TODO
        self.configman = ArchConfigManager()
        self.aur_mapper = AURDataMapper(http_client=context.http_client, i18n=context.i18n, logger=context.logger)
        self.i18n = context.i18n
        self.aur_client = AURClient(http_client=context.http_client, logger=context.logger, x86_64=context.is_system_x86_64())
        self.dcache_updater = None
        self.logger = context.logger
        self.enabled = True
        self.arch_distro = context.distro == 'arch'
        self.categories = {}
        self.deps_analyser = DependenciesAnalyser(self.aur_client, self.i18n, self.logger)
        self.http_client = context.http_client
        self._custom_actions: Optional[Dict[str, CustomSoftwareAction]] = None
        self.index_aur = None
        self.re_file_conflict = re.compile(r'[\w\d\-_.]+:')
        self.disk_cache_updater = disk_cache_updater
        self.pkgbuilder_user: Optional[str] = f'{__app_name__}-aur' if context.root_user else None
        self._suggestions_downloader: Optional[RepositorySuggestionsDownloader] = None

    def refresh_mirrors(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
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

        sort_limit = self.configman.get_config()['mirrors_sort_limit']

        if sort_limit is not None and isinstance(sort_limit, int) and sort_limit >= 0:
            watcher.change_substatus(self.i18n['arch.custom_action.refresh_mirrors.status.sorting'])
            handler.handle_simple(pacman.sort_fastest_mirrors(root_password, sort_limit))

        mirrors.register_sync(self.logger)

        watcher.change_substatus(self.i18n['arch.sync_databases.substatus'])
        return self.sync_databases(root_password=root_password, watcher=watcher)

    def sync_databases(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
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

    def _fill_repos_search_results(self, query: str, output: dict):
        ti = time.time()
        output['repositories'] = pacman.search(query)
        tf = time.time()
        self.logger.info("Repositories search took {0:.2f} seconds".format(tf - ti))

    def _fill_aur_search_results(self, query: str, output: dict):
        ti = time.time()
        api_res = self.aur_client.search(query)

        pkgs_found = None
        if api_res and api_res.get('results'):
            pkgs_found = api_res['results']
        else:
            tii = time.time()
            if self.index_aur:
                self.index_aur.join()

            aur_index = self.aur_client.read_local_index()
            if aur_index:
                self.logger.info("Querying through the local AUR index")
                to_query = set()
                for norm_name, real_name in aur_index.items():
                    if query in norm_name:
                        to_query.add(real_name)

                    if len(to_query) == 25:
                        break

                pkgs_found = self.aur_client.get_info(to_query)

            tif = time.time()
            self.logger.info("Query through local AUR index took {0:.2f} seconds".format(tif - tii))

        if pkgs_found:
            for pkg in pkgs_found:
                output['aur'][pkg['Name']] = pkg

        tf = time.time()
        self.logger.info("AUR search took {0:.2f} seconds".format(tf - ti))

    def __fill_search_installed_and_matched(self, query: str, res: dict):
        matches = set()
        installed = pacman.list_installed_names()
        res['installed'] = installed
        res['installed_matches'] = matches

        if installed and ' ' not in query:  # already filling some matches only based on the query
            matches.update((name for name in installed if query in name))

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        if is_url:
            return SearchResult.empty()

        arch_config = self.configman.get_config()
        repos_supported, aur_supported = arch_config['repositories'], aur.is_supported(arch_config)

        if not any([repos_supported, aur_supported]):
            return SearchResult.empty()

        res = SearchResult.empty()

        search_output, search_threads = {'aur': {}, 'repositories': {}}, []
        t = Thread(target=self.__fill_search_installed_and_matched, args=(words, search_output), daemon=True)
        t.start()
        search_threads.append(t)

        if aur_supported:
            taur = Thread(target=self._fill_aur_search_results, args=(words, search_output), daemon=True)
            taur.start()
            search_threads.append(taur)

        if repos_supported:
            trepo = Thread(target=self._fill_repos_search_results, args=(words, search_output), daemon=True)
            trepo.start()
            search_threads.append(trepo)

        for t in search_threads:
            t.join()

        for name in {*search_output['repositories'].keys(), *search_output['aur'].keys()}:
            if name in search_output['installed']:
                search_output['installed_matches'].add(name)

        if search_output['installed_matches']:
            installed = self.read_installed(disk_loader=disk_loader, names=search_output['installed_matches']).installed

            for pkg in installed:
                if pkg.repository != 'aur':
                    if repos_supported:
                        res.installed.append(pkg)
                        if pkg.name in search_output['repositories']:
                            del search_output['repositories'][pkg.name]
                elif aur_supported:
                    res.installed.append(pkg)
                    if pkg.name in search_output['aur']:
                        del search_output['aur'][pkg.name]

        if search_output['repositories']:
            for pkgname, data in search_output['repositories'].items():
                res.new.append(ArchPackage(name=pkgname, i18n=self.i18n, **data))

        if search_output['aur']:
            for pkgname, apidata in search_output['aur'].items():
                res.new.append(self.aur_mapper.map_api_data(apidata, None, self.categories))

        res.update_total()
        return res

    def _fill_aur_pkgs_offline(self, aur_pkgs: dict,  arch_config: dict, output: List[ArchPackage], disk_loader: Optional[DiskCacheLoader]):
        self.logger.info("Reading cached data from installed AUR packages")

        editable_pkgbuilds = self._read_editable_pkgbuilds() if arch_config['edit_aur_pkgbuild'] is not False else None
        for name, data in aur_pkgs.items():
            pkg = ArchPackage(name=name, version=data.get('version'),
                              latest_version=data.get('version'), description=data.get('description'),
                              installed=True, repository='aur', i18n=self.i18n)

            pkg.categories = self.categories.get(pkg.name)
            pkg.pkgbuild_editable = pkg.name in editable_pkgbuilds if editable_pkgbuilds is not None else None

            if disk_loader:
                disk_loader.fill(pkg)

            pkg.status = PackageStatus.READY
            output.append(pkg)

    def _fill_aur_pkgs(self, aur_pkgs: dict, output: List[ArchPackage], disk_loader: Optional[DiskCacheLoader], internet_available: bool,
                       arch_config: dict, rebuild_check: Optional[Thread], rebuild_ignored: Optional[Thread], rebuild_output: Optional[Dict[str, Set[str]]]):

        if not internet_available:
            self._fill_aur_pkgs_offline(aur_pkgs=aur_pkgs, arch_config=arch_config,
                                        output=output, disk_loader=disk_loader)
            return

        pkgsinfo = self.aur_client.get_info(aur_pkgs.keys())

        if pkgsinfo is None:
            self._fill_aur_pkgs_offline(aur_pkgs=aur_pkgs, arch_config=arch_config, output=output, disk_loader=disk_loader)
        elif not pkgsinfo:
            self.logger.warning("No data found for the supposed installed AUR packages returned from AUR API's info endpoint")
        else:
            editable_pkgbuilds = self._read_editable_pkgbuilds() if arch_config['edit_aur_pkgbuild'] is not False else None

            ignore_rebuild_check = None
            if rebuild_ignored and rebuild_output is not None:
                rebuild_ignored.join()
                ignore_rebuild_check = rebuild_output['ignored']

            to_rebuild = None
            if rebuild_check and rebuild_output is not None:
                self.logger.info("Waiting for rebuild-detector")
                rebuild_check.join()
                to_rebuild = rebuild_output['to_rebuild']

            for pkgdata in pkgsinfo:
                pkg = self.aur_mapper.map_api_data(pkgdata, aur_pkgs, self.categories)
                pkg.pkgbuild_editable = pkg.name in editable_pkgbuilds if editable_pkgbuilds is not None else None

                if pkg.installed:
                    if disk_loader:
                        disk_loader.fill(pkg, sync=True)

                    pkg.update = self._check_aur_package_update(pkg=pkg,
                                                                installed_data=aur_pkgs.get(pkg.name, {}),
                                                                api_data=pkgdata)
                    pkg.aur_update = pkg.update  # used in 'set_rebuild_check'

                    if ignore_rebuild_check is not None:
                        pkg.allow_rebuild = pkg.name not in ignore_rebuild_check

                    if to_rebuild and not pkg.update and pkg.name in to_rebuild:
                        pkg.require_rebuild = True

                    pkg.update_state()

                pkg.status = PackageStatus.READY
                output.append(pkg)

    def _check_aur_package_update(self, pkg: ArchPackage, installed_data: dict, api_data: dict) -> bool:
        if pkg.last_modified is None:  # if last_modified is not available, then the install_date will be used instead
            install_date = installed_data.get('install_date')

            if install_date:
                try:
                    pkg.install_date = datetime_as_milis(parse_date(install_date))
                except ValueError:
                    self.logger.error(f"Could not parse 'install_date' ({install_date}) from AUR package '{pkg.name}'")
            else:
                self.logger.error(f"AUR package '{pkg.name}' install_date was not retrieved")

        return self.aur_mapper.check_update(pkg=pkg, last_modified=api_data['LastModified'])

    def _fill_repo_updates(self, updates: dict):
        updates.update(pacman.list_repository_updates())

    def _fill_repo_pkgs(self, repo_pkgs: dict, pkgs: list, aur_index: Optional[Set[str]], disk_loader: DiskCacheLoader):
        updates = {}

        thread_updates = Thread(target=self._fill_repo_updates, args=(updates,), daemon=True)
        thread_updates.start()

        repo_map = pacman.map_repositories(repo_pkgs)

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
                              categories=self.categories.get(name, []))

            if updates:
                update_version = updates.get(pkg.name)

                if update_version:
                    pkg.latest_version = update_version
                    pkg.update = True

            if disk_loader:
                disk_loader.fill(pkg, sync=True)

            if pkg.repository == 'aur':
                pkg.repository = None

                if aur_index and pkg.name not in aur_index:
                    removed_cat = self.i18n['arch.category.remove_from_aur']

                    if removed_cat not in pkg.categories:
                        pkg.categories.append(removed_cat)

            pkgs.append(pkg)

    def _wait_for_disk_cache(self):
        if self.disk_cache_updater and self.disk_cache_updater.is_alive():
            self.logger.info("Waiting for disk cache to be ready")
            self.disk_cache_updater.join()
            self.logger.info("Disk cache ready")

    def __fill_packages_to_rebuild(self, output: Dict[str, Set[str]], ignore_binaries: bool):
        if rebuild_detector.is_installed():
            self.logger.info("rebuild-detector: checking")
            to_rebuild = rebuild_detector.list_required_rebuild()

            if to_rebuild and ignore_binaries:
                to_rebuild = {p for p in to_rebuild if not RE_PKG_ENDS_WITH_BIN.match(p)}

            output['to_rebuild'].update(to_rebuild)
            self.logger.info("rebuild-detector: {} packages require rebuild".format(len(to_rebuild)))

    def __fill_ignored_by_rebuild_detector(self, output: Dict[str, Set[str]]):
        output['ignored'].update(rebuild_detector.list_ignored())

    def read_installed(self, disk_loader: Optional[DiskCacheLoader], limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None, names: Iterable[str] = None, wait_disk_cache: bool = True) -> SearchResult:
        self.aur_client.clean_caches()
        arch_config = self.configman.get_config()

        aur_supported, repos_supported = aur.is_supported(arch_config), arch_config['repositories']

        if not aur_supported and not repos_supported:
            return SearchResult.empty()

        rebuild_output, rebuild_check, rebuild_ignored = None, None, None
        if aur_supported and arch_config['aur_rebuild_detector']:
            rebuild_output = {'to_rebuild': set(), 'ignored': set()}
            rebuild_check = Thread(target=self.__fill_packages_to_rebuild,
                                   args=(rebuild_output, arch_config['aur_rebuild_detector_no_bin']),
                                   daemon=True)
            rebuild_check.start()

            rebuild_ignored = Thread(target=self.__fill_ignored_by_rebuild_detector, args=(rebuild_output, ), daemon=True)
            rebuild_ignored.start()

        installed = pacman.map_packages(names=names)

        aur_pkgs, repo_pkgs, aur_index = None, None, None

        if repos_supported:
            repo_pkgs = installed['signed']

        if installed['not_signed']:
            if aur_supported:
                if self.index_aur:
                    self.index_aur.join()

                aur_index = self.aur_client.read_index()

                for pkg in {*installed['not_signed']}:
                    if pkg not in aur_index:
                        if repos_supported:
                            repo_pkgs[pkg] = installed['not_signed'][pkg]

                        if aur_supported and installed['not_signed']:
                            del installed['not_signed'][pkg]

                aur_pkgs = installed['not_signed']
            elif repos_supported:
                repo_pkgs.update(installed['not_signed'])

        pkgs = []
        if repo_pkgs or aur_pkgs:
            if wait_disk_cache:
                self._wait_for_disk_cache()

            map_threads = []

            if aur_pkgs:
                t = Thread(target=self._fill_aur_pkgs, args=(aur_pkgs, pkgs, disk_loader, internet_available, arch_config, rebuild_check, rebuild_ignored, rebuild_output), daemon=True)
                t.start()
                map_threads.append(t)

            if repo_pkgs:
                t = Thread(target=self._fill_repo_pkgs, args=(repo_pkgs, pkgs, aur_index, disk_loader), daemon=True)
                t.start()
                map_threads.append(t)

            for t in map_threads:
                t.join()

        if pkgs:
            ignored = self._fill_ignored_updates(set())

            if ignored:
                for p in pkgs:
                    if p.name in ignored:
                        p.update_ignored = True

        return SearchResult(pkgs, None, len(pkgs))

    def _downgrade_aur_pkg(self, context: TransactionContext) -> bool:
        if not self.add_package_builder_user(context.handler):
            return False

        if context.commit:
            self.logger.info("Package '{}' current commit {}".format(context.name, context.commit))
        else:
            self.logger.warning("Package '{}' has no commit associated with it. Downgrading will only compare versions.".format(context.name))

        context.build_dir = f'{get_build_dir(context.config, self.pkgbuilder_user)}/build_{int(time.time())}'

        try:
            if not os.path.exists(context.build_dir):
                build_dir, build_dir_error = sshell.mkdir(dir_path=context.build_dir, custom_user=self.pkgbuilder_user)

                if not build_dir:
                    context.watcher.print(build_dir_error)
                else:
                    context.handler.watcher.change_progress(10)
                    base_name = context.get_base_name()
                    context.watcher.change_substatus(self.i18n['arch.clone'].format(bold(context.name)))
                    clone_dir = f'{context.build_dir}/{base_name}'
                    cloned, _ = context.handler.handle_simple(git.clone(url=URL_GIT.format(base_name),
                                                                        target_dir=clone_dir,
                                                                        custom_user=self.pkgbuilder_user))
                    context.watcher.change_progress(30)

                    if cloned:
                        context.watcher.change_substatus(self.i18n['arch.downgrade.reading_commits'])
                        context.project_dir = clone_dir
                        srcinfo_path = f'{clone_dir}/.SRCINFO'

                        logs = git.list_commits(clone_dir)
                        context.watcher.change_progress(40)

                        if not logs or len(logs) == 1:
                            context.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                                         body=self.i18n['arch.downgrade.impossible'].format(context.name),
                                                         type_=MessageType.ERROR)
                            return False

                        if context.commit:
                            target_commit, target_commit_timestamp = None, None
                            for idx, log in enumerate(logs):
                                if context.commit == log[0] and idx + 1 < len(logs):
                                    target_commit = logs[idx + 1][0]
                                    target_commit_timestamp = logs[idx + 1][1]
                                    break

                            if not target_commit:
                                self.logger.warning("Could not find '{}' target commit to revert to".format(context.name))
                            else:
                                context.watcher.change_substatus(self.i18n['arch.downgrade.version_found'])
                                checkout_proc = new_subprocess(['git', 'checkout', target_commit], cwd=clone_dir, custom_user=self.pkgbuilder_user)
                                if not context.handler.handle(SystemProcess(checkout_proc, check_error_output=False)):
                                    context.watcher.print("Could not rollback to current version's commit")
                                    return False

                                context.watcher.change_substatus(self.i18n['arch.downgrade.install_older'])
                                context.last_modified = target_commit_timestamp
                                context.commit = target_commit
                                return self._build(context)

                        # trying to downgrade by version comparison
                        commit_found, commit_date = None, None
                        srcfields = {'pkgver', 'pkgrel', 'epoch'}

                        for idx in range(1, len(logs)):
                            commit, date = logs[idx][0], logs[idx][1]
                            with open(srcinfo_path) as f:
                                pkgsrc = aur.map_srcinfo(string=f.read(), pkgname=context.name, fields=srcfields)

                            reset_proc = new_subprocess(['git', 'reset', '--hard', commit], cwd=clone_dir, custom_user=self.pkgbuilder_user)
                            if not context.handler.handle(SystemProcess(reset_proc, check_error_output=False)):
                                context.handler.watcher.print('Could not downgrade anymore. Aborting...')
                                return False

                            epoch, version, release = pkgsrc.get('epoch'), pkgsrc.get('pkgver'), pkgsrc.get('pkgrel')

                            if epoch:
                                current_version = '{}:{}-{}'.format(epoch, version, release)
                            else:
                                current_version = '{}-{}'.format(version, release)

                            if commit_found:
                                context.watcher.change_substatus(self.i18n['arch.downgrade.version_found'])
                                checkout_proc = new_subprocess(['git', 'checkout', commit_found], cwd=clone_dir, custom_user=self.pkgbuilder_user)
                                if not context.handler.handle(SystemProcess(checkout_proc, check_error_output=False)):
                                    context.watcher.print("Could not rollback to current version's commit")
                                    return False

                                reset_proc = new_subprocess(['git', 'reset', '--hard', commit_found], cwd=clone_dir, custom_user=self.pkgbuilder_user)
                                if not context.handler.handle(SystemProcess(reset_proc, check_error_output=False)):
                                    context.watcher.print("Could not downgrade to previous commit of '{}'. Aborting...".format(commit_found))
                                    return False

                                break
                            elif current_version == context.get_version():
                                commit_found, commit_date = commit, date

                        context.watcher.change_substatus(self.i18n['arch.downgrade.install_older'])
                        context.last_modified = commit_date
                        context.commit = commit_found
                        return self._build(context)
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

    def downgrade(self, pkg: ArchPackage, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        if not self.check_action_allowed(pkg, watcher):
            return False

        self.aur_client.clean_caches()

        handler = ProcessHandler(watcher)

        if self._is_database_locked(handler, root_password):
            return False

        arch_config = self.configman.get_config()
        aur_supported = pkg.repository == 'aur' or aur.is_supported(arch_config)
        context = TransactionContext(name=pkg.name, base=pkg.get_base_name(), skip_opt_deps=True,
                                     change_progress=True, dependency=False, repository=pkg.repository, pkg=pkg,
                                     arch_config=arch_config, watcher=watcher, handler=handler, root_password=root_password,
                                     installed=set(), removed={},
                                     aur_supported=aur_supported,
                                     commit=pkg.commit)

        self._sync_databases(arch_config=context.config, aur_supported=aur_supported,
                             root_password=root_password, handler=handler)

        watcher.change_progress(5)

        if pkg.repository == 'aur':
            return self._downgrade_aur_pkg(context)
        else:
            return self._downgrade_repo_pkg(context)

    def clean_cache_for(self, pkg: ArchPackage):
        if os.path.exists(pkg.get_disk_cache_path()):
            shutil.rmtree(pkg.get_disk_cache_path())

    def _is_database_locked(self, handler: ProcessHandler, root_password: Optional[str]) -> bool:
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

    def list_related(self, pkgs: Collection[str], all_pkgs: Collection[str], data: Dict[str, dict], related: Set[str], provided_map: Dict[str, Set[str]]) -> Set[str]:
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

    def _upgrade_repo_pkgs(self, to_upgrade: List[str], to_remove: Optional[Set[str]], handler: ProcessHandler, root_password: Optional[str],
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

    def _remove_transaction_packages(self, to_remove: Set[str], handler: ProcessHandler, root_password: Optional[str]) -> bool:
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
            self.logger.error("An error occurred while removing packages: {}".format(', '.join(to_remove)))
            traceback.print_exc()
            output_handler.stop_working()
            output_handler.join()
            return False

    def _show_upgrade_download_failed(self, watcher: ProcessWatcher):
        watcher.show_message(title=self.i18n['error'].capitalize(),
                             body=self.i18n['arch.upgrade.mthreaddownload.fail'],
                             type_=MessageType.ERROR)

    def upgrade(self, requirements: UpgradeRequirements, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
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

        arch_config = self.configman.get_config()
        aur_supported = bool(aur_pkgs) or aur.is_supported(arch_config)

        self._sync_databases(arch_config=arch_config, aur_supported=aur_supported,
                             root_password=root_password, handler=handler)

        if repo_pkgs and self.check_action_allowed(repo_pkgs[0], watcher):
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

        if aur_pkgs and self.check_action_allowed(aur_pkgs[0], watcher) and self.add_package_builder_user(handler):
            watcher.change_status('{}...'.format(self.i18n['arch.upgrade.upgrade_aur_pkgs']))

            self.logger.info("Retrieving the 'last_modified' field for each package to upgrade")
            pkgs_api_data = self.aur_client.get_info({p.name for p in aur_pkgs})

            if not pkgs_api_data:
                self.logger.warning("Could not retrieve the 'last_modified' fields from the AUR API during the upgrade process")

            any_upgraded = False
            for pkg in aur_pkgs:
                watcher.change_substatus("{} {} ({})...".format(self.i18n['manage_window.status.upgrading'], pkg.name, pkg.version))

                if pkgs_api_data:
                    apidata = [p for p in pkgs_api_data if p.get('Name') == pkg.name]

                    if not apidata:
                        self.logger.warning("AUR API data from package '{}' could not be found".format(pkg.name))
                    else:
                        self.aur_mapper.fill_last_modified(pkg=pkg, api_data=apidata[0])

                context = TransactionContext.gen_context_from(pkg=pkg, arch_config=arch_config,
                                                              root_password=root_password, handler=handler, aur_supported=True)
                context.change_progress = False

                try:
                    if not self.install(pkg=pkg, root_password=root_password, watcher=watcher, disk_loader=None, context=context).success:
                        if any_upgraded:
                            self._update_aur_index(watcher)

                        watcher.print(self.i18n['arch.upgrade.fail'].format('"{}"'.format(pkg.name)))
                        self.logger.error("Could not upgrade AUR package '{}'".format(pkg.name))
                        watcher.change_substatus('')
                        return False
                    else:
                        any_upgraded = True
                        watcher.print(self.i18n['arch.upgrade.success'].format('"{}"'.format(pkg.name)))
                except:
                    if any_upgraded:
                        self._update_aur_index(watcher)

                    watcher.print(self.i18n['arch.upgrade.fail'].format('"{}"'.format(pkg.name)))
                    watcher.change_substatus('')
                    self.logger.error("An error occurred when upgrading AUR package '{}'".format(pkg.name))
                    traceback.print_exc()
                    return False

            if any_upgraded:
                self._update_aur_index(watcher)

        watcher.change_substatus('')
        return True

    def _uninstall_pkgs(self, pkgs: Collection[str], root_password: Optional[str],
                        handler: ProcessHandler, ignore_dependencies: bool = False,
                        replacers: Optional[Set[str]] = None) -> bool:

        status_handler = TransactionStatusHandler(watcher=handler.watcher,
                                                  i18n=self.i18n,
                                                  names={*pkgs},
                                                  logger=self.logger,
                                                  pkgs_to_remove=len(pkgs))

        cmd = ['pacman', '-R', *pkgs, '--noconfirm']

        if ignore_dependencies:
            cmd.append('-dd')

        if replacers:
            cmd.extend(f'--assume-installed={r}' for r in replacers)

        status_handler.start()
        all_uninstalled, _ = handler.handle_simple(SimpleProcess(cmd=cmd,
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

    def _confirm_removal(self, to_remove: Collection[str], required: Collection[str],
                         watcher: ProcessWatcher, data: Optional[Dict[str, Dict[str, str]]] = None) -> bool:

        required_data = data if data is not None else self._map_installed_data_for_removal(required)
        reqs = self._map_as_input_options(required, required_data, read_only=True)
        reqs_select = MultipleSelectComponent(options=reqs, default_options=set(reqs), label="")

        main_msg = self.i18n['arch.uninstall.required_by'].format(no=bold(str(len(required))),
                                                                  pkgs=', '.join(bold(n) for n in to_remove)) + '.'

        full_msg = f"<p>{main_msg}</p><p>{self.i18n['arch.uninstall.required_by.warn'] + '.'}</p>"

        if not watcher.request_confirmation(title=self.i18n['warning'].capitalize(),
                                            body=full_msg,
                                            components=[reqs_select],
                                            confirmation_label=self.i18n['proceed'].capitalize(),
                                            deny_label=self.i18n['cancel'].capitalize(),
                                            min_width=600,
                                            window_cancel=False):
            watcher.print("Aborted")
            return False

        return True

    def _map_as_input_options(self, names: Iterable[str], data: Optional[Dict[str, Dict[str, str]]],
                              read_only: bool = False) -> List[InputOption]:
        opts = []
        for p in names:
            pkgdata = data and data.get(p)
            pkgver, pkgdesc, pkgrepo = None, None, None

            if pkgdata:
                pkgver, pkgdesc, pkgrepo = (pkgdata.get(k) for k in ('version', 'description', 'repository'))

            opts.append(InputOption(label=f"{p}{f' ({pkgver})' if pkgver else ''}", value=p, read_only=read_only,
                                    icon_path=get_repo_icon_path() if pkgrepo == 'repo' else get_icon_path(),
                                    tooltip=pkgdesc))

        return opts

    def _confirm_unneeded_removal(self, unnecessary: Iterable[str], watcher: ProcessWatcher,
                                  data: Optional[Dict[str, Dict[str, str]]] = None) -> Optional[Set[str]]:
        unneeded_data = data if data is not None else self._map_installed_data_for_removal(unnecessary)
        reqs = self._map_as_input_options(unnecessary, unneeded_data)
        reqs_select = MultipleSelectComponent(options=reqs, default_options=set(reqs), label="")

        if not watcher.request_confirmation(title=self.i18n['arch.uninstall.unnecessary.l1'],
                                            body=f"<p>{self.i18n['arch.uninstall.unnecessary.l2'] + ':'}</p>",
                                            components=[reqs_select],
                                            deny_label=self.i18n['arch.uninstall.unnecessary.proceed'].capitalize(),
                                            confirmation_label=self.i18n['arch.uninstall.unnecessary.cancel'].capitalize(),
                                            window_cancel=False,
                                            min_width=500):
            return {*reqs_select.get_selected_values()}

    def _confirm_all_unneeded_removal(self, pkgs: Collection[str], context: TransactionContext,
                                      data: Optional[Dict[str, Dict[str, str]]] = None) -> bool:
        unnecessary_data = data if data is not None else self._map_installed_data_for_removal(pkgs)
        reqs = self._map_as_input_options(pkgs, unnecessary_data, read_only=True)
        reqs_select = MultipleSelectComponent(options=reqs, default_options=set(reqs), label="")

        if not context.watcher.request_confirmation(title=self.i18n['confirmation'].capitalize(),
                                                    body=self.i18n['arch.uninstall.unnecessary.all'].format(bold(str(len(pkgs)))),
                                                    components=[reqs_select],
                                                    confirmation_label=self.i18n['proceed'].capitalize(),
                                                    deny_label=self.i18n['cancel'].capitalize(),
                                                    window_cancel=False,
                                                    min_width=500):
            context.watcher.print("Aborted")
            return False

        return True

    def _fill_aur_providers(self, names: str,  output: Set[str]):
        for _, data in self.aur_client.gen_updates_data(names):
            providers = data.get('p')

            if providers:
                output.update(providers)

    def _map_actual_replacers(self, names: Set[str], context: TransactionContext) -> Optional[Set[str]]:
        if not names:
            return

        repo_replacers, aur_replacers = set(), set()

        for r in names:
            repo = context.remote_repo_map.get(r)

            if repo and repo != 'aur':
                repo_replacers.add(r)
            elif repo == 'aur' or (context.aur_idx and r in context.aur_idx):
                aur_replacers.add(r)

        actual_replacers = set()

        thread_fill_aur = None
        if aur_replacers:
            thread_fill_aur = Thread(target=self._fill_aur_providers, args=(aur_replacers, actual_replacers))
            thread_fill_aur.start()

        if repo_replacers:
            repo_replace_providers = pacman.map_provided(remote=True, pkgs=repo_replacers)

            if repo_replace_providers:
                actual_replacers.update(repo_replace_providers)

        if thread_fill_aur:
            thread_fill_aur.join()

        return actual_replacers

    def _uninstall(self, context: TransactionContext, names: Set[str], remove_unneeded: bool = False,
                   disk_loader: Optional[DiskCacheLoader] = None, skip_requirements: bool = False,
                   replacers: Optional[Set[str]] = None):

        self._update_progress(context, 10)

        actual_replacers = self._map_actual_replacers(replacers, context) if replacers else None

        net_available = self.context.internet_checker.is_available() if disk_loader else True

        hard_requirements = set()

        if not skip_requirements:
            for n in names:
                try:
                    pkg_reqs = pacman.list_hard_requirements(name=n, logger=self.logger, assume_installed=actual_replacers)

                    if pkg_reqs:
                        hard_requirements.update(pkg_reqs)

                except PackageInHoldException:
                    error_msg = self.i18n['arch.uninstall.error.hard_dep_in_hold'].format(bold(n))
                    context.watcher.show_message(title=self.i18n['error'].capitalize(), body=error_msg,
                                                 type_=MessageType.ERROR)
                    return False

        self._update_progress(context, 25)

        to_uninstall = set()
        to_uninstall.update(names)

        if hard_requirements:
            to_uninstall.update(hard_requirements)

            if not self._confirm_removal(to_remove=names, required=hard_requirements, watcher=context.watcher):
                return False

        if not skip_requirements and remove_unneeded:
            unnecessary_packages = pacman.list_post_uninstall_unneeded_packages(to_uninstall)
            self.logger.info("Checking unnecessary optdeps")

            if context.config['suggest_optdep_uninstall']:
                unnecessary_packages.update(self._list_opt_deps_with_no_hard_requirements(source_pkgs=to_uninstall))

            self.logger.info("Packages no longer needed found: {}".format(len(unnecessary_packages)))
        else:
            unnecessary_packages = None

        self._update_progress(context, 50)

        if disk_loader and to_uninstall:  # loading package instances in case the removal succeeds
            instances = self.read_installed(disk_loader=disk_loader,
                                            names={n for n in to_uninstall},
                                            internet_available=net_available).installed

            if len(instances) != len(to_uninstall):
                self.logger.warning("Not all packages to be uninstalled could be read")
        else:
            instances = None

        provided_by_uninstalled = pacman.map_provided(pkgs=to_uninstall)

        uninstalled = self._uninstall_pkgs(to_uninstall, context.root_password, context.handler,
                                           ignore_dependencies=skip_requirements, replacers=actual_replacers)

        if uninstalled:
            self._remove_uninstalled_from_context(provided_by_uninstalled, context)

            if disk_loader:  # loading package instances in case the removal succeeds
                if instances:
                    for p in instances:
                        context.removed[p.name] = p

            self._update_progress(context, 70)

            if unnecessary_packages:
                unnecessary_to_uninstall = self._confirm_unneeded_removal(unnecessary=unnecessary_packages,
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

                    if not unnecessary_requirements or self._confirm_all_unneeded_removal(all_unnecessary_to_uninstall,
                                                                                          context):
                        if disk_loader:  # loading package instances in case the uninstall succeeds
                            unnecessary_instances = self.read_installed(disk_loader=disk_loader,
                                                                        internet_available=net_available,
                                                                        names=all_unnecessary_to_uninstall).installed
                        else:
                            unnecessary_instances = None

                        unneded_uninstalled = self._uninstall_pkgs(all_unnecessary_to_uninstall, context.root_password,
                                                                   context.handler, replacers=actual_replacers)

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

    def _map_installed_data_for_removal(self, names: Iterable[str]) -> Optional[Dict[str, Dict[str, str]]]:
        data = pacman.map_packages(names)

        if data:
            remapped_data = {}
            for key, pkgs in data.items():
                repository = 'aur' if key == 'not_signed' else 'repo'
                for name, data in pkgs.items():
                    remapped_data[name] = {**data, 'repository': repository}

            return remapped_data

    def _remove_uninstalled_from_context(self, provided_by_uninstalled: Dict[str, Set[str]], context: TransactionContext):
        if context.provided_map and provided_by_uninstalled:  # updating the current provided context
            for name, provided in provided_by_uninstalled.items():
                if name in context.provided_map:
                    del context.provided_map[name]

                if provided:
                    for exp in provided:
                        exp_provided = context.provided_map.get(exp)

                        if exp_provided and name in exp_provided:
                            exp_provided.remove(name)

                            if not exp_provided:
                                del context.provided_map[exp]

    def uninstall(self, pkg: ArchPackage, root_password: Optional[str], watcher: ProcessWatcher, disk_loader: DiskCacheLoader) -> TransactionResult:
        self.aur_client.clean_caches()

        handler = ProcessHandler(watcher)

        if self._is_database_locked(handler, root_password):
            return TransactionResult.fail()

        removed = {}
        arch_config = self.configman.get_config()
        success = self._uninstall(TransactionContext(change_progress=True,
                                                     arch_config=arch_config,
                                                     watcher=watcher,
                                                     root_password=root_password,
                                                     handler=handler,
                                                     removed=removed,
                                                     aur_supported=pkg.repository == 'aur' or aur.is_supported(arch_config)),
                                  remove_unneeded=arch_config['suggest_unneeded_uninstall'],
                                  names={pkg.name},
                                  disk_loader=disk_loader)  # to be able to return all uninstalled packages
        if success:
            removed_list = []

            main_removed = removed.get(pkg.name)
            if main_removed:
                pkg.installed = False
                pkg.url_download = main_removed.url_download  # otherwise uninstalled AUR packages cannot be reinstalled on the same view
                removed_list.append(pkg)

            removed_list.extend((inst for name, inst in removed.items() if name != pkg.name))
            return TransactionResult(success=not pkg.installed, installed=None, removed=removed_list)
        else:
            return TransactionResult.fail()

    def get_managed_types(self) -> Set["type"]:
        return {ArchPackage}

    def _get_info_aur_pkg(self, pkg: ArchPackage) -> dict:
        fill_pkgbuild = Thread(target=self.aur_mapper.fill_package_build, args=(pkg,), daemon=True)
        fill_pkgbuild.start()

        if pkg.installed:
            info = pacman.get_info_dict(pkg.name)

            if info is not None:
                self._parse_dates_string_from_info(pkg.name, info)

                info['04_orphan'] = pkg.orphan
                info['04_out_of_date'] = pkg.out_of_date

                if pkg.commit:
                    info['commit'] = pkg.commit

                if pkg.last_modified:
                    info['last_modified'] = self._parse_timestamp(ts=pkg.last_modified,
                                                                  error_msg="Could not parse AUR package '{}' 'last_modified' field ({})".format(pkg.name, pkg.last_modified))

                info['14_installed_files'] = pacman.list_installed_files(pkg.name)

                fill_pkgbuild.join()

                if pkg.pkgbuild:
                    info['13_pkg_build'] = pkg.pkgbuild

            return info
        else:
            info = {
                '01_id': pkg.id,
                '02_name': pkg.name,
                '03_description': pkg.description,
                '03_version': pkg.version,
                '04_orphan': pkg.orphan,
                '04_out_of_date': pkg.out_of_date,
                '04_popularity': pkg.popularity,
                '05_votes': pkg.votes,
                '06_package_base': pkg.package_base,
                '07_maintainer': pkg.maintainer,
                '10_url': pkg.url_download
            }

            if pkg.first_submitted:
                info['08_first_submitted'] = self._parse_timestamp(ts=pkg.first_submitted,
                                                                   error_msg="Could not parse AUR package '{}' 'first_submitted' field".format(pkg.name, pkg.first_submitted))

            if pkg.last_modified:
                info['09_last_modified'] = self._parse_timestamp(ts=pkg.last_modified,
                                                                 error_msg="Could not parse AUR package '{}' 'last_modified' field ({})".format(pkg.name, pkg.last_modified))

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

            fill_pkgbuild.join()

            if pkg.pkgbuild:
                info['00_pkg_build'] = pkg.pkgbuild
            else:
                info['11_pkg_build_url'] = pkg.get_pkg_build_url()

            return info

    def _parse_dates_string_from_info(self, pkgname: str, info: dict):
        for date_attr in ('install date', 'build date'):
            en_date_str = info.get(date_attr)

            if en_date_str:
                try:
                    info[date_attr] = parse_date(en_date_str)
                except ValueError:
                    self.logger.error("Could not parse date attribute '{}' ({}) from package '{}'".format(date_attr, en_date_str, pkgname))

    def _parse_timestamp(self, ts: int, error_msg: str) -> datetime:
        if ts:
            try:
                return datetime.fromtimestamp(ts)
            except ValueError:
                if error_msg:
                    self.logger.error(error_msg)

    def _get_info_repo_pkg(self, pkg: ArchPackage) -> dict:
        info = pacman.get_info_dict(pkg.name, remote=not pkg.installed)

        if info is not None:
            self._parse_dates_string_from_info(pkg.name, info)

            if pkg.installed:
                info['installed files'] = pacman.list_installed_files(pkg.name)

        for attr in ('version', 'description'):
            val = info.get(attr)

            if val is not None:
                info[f'03_{attr}'] = val
                del info[attr]

        return info

    def get_info(self, pkg: ArchPackage) -> dict:
        if pkg.repository == 'aur':
            info = self._get_info_aur_pkg(pkg)
        else:
            info = self._get_info_repo_pkg(pkg)

        if pkg.is_application():
            info['04_exec'] = pkg.command

        return info

    def _get_history_aur_pkg(self, pkg: ArchPackage) -> PackageHistory:

        if pkg.commit:
            self.logger.info("Package '{}' current commit {}".format(pkg.name, pkg.commit))
        else:
            self.logger.warning("Package '{}' has no commit associated with it. Current history status may not be correct.".format(pkg.name))

        arch_config = self.configman.get_config()
        temp_dir = f'{get_build_dir(arch_config, self.pkgbuilder_user)}/build_{int(time.time())}'

        try:
            Path(temp_dir).mkdir(parents=True)
            base_name = pkg.get_base_name()
            run_cmd('git clone ' + URL_GIT.format(base_name), print_error=False, cwd=temp_dir)

            clone_dir = f'{temp_dir}/{base_name}'

            srcinfo_path = f'{clone_dir}/.SRCINFO'

            if not os.path.exists(srcinfo_path):
                return PackageHistory.empyt(pkg)

            logs = git.list_commits(clone_dir)

            if logs:
                srcfields = {'epoch', 'pkgver', 'pkgrel'}
                history, status_idx = [], -1

                for idx, log in enumerate(logs):
                    commit, timestamp = log[0], log[1]

                    with open(srcinfo_path) as f:
                        pkgsrc = aur.map_srcinfo(string=f.read(), pkgname=pkg.name, fields=srcfields)

                    epoch, version, release = pkgsrc.get('epoch'), pkgsrc.get('pkgver'), pkgsrc.get('pkgrel')

                    pkgver = '{}:{}'.format(epoch, version) if epoch is not None else version
                    current_version = '{}-{}'.format(pkgver, release)

                    if status_idx < 0:
                        if pkg.commit:
                            status_idx = idx if pkg.commit == commit else -1
                        else:
                            status_idx = idx if current_version == pkg.version else -1

                    history.append({'1_version': pkgver, '2_release': release,
                                    '3_date': datetime.fromtimestamp(timestamp)})  # the number prefix is to ensure the rendering order

                    if idx + 1 < len(logs):
                        if not run_cmd('git reset --hard ' + logs[idx + 1][0], cwd=clone_dir):
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
        extract_path = f'{TEMP_DIR}/arch/history'

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

    def _request_conflict_resolution(self, pkg: str, conflicting_pkg: str, context: TransactionContext,
                                     skip_requirements: bool = False) -> bool:

        conflict_msg = f"{bold(pkg)} {self.i18n['and']} {bold(conflicting_pkg)}"
        msg_body = self.i18n['arch.install.conflict.popup.body'].format(conflict_msg)

        if not context.watcher.request_confirmation(title=self.i18n['arch.install.conflict.popup.title'], body=msg_body):
            context.watcher.print(self.i18n['action.cancelled'])
            return False
        else:
            context.watcher.change_substatus(self.i18n['arch.uninstalling.conflict'].format(bold(conflicting_pkg)))
            context.disable_progress_if_changing()

            if context.removed is None:
                context.removed = {}

            res = self._uninstall(context=context, names={conflicting_pkg}, disk_loader=context.disk_loader,
                                  remove_unneeded=False, skip_requirements=skip_requirements, replacers={pkg})

            context.restabilish_progress()
            return res

    def _install_deps(self, context: TransactionContext, deps: List[Tuple[str, str]]) -> Optional[Iterable[str]]:
        progress_increment = int(100 / len(deps))
        progress = 0
        self._update_progress(context, 1)

        repo_deps, repo_dep_names, aur_deps_context = [], None, []

        for dep in deps:
            context.watcher.change_substatus(self.i18n['arch.install.dependency.install'].format(bold('{} ({})'.format(dep[0], dep[1]))))

            if dep[1] == 'aur':
                dep_context = context.gen_dep_context(dep[0], dep[1])
                dep_src = self.aur_client.get_src_info(dep[0])
                dep_context.base = dep_src['pkgbase'] if dep_src['pkgbase'] else dep[0]
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

            for dep, data in pacman.map_conflicts_with(repo_dep_names, remote=True).items():
                if data and data['c']:
                    for c in data['c']:
                        source_conflict = all_provided.get(c)

                        if source_conflict:
                            conflict_pkg = [*source_conflict][0]

                            if dep != conflict_pkg:
                                if not self._request_conflict_resolution(dep, conflict_pkg, context,
                                                                         skip_requirements=data['r'] and conflict_pkg in data['r']):
                                    return {dep}

            downloaded = 0
            if self._multithreaded_download_enabled(context.config):
                try:
                    pkg_sizes = pacman.map_download_sizes(repo_dep_names)
                    downloaded = self._download_packages(repo_dep_names, context.handler, context.root_password, pkg_sizes, multithreaded=True)
                except ArchDownloadException:
                    return None

            status_handler = TransactionStatusHandler(watcher=context.watcher, i18n=self.i18n, names={*repo_dep_names},
                                                      logger=self.logger, percentage=len(repo_deps) > 1, downloading=downloaded)
            status_handler.start()
            installed, _ = context.handler.handle_simple(pacman.install_as_process(pkgpaths=repo_dep_names,
                                                                                   root_password=context.root_password,
                                                                                   file=False,
                                                                                   as_deps=True),
                                                         output_handler=status_handler.handle)

            if installed:
                pkg_map = {d[0]: ArchPackage(name=d[0], repository=d[1], maintainer=d[1],
                                             categories=self.categories.get(d[0])) for d in repo_deps}
                disk.write_several(pkg_map, overwrite=True, maintainer=None)
                progress += len(repo_deps) * progress_increment
                self._update_progress(context, progress)
            else:
                return repo_dep_names

        if aur_deps_context:
            aur_deps_info = self.aur_client.get_info((c.base for c in aur_deps_context))
            aur_deps_data = None

            if aur_deps_info:
                aur_deps_data = {data['Name']: data for data in aur_deps_info}

            for aur_context in aur_deps_context:
                if aur_deps_data:
                    dep_data = aur_deps_data.get(aur_context.base)

                    if dep_data:
                        last_modified = dep_data.get('LastModified')

                        if last_modified and isinstance(last_modified, int):
                            aur_context.last_modified = last_modified
                        else:
                            self.logger.warning(f"No valid 'LastModified' field returned for AUR package "
                                                f"'{context.name}': {last_modified}")

                installed = self._install_from_aur(aur_context)

                if not installed:
                    return {aur_context.name}
                else:
                    progress += progress_increment
                    self._update_progress(context, progress)

        self._update_progress(context, 100)

    def _map_repos(self, pkgnames: Collection[str]) -> dict:
        pkg_repos = pacman.get_repositories(pkgnames)  # getting repositories set

        if len(pkgnames) != len(pkg_repos):  # checking if any dep not found in the distro repos are from AUR
            norepos = {p for p in pkgnames if p not in pkg_repos}

            aur_info = self.aur_client.get_info(norepos)

            if aur_info:
                for pkginfo in aur_info:
                    if pkginfo.get('Name') in norepos:
                        pkg_repos[pkginfo['Name']] = 'aur'

        return pkg_repos

    def _pre_download_source(self, pkgname: str, project_dir: str, watcher: ProcessWatcher) -> bool:
        # TODO: multi-threaded download client cannot be run as another user at the moment
        if not self.context.root_user and self.context.file_downloader.is_multithreaded():
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
            if not write_as_user(content=pkgbuild_input.get_value(), file_path=pkgbuild_path, user=self.pkgbuilder_user):
                return False

            return makepkg.update_srcinfo(project_dir='/'.join(pkgbuild_path.split('/')[0:-1]),
                                          custom_user=self.pkgbuilder_user)

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
                                              pkgbuild_path=f'{context.project_dir}/PKGBUILD'):
                context.pkgbuild_edited = True
                srcinfo = aur.map_srcinfo(string=makepkg.gen_srcinfo(build_dir=context.project_dir, custom_user=self.pkgbuilder_user),
                                          pkgname=context.name)

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
        src_path = f'{context.project_dir}/.SRCINFO'

        if not os.path.exists(src_path):
            srcinfo = makepkg.gen_srcinfo(build_dir=context.project_dir,
                                          custom_pkgbuild_path=context.custom_pkgbuild_path,
                                          custom_user=self.pkgbuilder_user)

            write_as_user(content=srcinfo, file_path=src_path, user=self.pkgbuilder_user)
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
        optimize = bool(context.config['optimize']) and cpu_manager.supports_performance_mode()

        cpus_changed, cpu_prev_governors = False, None

        if optimize:
            cpus_changed, cpu_prev_governors = cpu_manager.set_all_cpus_to('performance', context.root_password,
                                                                           self.logger)

        pkgbuilt = False

        try:
            pkgbuilt, output = makepkg.build(pkgdir=context.project_dir,
                                             optimize=optimize,
                                             handler=context.handler,
                                             custom_pkgbuild=context.custom_pkgbuild_path,
                                             custom_user=self.pkgbuilder_user)
        finally:
            if cpus_changed and cpu_prev_governors:
                self.logger.info("Restoring CPU governors")
                cpu_manager.set_cpus(cpu_prev_governors, context.root_password, self.logger, {'performance'})

        self._update_progress(context, 65)

        if pkgbuilt:
            self.__fill_aur_output_files(context)

            self.logger.info(f"Reading '{context.name}' cloned repository current commit")
            commits = git.list_commits(context.project_dir, limit=1)

            if commits:
                context.commit = commits[0][0]

            else:
                self.logger.error(f"Could not read '{context.name}' cloned repository current commit")

            if self._install(context=context):
                self._save_pkgbuild(context)

                if context.update_aur_index:
                    self._update_aur_index(context.watcher)

                if context.dependency or context.skip_opt_deps:
                    return True

                context.watcher.change_substatus(self.i18n['arch.optdeps.checking'].format(bold(context.name)))

                self._update_progress(context, 100)

                if self._install_optdeps(context):
                    return True

        return False

    def _update_aur_index(self, watcher: ProcessWatcher):
        if self.context.internet_checker.is_available():
            if watcher:
                watcher.change_substatus(self.i18n['arch.task.aur.index.status'])

            idx_updater = AURIndexUpdater(context=self.context, taskman=TaskManager())  # null task manager
            idx_updater.update_index()
        else:
            self.logger.warning("Could not update the AUR index: no internet connection detected")

    def __fill_aur_output_files(self, context: TransactionContext):
        self.logger.info("Determining output files of '{}'".format(context.name))
        context.watcher.change_substatus(self.i18n['arch.aur.build.list_output'])

        output_files = {f for f in makepkg.list_output_files(project_dir=context.project_dir,
                                                             custom_pkgbuild_path=context.custom_pkgbuild_path,
                                                             custom_user=self.pkgbuilder_user) if os.path.isfile(f)}

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
                srcinfo = aur.map_srcinfo(string=makepkg.gen_srcinfo(build_dir=context.project_dir, custom_user=self.pkgbuilder_user),
                                          pkgname=context.name)
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

        if not confirm_missing_deps(missing_deps, context.watcher, self.i18n):
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
                                                           prefer_repository_provider=context.config['prefer_repository_provider'],
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
        if not context.dependency:
            handled_deps = self._handle_missing_deps(context)
            if not handled_deps:
                return False

        check_res = makepkg.check(project_dir=context.project_dir,
                                  optimize=bool(context.config['optimize']),
                                  missing_deps=False,
                                  handler=context.handler,
                                  custom_pkgbuild=context.custom_pkgbuild_path,
                                  custom_user=self.pkgbuilder_user)

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
                                                                   prefer_repository_provider=context.config['prefer_repository_provider'],
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

                if display_deps_dialog and not confirm_missing_deps(sorted_deps, context.watcher, self.i18n):
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

    def _download_packages(self, pkgnames: List[str], handler: ProcessHandler, root_password: Optional[str], sizes: Dict[str, int] = None, multithreaded: bool = True) -> int:
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

                    if not self._uninstall(names=to_uninstall, context=context, remove_unneeded=False,
                                           disk_loader=context.disk_loader,
                                           replacers=names_to_install):

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
            to_install.extend((d[0] for d in context.missing_deps if d[1] != 'aur'))

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
        context.watcher.change_substatus(self.i18n['arch.installing.package'].format(bold(context.name))) #

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
                    aur_infos = self.aur_client.get_info((context.name,))
                    pkg_maintainer = aur_infos[0].get('Maintainer') if aur_infos else None
                else:
                    pkg_maintainer = context.repository
            else:
                pkg_maintainer = context.maintainer

            cache_map = {context.name: ArchPackage(name=context.name,
                                                   repository=context.repository,
                                                   maintainer=pkg_maintainer,
                                                   last_modified=context.last_modified,
                                                   commit=context.commit,
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
                                                                       overwrite_conflicting_files=overwrite_files,
                                                                       as_deps=context.dependency),
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

    def _import_pgp_keys(self, pkgname: str, root_password: Optional[str], handler: ProcessHandler):
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
        if not context.dependency and not self.add_package_builder_user(context.handler):
            return False

        self._optimize_makepkg(context.config, context.watcher)

        context.build_dir = f'{get_build_dir(context.config, self.pkgbuilder_user)}/build_{int(time.time())}'

        try:
            if not os.path.exists(context.build_dir):
                build_dir, build_dir_error = sshell.mkdir(dir_path=context.build_dir, custom_user=self.pkgbuilder_user)
                self._update_progress(context, 10)

                if not build_dir:
                    context.watcher.print(build_dir_error)
                else:
                    base_name = context.get_base_name()
                    context.watcher.change_substatus(self.i18n['arch.clone'].format(bold(base_name)))
                    clone_dir = f'{context.build_dir}/{base_name}'
                    cloned = context.handler.handle_simple(git.clone(url=URL_GIT.format(base_name), target_dir=clone_dir,
                                                                     depth=1, custom_user=self.pkgbuilder_user))

                    if cloned:
                        self._update_progress(context, 40)
                        context.project_dir = clone_dir
                        return self._build(context)
        finally:
            if os.path.exists(context.build_dir) and context.config['aur_remove_build_dir']:
                context.handler.handle(SystemProcess(new_subprocess(['rm', '-rf', context.build_dir])))

        return False

    def _sync_databases(self, arch_config: dict, aur_supported: bool, root_password: Optional[str], handler: ProcessHandler, change_substatus: bool = True):
        if bool(arch_config['sync_databases']) and database.should_sync(arch_config, aur_supported, handler, self.logger):
            if change_substatus:
                handler.watcher.change_substatus(self.i18n['arch.sync_databases.substatus'])

            synced, output = handler.handle_simple(pacman.sync_databases(root_password=root_password, force=True))
            if synced:
                database.register_sync(self.logger)
            else:
                self.logger.warning("It was not possible to synchronized the package databases")
                handler.watcher.change_substatus(self.i18n['arch.sync_databases.substatus.error'])

    def _optimize_makepkg(self, arch_config: dict, watcher: Optional[ProcessWatcher]):
        if arch_config['optimize'] and not os.path.exists(CUSTOM_MAKEPKG_FILE):
            watcher.change_substatus(self.i18n['arch.makepkg.optimizing'])
            ArchCompilationOptimizer(i18n=self.i18n, logger=self.context.logger, taskman=TaskManager()).optimize()

    def install(self, pkg: ArchPackage, root_password: Optional[str], disk_loader: Optional[DiskCacheLoader], watcher: ProcessWatcher, context: TransactionContext = None) -> TransactionResult:
        if not self.check_action_allowed(pkg, watcher):
            return TransactionResult.fail()

        self.aur_client.clean_caches()

        handler = ProcessHandler(watcher) if not context else context.handler

        if self._is_database_locked(handler, root_password):
            return TransactionResult(success=False, installed=[], removed=[])

        if context:
            install_context = context
        else:
            install_context = TransactionContext.gen_context_from(pkg=pkg, handler=handler, arch_config=self.configman.get_config(),
                                                                  root_password=root_password)
            install_context.skip_opt_deps = False
            install_context.disk_loader = disk_loader
            install_context.update_aur_index = pkg.repository == 'aur'

        self._sync_databases(arch_config=install_context.config, aur_supported=install_context.aur_supported,
                             root_password=root_password, handler=handler)

        if pkg.repository == 'aur':
            pkg_installed = self._install_from_aur(install_context)
        else:
            pkg_installed = self._install_from_repository(install_context)

        if pkg_installed:
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

        if pkg_installed and disk_loader and install_context.installed:
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
        return TransactionResult(success=pkg_installed, installed=installed, removed=removed)

    def _install_from_repository(self, context: TransactionContext) -> bool:
        if not self._handle_missing_deps(context):
            return False

        res = self._install(context)

        if res and not context.skip_opt_deps:
            self._update_progress(context, 100)
            return self._install_optdeps(context)

        return res

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> Tuple[bool, Optional[str]]:
        if not self.arch_distro:
            return False, self.i18n['arch.can_work.not_arch_distro']

        if not pacman.is_available():
            return False, self.i18n['missing_dep'].format(dep=bold('pacman'))

        return True, None

    def cache_to_disk(self, pkg: ArchPackage, icon_bytes: bytes, only_icon: bool):
        pass

    def requires_root(self, action: SoftwareAction, pkg: ArchPackage) -> bool:
        if action == SoftwareAction.PREPARE:
            arch_config = self.configman.get_config()
            aur_supported = (pkg and pkg.repository == 'aur') or aur.is_supported(arch_config)

            if RefreshMirrors.should_synchronize(arch_config, aur_supported, self.logger):
                return True

            return SyncDatabases.should_sync(mirrors_refreshed=False, arch_config=arch_config,
                                             aur_supported=aur_supported, logger=self.logger)

        return action != SoftwareAction.SEARCH

    def _start_category_task(self, taskman: TaskManager, create_config: CreateConfigFile, downloader: CategoriesDownloader):
        taskman.update_progress('arch_aur_cats', 0, self.i18n['task.waiting_task'].format(bold(create_config.task_name)))
        create_config.join()
        arch_config = create_config.config

        downloader.expiration = arch_config['categories_exp'] if isinstance(arch_config['categories_exp'], int) else None
        taskman.update_progress('arch_aur_cats', 50, None)

    def _finish_category_task(self, taskman: TaskManager):
        taskman.update_progress('arch_aur_cats', 100, None)
        taskman.finish_task('arch_aur_cats')

    def prepare(self, task_manager: TaskManager, root_password: Optional[str], internet_available: bool):
        create_config = CreateConfigFile(taskman=task_manager, configman=self.configman, i18n=self.i18n,
                                         task_icon_path=get_icon_path(), logger=self.logger)
        create_config.start()

        if internet_available:
            self.index_aur = AURIndexUpdater(context=self.context, taskman=task_manager, create_config=create_config)  # must always execute to properly determine the installed packages (even that AUR is disabled)
            self.index_aur.start()

            if not self.suggestions_downloader.is_custom_local_file_mapped():
                self.suggestions_downloader.create_config = create_config
                self.suggestions_downloader.register_task(task_manager)
                self.suggestions_downloader.start()

            refresh_mirrors = RefreshMirrors(taskman=task_manager, i18n=self.i18n, root_password=root_password,
                                             logger=self.logger, create_config=create_config)
            refresh_mirrors.start()

            SyncDatabases(taskman=task_manager, root_password=root_password, i18n=self.i18n,
                          logger=self.logger, refresh_mirrors=refresh_mirrors, create_config=create_config).start()

        ArchCompilationOptimizer(i18n=self.i18n, logger=self.context.logger,
                                 taskman=task_manager, create_config=create_config).start()

        self.disk_cache_updater = ArchDiskCacheUpdater(taskman=task_manager,
                                                       i18n=self.i18n,
                                                       logger=self.context.logger,
                                                       controller=self,
                                                       internet_available=internet_available,
                                                       aur_indexer=self.index_aur,
                                                       create_config=create_config)
        self.disk_cache_updater.start()

        task_manager.register_task('arch_aur_cats', self.i18n['task.download_categories'], get_icon_path())
        cat_download = CategoriesDownloader(id_='Arch', http_client=self.context.http_client,
                                            logger=self.context.logger,
                                            manager=self, url_categories_file=URL_CATEGORIES_FILE,
                                            categories_path=CATEGORIES_FILE_PATH,
                                            internet_connection=internet_available,
                                            internet_checker=self.context.internet_checker,
                                            after=lambda: self._finish_category_task(task_manager))
        cat_download.before = lambda: self._start_category_task(taskman=task_manager, create_config=create_config,
                                                                downloader=cat_download)
        cat_download.start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        installed = self.read_installed(disk_loader=None, internet_available=internet_available).installed

        aur_type, repo_type = self.i18n['gem.arch.type.aur.label'], self.i18n['gem.arch.type.arch_repo.label']

        return [PackageUpdate(p.name, p.latest_version, aur_type if p.repository == 'aur' else repo_type, p.name) for p in installed if p.update and not p.is_update_ignored()]

    def list_warnings(self, internet_available: bool) -> Optional[List[str]]:
        if not git.is_installed():
            return [self.i18n['arch.warning.aur_missing_dep'].format(bold('git'))]

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: ArchPackage):
        if pkg.command:
            final_cmd = pkg.command.replace('%U', '')
            subprocess.Popen(final_cmd, shell=True)

    def _gen_bool_selector(self, id_: str, label_key: str, tooltip_key: str, value: bool,
                           max_width: Optional[int] = None, capitalize_label: bool = True,
                           label_params: Optional[list] = None, tooltip_params: Optional[list] = None) \
            -> SingleSelectComponent:

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

    def _get_general_settings(self, arch_config: dict) -> SettingsView:
        db_sync_start = self._gen_bool_selector(id_='sync_dbs_start',
                                                label_key='arch.config.sync_dbs',
                                                tooltip_key='arch.config.sync_dbs_start.tip',
                                                value=bool(arch_config['sync_databases_startup']))

        db_sync_start.label += f" ({self.i18n['initialization'].capitalize()})"

        fields = [
            self._gen_bool_selector(id_='repos',
                                    label_key='arch.config.repos',
                                    tooltip_key='arch.config.repos.tip',
                                    value=bool(arch_config['repositories'])),
            self._gen_bool_selector(id_='autoprovs',
                                    label_key='arch.config.automatch_providers',
                                    tooltip_key='arch.config.automatch_providers.tip',
                                    value=bool(arch_config['automatch_providers'])),
            self._gen_bool_selector(id_='prefer_repo_provider',
                                    label_key='arch.config.prefer_repository_provider',
                                    tooltip_key='arch.config.prefer_repository_provider.tip',
                                    value=bool(arch_config['prefer_repository_provider']),
                                    tooltip_params=['AUR']),
            self._gen_bool_selector(id_='check_dependency_breakage',
                                    label_key='arch.config.check_dependency_breakage',
                                    tooltip_key='arch.config.check_dependency_breakage.tip',
                                    value=bool(arch_config['check_dependency_breakage'])),
            self._gen_bool_selector(id_='mthread_download',
                                    label_key='arch.config.pacman_mthread_download',
                                    tooltip_key='arch.config.pacman_mthread_download.tip',
                                    value=arch_config['repositories_mthread_download'],
                                    capitalize_label=True),
            self._gen_bool_selector(id_='sync_dbs',
                                    label_key='arch.config.sync_dbs',
                                    tooltip_key='arch.config.sync_dbs.tip',
                                    value=bool(arch_config['sync_databases'])),
            db_sync_start,
            self._gen_bool_selector(id_='clean_cached',
                                    label_key='arch.config.clean_cache',
                                    tooltip_key='arch.config.clean_cache.tip',
                                    value=bool(arch_config['clean_cached'])),
            self._gen_bool_selector(id_='suggest_unneeded_uninstall',
                                    label_key='arch.config.suggest_unneeded_uninstall',
                                    tooltip_params=['"{}"'.format(self.i18n['arch.config.suggest_optdep_uninstall'])],
                                    tooltip_key='arch.config.suggest_unneeded_uninstall.tip',
                                    value=bool(arch_config['suggest_unneeded_uninstall'])),
            self._gen_bool_selector(id_='suggest_optdep_uninstall',
                                    label_key='arch.config.suggest_optdep_uninstall',
                                    tooltip_key='arch.config.suggest_optdep_uninstall.tip',
                                    value=bool(arch_config['suggest_optdep_uninstall'])),
            self._gen_bool_selector(id_='ref_mirs',
                                    label_key='arch.config.refresh_mirrors',
                                    tooltip_key='arch.config.refresh_mirrors.tip',
                                    value=bool(arch_config['refresh_mirrors_startup'])),
            TextInputComponent(id_='mirrors_sort_limit',
                               label=self.i18n['arch.config.mirrors_sort_limit'],
                               tooltip=self.i18n['arch.config.mirrors_sort_limit.tip'],
                               only_int=True,
                               value=arch_config['mirrors_sort_limit'] if isinstance(arch_config['mirrors_sort_limit'], int) else ''),
            TextInputComponent(id_='arch_cats_exp',
                               label=self.i18n['arch.config.categories_exp'],
                               tooltip=self.i18n['arch.config.categories_exp.tip'],
                               only_int=True,
                               capitalize_label=False,
                               value=arch_config['categories_exp'] if isinstance(arch_config['categories_exp'], int) else ''),
            TextInputComponent(id_='arch_sugs_exp',
                               label=self.i18n['arch.config.suggestions_exp'],
                               tooltip=self.i18n['arch.config.suggestions_exp.tip'],
                               only_int=True,
                               capitalize_label=False,
                               value=arch_config['suggestions_exp'] if isinstance(arch_config['suggestions_exp'], int) else '')
        ]

        return SettingsView(self, PanelComponent([FormComponent(fields, spaces=False)], id_="repo"), icon_path=get_repo_icon_path())

    def _get_aur_settings(self, arch_config: dict) -> SettingsView:
        fields = [
            self._gen_bool_selector(id_='aur',
                                    label_key='arch.config.aur',
                                    tooltip_key='arch.config.aur.tip',
                                    value=arch_config['aur'],
                                    capitalize_label=False),
            self._gen_bool_selector(id_='opts',
                                    label_key='arch.config.optimize',
                                    tooltip_key='arch.config.optimize.tip',
                                    value=bool(arch_config['optimize']),
                                    capitalize_label=False),
            self._gen_bool_selector(id_='rebuild_detector',
                                    label_key='arch.config.aur_rebuild_detector',
                                    tooltip_key='arch.config.aur_rebuild_detector.tip',
                                    value=bool(arch_config['aur_rebuild_detector']),
                                    tooltip_params=["'rebuild-detector'"],
                                    capitalize_label=False),
            self._gen_bool_selector(id_='rebuild_detector_no_bin',
                                    label_key='arch.config.aur_rebuild_detector_no_bin',
                                    label_params=['rebuild-detector'],
                                    tooltip_key='arch.config.aur_rebuild_detector_no_bin.tip',
                                    tooltip_params=['rebuild-detector',
                                                    self.i18n['arch.config.aur_rebuild_detector'].format('')],
                                    value=bool(arch_config['aur_rebuild_detector_no_bin']),
                                    capitalize_label=False),
            new_select(id_='aur_build_only_chosen',
                       label=self.i18n['arch.config.aur_build_only_chosen'],
                       tip=self.i18n['arch.config.aur_build_only_chosen.tip'],
                       opts=[(self.i18n['yes'].capitalize(), True, None),
                             (self.i18n['no'].capitalize(), False, None),
                             (self.i18n['ask'].capitalize(), None, None),
                             ],
                       value=arch_config['aur_build_only_chosen'],
                       type_=SelectViewType.RADIO,
                       capitalize_label=False),
            new_select(label=self.i18n['arch.config.edit_aur_pkgbuild'],
                       tip=self.i18n['arch.config.edit_aur_pkgbuild.tip'],
                       id_='edit_aur_pkgbuild',
                       opts=[(self.i18n['yes'].capitalize(), True, None),
                             (self.i18n['no'].capitalize(), False, None),
                             (self.i18n['ask'].capitalize(), None, None),
                             ],
                       value=arch_config['edit_aur_pkgbuild'],
                       type_=SelectViewType.RADIO,
                       capitalize_label=False),
            self._gen_bool_selector(id_='aur_remove_build_dir',
                                    label_key='arch.config.aur_remove_build_dir',
                                    tooltip_key='arch.config.aur_remove_build_dir.tip',
                                    value=bool(arch_config['aur_remove_build_dir']),
                                    capitalize_label=False),
            FileChooserComponent(id_='aur_build_dir',
                                 label=self.i18n['arch.config.aur_build_dir'],
                                 tooltip=self.i18n['arch.config.aur_build_dir.tip'].format(
                                     get_build_dir(arch_config, self.pkgbuilder_user)),
                                 file_path=arch_config['aur_build_dir'],
                                 capitalize_label=False,
                                 directory=True),
            TextInputComponent(id_='aur_idx_exp',
                               label=self.i18n['arch.config.aur_idx_exp'],
                               tooltip=self.i18n['arch.config.aur_idx_exp.tip'],
                               only_int=True,
                               capitalize_label=False,
                               value=arch_config['aur_idx_exp'] if isinstance(arch_config['aur_idx_exp'], int) else '')
        ]

        return SettingsView(self, PanelComponent([FormComponent(fields, spaces=False)], id_='aur'),
                            label='AUR',
                            icon_path=get_icon_path())

    def get_settings(self) -> Optional[Generator[SettingsView, None, None]]:
        arch_config = self.configman.get_config()
        yield self._get_general_settings(arch_config)
        yield self._get_aur_settings(arch_config)

    @staticmethod
    def fill_general_settings(arch_config: dict, form: FormComponent):
        arch_config['repositories'] = form.get_component('repos', SingleSelectComponent).get_selected()
        arch_config['sync_databases'] = form.get_component('sync_dbs', SingleSelectComponent).get_selected()
        arch_config['clean_cached'] = form.get_component('clean_cached', SingleSelectComponent).get_selected()
        arch_config['refresh_mirrors_startup'] = form.get_component('ref_mirs', SingleSelectComponent).get_selected()
        arch_config['mirrors_sort_limit'] = form.get_component('mirrors_sort_limit', TextInputComponent).get_int_value()
        arch_config['automatch_providers'] = form.get_component('autoprovs', SingleSelectComponent).get_selected()

        sync_dbs_startup = form.get_component('sync_dbs_start', SingleSelectComponent).get_selected()
        arch_config['sync_databases_startup'] = sync_dbs_startup

        mthread_download = form.get_component('mthread_download', SingleSelectComponent).get_selected()
        arch_config['repositories_mthread_download'] = mthread_download

        prefer_repo_provider = form.get_component('prefer_repo_provider', SingleSelectComponent).get_selected()
        arch_config['prefer_repository_provider'] = prefer_repo_provider

        check_dep_break = form.get_component('check_dependency_breakage', SingleSelectComponent).get_selected()
        arch_config['check_dependency_breakage'] = check_dep_break

        sug_opt_dep_uni = form.get_component('suggest_optdep_uninstall', SingleSelectComponent).get_selected()
        arch_config['suggest_optdep_uninstall'] = sug_opt_dep_uni

        sug_unneeded_uni = form.get_component('suggest_unneeded_uninstall', SingleSelectComponent).get_selected()
        arch_config['suggest_unneeded_uninstall'] = sug_unneeded_uni

        arch_config['categories_exp'] = form.get_component('arch_cats_exp', TextInputComponent).get_int_value()
        arch_config['suggestions_exp'] = form.get_component('arch_sugs_exp', TextInputComponent).get_int_value()

    def _fill_aur_settings(self, arch_config: dict, form: FormComponent):
        arch_config['optimize'] = form.get_component('opts', SingleSelectComponent).get_selected()

        rebuild_detect = form.get_component('rebuild_detector', SingleSelectComponent).get_selected()
        arch_config['aur_rebuild_detector'] = rebuild_detect

        rebuild_no_bin = form.get_component('rebuild_detector_no_bin', SingleSelectComponent).get_selected()
        arch_config['aur_rebuild_detector_no_bin'] = rebuild_no_bin

        arch_config['edit_aur_pkgbuild'] = form.get_component('edit_aur_pkgbuild', SingleSelectComponent).get_selected()

        remove_build_dir = form.get_component('aur_remove_build_dir', SingleSelectComponent).get_selected()
        arch_config['aur_remove_build_dir'] = remove_build_dir

        build_chosen = form.get_component('aur_build_only_chosen', SingleSelectComponent).get_selected()
        arch_config['aur_build_only_chosen'] = build_chosen

        arch_config['aur_build_dir'] = form.get_component('aur_build_dir', FileChooserComponent).file_path
        arch_config['aur_idx_exp'] = form.get_component('aur_idx_exp', TextInputComponent).get_int_value()

        if not arch_config['aur_build_dir']:
            arch_config['aur_build_dir'] = None

        aur_enabled_select = form.get_component('aur', SingleSelectComponent)
        arch_config['aur'] = aur_enabled_select.get_selected()

        if aur_enabled_select.changed() and arch_config['aur']:
            self.index_aur = AURIndexUpdater(context=self.context, taskman=TaskManager(), arch_config=arch_config)
            self.index_aur.start()

    def save_settings(self, component: PanelComponent) -> Tuple[bool, Optional[List[str]]]:
        arch_config = self.configman.get_config()
        form = component.get_component_by_idx(0, FormComponent)

        if component.id == 'repo':
            self.fill_general_settings(arch_config, form)
        elif component.id == 'aur':
            self._fill_aur_settings(arch_config, form)

        try:
            self.configman.save_config(arch_config)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def get_upgrade_requirements(self, pkgs: List[ArchPackage], root_password: Optional[str], watcher: ProcessWatcher) -> UpgradeRequirements:
        self.aur_client.clean_caches()
        arch_config = self.configman.get_config()

        aur_supported = aur.is_supported(arch_config)

        self._sync_databases(arch_config=arch_config, aur_supported=aur_supported,
                             root_password=root_password, handler=ProcessHandler(watcher), change_substatus=False)

        summarizer = UpdatesSummarizer(aur_client=self.aur_client,
                                       aur_supported=aur_supported,
                                       i18n=self.i18n,
                                       logger=self.logger,
                                       deps_analyser=self.deps_analyser,
                                       watcher=watcher)
        try:
            return summarizer.summarize(pkgs, root_password, arch_config)
        except PackageNotFoundException:
            pass  # when nothing is returned, the upgrade is called off by the UI

    def gen_custom_actions(self) -> Generator[CustomSoftwareAction, None, None]:
        if self._custom_actions is None:
            self._custom_actions = {
                'sys_up': CustomSoftwareAction(i18n_label_key='arch.custom_action.upgrade_system',
                                               i18n_status_key='arch.custom_action.upgrade_system.status',
                                               i18n_description_key='arch.custom_action.upgrade_system.desc',
                                               manager_method='upgrade_system',
                                               icon_path=get_icon_path(),
                                               requires_root=True,
                                               backup=True,
                                               manager=self),
                'ref_dbs': CustomSoftwareAction(i18n_label_key='arch.custom_action.refresh_dbs',
                                                i18n_status_key='arch.sync_databases.substatus',
                                                i18n_description_key='arch.custom_action.refresh_dbs.desc',
                                                manager_method='sync_databases',
                                                icon_path=get_icon_path(),
                                                requires_root=True,
                                                manager=self),
                'ref_mirrors': CustomSoftwareAction(i18n_label_key='arch.custom_action.refresh_mirrors',
                                                    i18n_status_key='arch.task.mirrors',
                                                    i18n_description_key='arch.custom_action.refresh_mirrors.desc',
                                                    manager_method='refresh_mirrors',
                                                    icon_path=get_icon_path(),
                                                    requires_root=True,
                                                    manager=self,
                                                    requires_confirmation=False),
                'clean_cache': CustomSoftwareAction(i18n_label_key='arch.custom_action.clean_cache',
                                                    i18n_status_key='arch.custom_action.clean_cache.status',
                                                    i18n_description_key='arch.custom_action.clean_cache.desc',
                                                    manager_method='clean_cache',
                                                    icon_path=get_icon_path(),
                                                    requires_root=True,
                                                    refresh=False,
                                                    manager=self,
                                                    requires_confirmation=False),
                'setup_snapd': CustomSoftwareAction(i18n_label_key='arch.custom_action.setup_snapd',
                                                    i18n_status_key='arch.custom_action.setup_snapd.status',
                                                    i18n_description_key='arch.custom_action.setup_snapd.desc',
                                                    manager_method='setup_snapd',
                                                    icon_path=get_icon_path(),
                                                    requires_root=False,
                                                    refresh=False,
                                                    manager=self,
                                                    requires_confirmation=False)
            }

        arch_config = self.configman.get_config()

        if pacman.is_mirrors_available():
            yield self._custom_actions['ref_mirrors']

        yield self._custom_actions['ref_dbs']
        yield self._custom_actions['clean_cache']

        if bool(arch_config['repositories']):
            yield self._custom_actions['sys_up']

        if pacman.is_snapd_installed():
            yield self._custom_actions['setup_snapd']

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

    def upgrade_system(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        # repo_map = pacman.map_repositories()
        net_available = self.context.internet_checker.is_available()
        installed = self.read_installed(limit=-1, only_apps=False, pkg_types=None, internet_available=net_available, disk_loader=None).installed

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

    def clean_cache(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:

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

    def _fill_ignored_updates(self, output: Set[str]) -> Set[str]:
        if os.path.exists(UPDATES_IGNORED_FILE):
            with open(UPDATES_IGNORED_FILE) as f:
                ignored_lines = f.readlines()

            for line in ignored_lines:
                if line:
                    line_clean = line.strip()

                    if line_clean:
                        output.add(line_clean)

        return output

    def _write_ignored(self, names: Set[str]):
        Path(ARCH_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        ignored_list = [*names]
        ignored_list.sort()

        with open(UPDATES_IGNORED_FILE, 'w+') as f:
            if ignored_list:
                for pkg in ignored_list:
                    f.write('{}\n'.format(pkg))
            else:
                f.write('')

    def ignore_update(self, pkg: ArchPackage):
        ignored = self._fill_ignored_updates(set())

        if pkg.name not in ignored:
            ignored.add(pkg.name)
            self._write_ignored(ignored)

        pkg.update_ignored = True

    def _revert_ignored_updates(self, pkgs: Iterable[str]):
        ignored = self._fill_ignored_updates(set())

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

    def enable_pkgbuild_edition(self, pkg: ArchPackage, root_password: Optional[str], watcher: ProcessWatcher):
        if self._add_as_editable_pkgbuild(pkg.name):
            pkg.pkgbuild_editable = True

    def disable_pkgbuild_edition(self, pkg: ArchPackage, root_password: Optional[str], watcher: ProcessWatcher):
        if self._remove_from_editable_pkgbuilds(pkg.name):
            pkg.pkgbuild_editable = False

    def setup_snapd(self, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
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

                valid_pwd, pwd = watcher.request_root_password()

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

        pkgbuild_path = f'{context.project_dir}/PKGBUILD'

        with open(pkgbuild_path) as f:
            current_pkgbuild = f.read()

        if context.pkgs_to_build:
            names = '({})'.format(' '.join(("'{}'".format(p) for p in context.pkgs_to_build)))
        else:
            names = context.name
            context.pkgs_to_build = {context.name}

        new_pkgbuild = RE_PKGBUILD_PKGNAME.sub(f"pkgname={names}", current_pkgbuild)
        custom_pkgbuild_path = f'{pkgbuild_path}_CUSTOM'

        if not write_as_user(content=new_pkgbuild,
                             file_path=custom_pkgbuild_path,
                             user=self.pkgbuilder_user):
            self.logger.error(f"Could not write edited PKGBUILD to '{custom_pkgbuild_path}'")
            return

        new_srcinfo = makepkg.gen_srcinfo(build_dir=context.project_dir,
                                          custom_pkgbuild_path=custom_pkgbuild_path,
                                          custom_user=self.pkgbuilder_user)

        srcinfo_path = f'{context.project_dir}/.SRCINFO'
        if not write_as_user(content=new_srcinfo, file_path=srcinfo_path, user=self.pkgbuilder_user):
            self.logger.warning(f"Could not write the updated .SRCINFO content to '{srcinfo_path}'")

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
                    except PackageNotFoundException:
                        self.logger.warning(f"No hard requirements found for optional {p}. Reason: package not found")

        return res

    def reinstall(self, pkg: ArchPackage, root_password: Optional[str], watcher: ProcessWatcher) -> bool:  # only available for AUR packages
        if not self.context.internet_checker.is_available():
            raise NoInternetException()

        self.aur_client.clean_caches()

        apidatas = self.aur_client.get_info((pkg.name,))

        if not apidatas:
            watcher.show_message(title=self.i18n['error'],
                                 body=self.i18n['arch.action.reinstall.error.no_apidata'],
                                 type_=MessageType.ERROR)
            return False

        self.aur_mapper.fill_last_modified(pkg, apidatas[0])
        context = TransactionContext.gen_context_from(pkg=pkg,
                                                      arch_config=self.configman.get_config(),
                                                      root_password=root_password,
                                                      handler=ProcessHandler(watcher),
                                                      aur_supported=True)
        context.skip_opt_deps = False
        context.update_aur_index = True

        return self.install(pkg=pkg,
                            root_password=root_password,
                            watcher=watcher,
                            context=context,
                            disk_loader=self.context.disk_loader_factory.new()).success

    def set_rebuild_check(self, pkg: ArchPackage, root_password: Optional[str], watcher: ProcessWatcher) -> bool:
        if pkg.repository != 'aur':
            return False

        try:
            if pkg.allow_rebuild:
                rebuild_detector.add_as_ignored(pkg.name)
                pkg.allow_rebuild = False
            else:
                rebuild_detector.remove_from_ignored(pkg.name)
                pkg.allow_rebuild = True
        except:
            self.logger.error("An unexpected exception happened")
            traceback.print_exc()
            return False

        pkg.update_state()
        return True

    def check_action_allowed(self, pkg: ArchPackage, watcher: Optional[ProcessWatcher]) -> bool:
        if self.context.root_user and pkg.repository == 'aur':
            if not shutil.which('useradd'):
                if watcher:
                    watcher.show_message(title=self.i18n['error'].capitalize(),
                                         type_=MessageType.ERROR,
                                         body=self.i18n['arch.aur.error.missing_root_dep'].format(dep=bold('useradd'),
                                                                                                  aur=bold('AUR'),
                                                                                                  root=bold('root')))
                return False

            if not shutil.which('runuser'):
                if watcher:
                    watcher.show_message(title=self.i18n['error'].capitalize(),
                                         type_=MessageType.ERROR,
                                         body=self.i18n['arch.aur.error.missing_root_dep'].format(dep=bold('runuser'),
                                                                                                  aur=bold('AUR'),
                                                                                                  root=bold('root')))
                return False

        return True

    def add_package_builder_user(self, handler: ProcessHandler) -> bool:
        if self.context.root_user and self.pkgbuilder_user:
            try:
                getpwnam(self.pkgbuilder_user)
                return True
            except KeyError:
                self.logger.warning(f"Package builder user '{self.pkgbuilder_user}' does not exist")
                self.logger.info(f"Adding the package builder user '{self.pkgbuilder_user}'")
                added, output = handler.handle_simple(SimpleProcess(cmd=['useradd', self.pkgbuilder_user], shell=True))

                if not added:
                    output_log = "Command output: {}".format(output.replace('\n', ' ') if output else '(no output)')
                    self.logger.error(f"Could not add the package builder user '{self.pkgbuilder_user}'. {output_log}")
                    handler.watcher.show_message(title=self.i18n['error'].capitalize(),
                                                 type_=MessageType.ERROR,
                                                 body=self.i18n['arch.aur.error.add_builder_user'].format(user=bold(self.pkgbuilder_user),
                                                                                                          aur=bold('AUR')))

                return added

        return True

    def _fill_available_packages(self, output: Dict[str, Set[str]]):
        output.update(pacman.map_available_packages())

    def _fill_suggestions(self, output: Dict[str, int]):
        self.suggestions_downloader.register_task(None)
        suggestions = self.suggestions_downloader.read(self.configman.read_config())

        if suggestions:
            output.update(suggestions)

    def _fill_cached_if_unset(self, pkg: ArchPackage, loader: DiskCacheLoader):
        data = loader.read(pkg)

        if data:
            for attr, cached_val in data.items():
                if cached_val:
                    current_val = getattr(pkg, attr)

                    if current_val is None:
                        setattr(pkg, attr, cached_val)

    def list_suggestions(self, limit: int, filter_installed: bool) -> Optional[List[PackageSuggestion]]:
        if limit == 0:
            return

        arch_config = self.configman.get_config()

        if not arch_config['repositories']:
            return

        name_priority = dict()

        fill_suggestions = Thread(target=self._fill_suggestions, args=(name_priority,))
        fill_suggestions.start()

        available_packages = dict()
        fill_available = Thread(target=self._fill_available_packages, args=(available_packages,))
        fill_available.start()

        ignored_pkgs = set()
        fill_ignored = Thread(target=pacman.fill_ignored_packages, args=(ignored_pkgs,))
        fill_ignored.start()

        fill_suggestions.join()

        if not name_priority:
            self.logger.info("No Arch package suggestions found")
            return

        self.logger.info(f"Found {len(name_priority)} named Arch package suggestions")

        if fill_available:
            fill_available.join()

        if not available_packages:
            self.logger.error("No available Arch package found. It will not be possible to return suggestions")
            return

        fill_ignored.join()

        available_suggestions = dict()

        for n in name_priority:
            if n not in ignored_pkgs:
                data = available_packages.get(n)

                if data and (not filter_installed or not data['i']):
                    available_suggestions[n] = data

        if not available_suggestions:
            self.logger.info("No Arch package suggestion to return")
            return

        if filter_installed:
            ignored_updates = set()
            thread_fill_ignored_updates = Thread(target=self._fill_ignored_updates, args=(ignored_updates,))
            thread_fill_ignored_updates.start()
        else:
            ignored_updates, thread_fill_ignored_updates = None, None

        suggestion_by_priority = sort_by_priority({n: name_priority[n] for n in available_suggestions})

        if available_suggestions and 0 < limit < len(available_suggestions):
            suggestion_by_priority = suggestion_by_priority[0:limit]

        self.logger.info(f'Available Arch package suggestions: {len(suggestion_by_priority)}')

        if thread_fill_ignored_updates:
            thread_fill_ignored_updates.join()

        full_data = pacman.map_packages(names=suggestion_by_priority, remote=filter_installed, not_signed=False,
                                        skip_ignored=True)

        if full_data and full_data.get('signed'):
            full_data = full_data['signed']

        disk_loader, caching_threads = None, None
        if not filter_installed:
            disk_loader = self.context.disk_loader_factory.new()
            caching_threads = list()

        suggestions = []
        for name in suggestion_by_priority:
            pkg_data = available_suggestions[name]
            pkg_full_data = full_data.get(name)
            description = None

            if pkg_full_data:
                description = pkg_full_data.get('description')

            pkg_updates_ignored = pkg_data['i'] and ignored_updates and name in ignored_updates
            pkg = ArchPackage(name=name,
                              version=pkg_data['v'],
                              latest_version=pkg_data['v'],
                              repository=pkg_data['r'],
                              installed=pkg_data['i'],
                              description=description,
                              categories=self.categories.get(name),
                              i18n=self.i18n,
                              maintainer=pkg_data['r'],
                              update_ignored=pkg_updates_ignored)

            if disk_loader:
                t = Thread(target=self._fill_cached_if_unset, args=(pkg, disk_loader))
                t.start()
                caching_threads.append(t)

            suggestions.append(PackageSuggestion(package=pkg, priority=name_priority[name]))

        if caching_threads:
            for t in caching_threads:
                t.join()

        return suggestions

    @property
    def suggestions_downloader(self) -> RepositorySuggestionsDownloader:
        if not self._suggestions_downloader:
            file_url = self.context.get_suggestion_url(self.__module__)

            self._suggestions_downloader = RepositorySuggestionsDownloader(logger=self.logger,
                                                                           http_client=self.http_client,
                                                                           i18n=self.i18n,
                                                                           file_url=file_url)

            if self._suggestions_downloader.is_custom_local_file_mapped():
                self.logger.info(f"Local Arch suggestions file mapped: {file_url}")

        return self._suggestions_downloader
