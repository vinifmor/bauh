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
from typing import List, Set, Type, Tuple, Dict

import requests

from bauh.api.abstract.controller import SearchResult, SoftwareManager, ApplicationContext
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher, TaskManager
from bauh.api.abstract.model import PackageUpdate, PackageHistory, SoftwarePackage, PackageSuggestion, PackageStatus, \
    SuggestionPriority, CustomSoftwareAction
from bauh.api.abstract.view import MessageType, FormComponent, InputOption, SingleSelectComponent, SelectViewType, \
    ViewComponent, PanelComponent, MultipleSelectComponent, TextInputComponent
from bauh.api.constants import TEMP_DIR
from bauh.commons import user
from bauh.commons.category import CategoriesDownloader
from bauh.commons.config import save_config
from bauh.commons.html import bold
from bauh.commons.system import SystemProcess, ProcessHandler, new_subprocess, run_cmd, new_root_subprocess, \
    SimpleProcess
from bauh.gems.arch import BUILD_DIR, aur, pacman, makepkg, pkgbuild, message, confirmation, disk, git, \
    gpg, URL_CATEGORIES_FILE, CATEGORIES_CACHE_DIR, CATEGORIES_FILE_PATH, CUSTOM_MAKEPKG_FILE, SUGGESTIONS_FILE, \
    CONFIG_FILE, get_icon_path, database, mirrors
from bauh.gems.arch.aur import AURClient
from bauh.gems.arch.config import read_config
from bauh.gems.arch.depedencies import DependenciesAnalyser
from bauh.gems.arch.mapper import ArchDataMapper
from bauh.gems.arch.model import ArchPackage
from bauh.gems.arch.worker import AURIndexUpdater, ArchDiskCacheUpdater, ArchCompilationOptimizer, SyncDatabases, \
    RefreshMirrors

URL_GIT = 'https://aur.archlinux.org/{}.git'
URL_PKG_DOWNLOAD = 'https://aur.archlinux.org/cgit/aur.git/snapshot/{}.tar.gz'
URL_SRC_INFO = 'https://aur.archlinux.org/cgit/aur.git/plain/.SRCINFO?h='

RE_SPLIT_VERSION = re.compile(r'(=|>|<)')

SOURCE_FIELDS = ('source', 'source_x86_64')
RE_PRE_DOWNLOAD_WL_PROTOCOLS = re.compile(r'^(.+::)?(https?|ftp)://.+')
RE_PRE_DOWNLOAD_BL_EXT = re.compile(r'.+\.(git|gpg)$')


class ArchManager(SoftwareManager):

    def __init__(self, context: ApplicationContext):
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
        self.deps_analyser = DependenciesAnalyser(self.aur_client)
        self.local_config = None
        self.http_client = context.http_client
        self.custom_actions = [CustomSoftwareAction(i18_label_key='arch.custom_action.refresh_mirrors',
                                                    i18n_status_key='arch.task.mirrors',
                                                    manager_method='refresh_mirrors',
                                                    icon_path=get_icon_path(),
                                                    requires_root=True,
                                                    manager=self),
                               CustomSoftwareAction(i18_label_key='arch.custom_action.refresh_dbs',
                                                    i18n_status_key='arch.sync_databases.substatus',
                                                    manager_method='sync_databases',
                                                    icon_path=get_icon_path(),
                                                    requires_root=True,
                                                    manager=self)]
        self.index_aur = None

    @staticmethod
    def get_semantic_search_map() -> Dict[str, str]:
        return {'google chrome': 'google-chrome',
                'chrome google': 'google-chrome',
                'googlechrome': 'google-chrome'}

    def refresh_mirrors(self, root_password: str, watcher: ProcessWatcher) -> bool:

        available_countries = pacman.list_mirror_countries()
        current_countries = pacman.get_current_mirror_countries()

        if not available_countries:
            self.logger.warning("No country available")
            countries = current_countries
        else:
            country_opts = [InputOption(label=self.i18n['arch.custom_action.refresh_mirrors.location.all'], value='all')]
            mapped_opts = [InputOption(label=self.i18n[' '.join(c.split('_')).lower()].capitalize(), value=c) for c in available_countries]

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
            success, output = ProcessHandler(watcher).handle_simple(pacman.refresh_mirrors(root_password))
        else:
            success, output = ProcessHandler(watcher).handle_simple(pacman.update_mirrors(root_password, countries))

        if not success:
            watcher.show_message(title=self.i18n["action.failed"].capitalize(),
                                 body=self.i18n['arch.custom_action.refresh_mirrors.failed'],
                                 type_=MessageType.ERROR)
            return False

        sort_limit = read_config()['mirrors_sort_limit']

        if sort_limit is not None and isinstance(sort_limit, int) and sort_limit >= 0:
            watcher.change_substatus(self.i18n['arch.custom_action.refresh_mirrors.status.sorting'])
            ProcessHandler(watcher).handle_simple(pacman.sort_fastest_mirrors(root_password, sort_limit))

        mirrors.register_sync(self.logger)

        return self.sync_databases(root_password=root_password, watcher=watcher)

    def sync_databases(self, root_password: str, watcher: ProcessWatcher) -> bool:
        success, output = ProcessHandler(watcher).handle_simple(pacman.sync_databases(root_password, force=True))

        if not success:
            watcher.show_message(title=self.i18n["action.failed"].capitalize(),
                                 body=self.i18n['arch.custom_action.refresh_mirrors.failed'],
                                 type_=MessageType.ERROR)
            return False

        database.register_sync(self.logger)
        return True

    def _upgrade_search_result(self, apidata: dict, installed_pkgs: dict, downgrade_enabled: bool, res: SearchResult, disk_loader: DiskCacheLoader):
        app = self.mapper.map_api_data(apidata, installed_pkgs['not_signed'], self.categories)
        app.downgrade_enabled = downgrade_enabled

        if app.installed:
            res.installed.append(app)

            if disk_loader:
                disk_loader.fill(app)
        else:
            res.new.append(app)

        Thread(target=self.mapper.fill_package_build, args=(app,), daemon=True).start()

    def _search_in_repos_and_fill(self, words: str, disk_loader: DiskCacheLoader, res: SearchResult):
        repo_search = pacman.search(words)

        if repo_search:
            for name, data in repo_search.items():
                pkg = ArchPackage(name=name, i18n=self.i18n, **data)
                pkg.latest_version = pkg.version
                pkg.downgrade_enabled = True

                if disk_loader:
                    disk_loader.fill(pkg)

                if pkg.installed:
                    res.installed.append(pkg)
                else:
                    res.new.append(pkg)

    def _search_in_aur_and_fill(self, words: str, disk_loader: DiskCacheLoader, read_installed: Thread, installed: dict, res: SearchResult):
        api_res = self.aur_client.search(words)

        if api_res and api_res.get('results'):
            read_installed.join()

            downgrade_enabled = git.is_enabled()
            for pkgdata in api_res['results']:
                self._upgrade_search_result(pkgdata, installed, downgrade_enabled, res, disk_loader)

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
                    downgrade_enabled = git.is_enabled()

                    for pkgdata in pkgsinfo:
                        self._upgrade_search_result(pkgdata, installed, downgrade_enabled, res, disk_loader)

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        if is_url:
            return SearchResult([], [], 0)

        arch_config = read_config()
        res = SearchResult([], [], 0)

        if not any((arch_config['aur'], arch_config['repositories'])):
            return res

        mapped_words = self.get_semantic_search_map().get(words)
        final_words = mapped_words or words

        aur_search = None
        if arch_config['aur']:
            installed = {}
            read_installed = Thread(target=lambda: installed.update(pacman.map_installed(repositories=False)), daemon=True)
            read_installed.start()

            aur_search = Thread(target=self._search_in_aur_and_fill, args=(final_words, disk_loader, read_installed, installed, res), daemon=True)
            aur_search.start()

        if arch_config['repositories']:
            self._search_in_repos_and_fill(final_words, disk_loader, res)

        if aur_search:
            aur_search.join()

        res.total = len(res.installed) + len(res.new)
        return res

    def _fill_aur_pkgs(self, not_signed: dict, pkgs: list, disk_loader: DiskCacheLoader, internet_available: bool):
        downgrade_enabled = git.is_enabled()

        if internet_available:
            try:
                pkgsinfo = self.aur_client.get_info(not_signed.keys())

                if pkgsinfo:
                    for pkgdata in pkgsinfo:
                        pkg = self.mapper.map_api_data(pkgdata, not_signed, self.categories)
                        pkg.downgrade_enabled = downgrade_enabled

                        if disk_loader:
                            disk_loader.fill(pkg)
                            pkg.status = PackageStatus.READY

                        pkgs.append(pkg)

                return
            except requests.exceptions.ConnectionError:
                self.logger.warning('Could not retrieve installed AUR packages API data. It seems the internet connection is off.')
                self.logger.info("Reading only local AUR packages data")

        for name, data in not_signed.items():
            pkg = ArchPackage(name=name, version=data.get('version'),
                              latest_version=data.get('version'), description=data.get('description'),
                              installed=True, repository='aur', i18n=self.i18n)

            pkg.categories = self.categories.get(pkg.name)
            pkg.downgrade_enabled = downgrade_enabled

            if disk_loader:
                disk_loader.fill(pkg)
                pkg.status = PackageStatus.READY

            pkgs.append(pkg)

    def _fill_repo_updates(self, updates: dict):
        updates.update(pacman.list_repository_updates())

    def _fill_repo_pkgs(self, signed: dict, pkgs: list, disk_loader: DiskCacheLoader):
        updates = {}

        thread_updates = Thread(target=self._fill_repo_updates, args=(updates,), daemon=True)
        thread_updates.start()

        repo_map = pacman.map_repositories(list(signed.keys()))

        if len(repo_map) != len(signed):
            self.logger.warning("Not mapped all signed packages repositories. Mapped: {}. Total: {}".format(len(repo_map), len(signed)))

        thread_updates.join()
        for name, data in signed.items():
            pkg = ArchPackage(name=name,
                              version=data.get('version'),
                              latest_version=data.get('version'),
                              description=data.get('description'),
                              i18n=self.i18n,
                              installed=True,
                              repository=repo_map.get(name))
            pkg.downgrade_enabled = True
            if updates:
                update_version = updates.get(pkg.name)

                if update_version:
                    pkg.latest_version = update_version
                    pkg.update = True

            if disk_loader:
                disk_loader.fill(pkg)

            pkgs.append(pkg)

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = None) -> SearchResult:
        arch_config = read_config()
        installed = pacman.map_installed(repositories=arch_config['repositories'], aur=arch_config['aur'])

        pkgs = []
        if installed and (installed['not_signed'] or installed['signed']):
            map_threads = []

            if installed['not_signed']:
                t = Thread(target=self._fill_aur_pkgs, args=(installed['not_signed'], pkgs, disk_loader, internet_available), daemon=True)
                t.start()
                map_threads.append(t)

            if installed['signed']:
                t = Thread(target=self._fill_repo_pkgs, args=(installed['signed'], pkgs, disk_loader), daemon=True)
                t.start()
                map_threads.append(t)

            for t in map_threads:
                t.join()

        return SearchResult(pkgs, None, len(pkgs))

    def _downgrade_aur_pkg(self, pkg: ArchPackage, root_password: str, handler: ProcessHandler):
        self._sync_databases(root_password=root_password, handler=handler)

        app_build_dir = '{}/build_{}'.format(BUILD_DIR, int(time.time()))

        try:
            if not os.path.exists(app_build_dir):
                build_dir = handler.handle(SystemProcess(new_subprocess(['mkdir', '-p', app_build_dir])))

                if build_dir:
                    handler.watcher.change_progress(10)
                    base_name = pkg.get_base_name()
                    handler.watcher.change_substatus(self.i18n['arch.clone'].format(bold(pkg.name)))
                    clone = handler.handle(SystemProcess(subproc=new_subprocess(['git', 'clone', URL_GIT.format(base_name)],
                                                                                cwd=app_build_dir),check_error_output=False))
                    handler.watcher.change_progress(30)
                    if clone:
                        handler.watcher.change_substatus(self.i18n['arch.downgrade.reading_commits'])
                        clone_path = '{}/{}'.format(app_build_dir, base_name)
                        srcinfo_path = '{}/.SRCINFO'.format(clone_path)

                        commits = run_cmd("git log", cwd=clone_path)
                        handler.watcher.change_progress(40)

                        if commits:
                            commit_list = re.findall(r'commit (.+)\n', commits)
                            if commit_list:
                                if len(commit_list) > 1:
                                    srcfields = {'pkgver', 'pkgrel'}

                                    commit_found = None
                                    for idx in range(1, len(commit_list)):
                                        commit = commit_list[idx]
                                        with open(srcinfo_path) as f:
                                            pkgsrc = aur.map_srcinfo(f.read(), srcfields)

                                        if not handler.handle(SystemProcess(subproc=new_subprocess(['git', 'reset', '--hard', commit],
                                                                            cwd=clone_path), check_error_output=False)):
                                            handler.watcher.print('Could not downgrade anymore. Aborting...')
                                            return False

                                        if '{}-{}'.format(pkgsrc.get('pkgver'), pkgsrc.get('pkgrel')) == pkg.version:
                                            # current version found
                                            commit_found = commit
                                        elif commit_found:
                                            handler.watcher.change_substatus(self.i18n['arch.downgrade.version_found'])
                                            if not handler.handle(SystemProcess(subproc=new_subprocess(['git', 'checkout', commit_found],
                                                                               cwd=clone_path), check_error_output=False)):
                                                handler.watcher.print("Could not rollback to current version's commit")
                                                return False

                                            if not handler.handle(SystemProcess(subproc=new_subprocess(['git', 'reset', '--hard', commit_found],
                                                                                cwd=clone_path), check_error_output=False)):
                                                handler.watcher.print("Could not downgrade to previous commit of '{}'. Aborting...".format(commit_found))
                                                return False

                                            break

                                    handler.watcher.change_substatus(self.i18n['arch.downgrade.install_older'])
                                    return self._build(pkg.name, base_name, pkg.maintainer, root_password, handler,
                                                       app_build_dir, clone_path, dependency=False, skip_optdeps=True)
                                else:
                                    handler.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                                                 body=self.i18n['arch.downgrade.impossible'].format(pkg.name),
                                                                 type_=MessageType.ERROR)
                                    return False

                        handler.watcher.show_message(title=self.i18n['error'],
                                                     body=self.i18n['arch.downgrade.no_commits'],
                                                     type_=MessageType.ERROR)
                        return False

        finally:
            if os.path.exists(app_build_dir):
                handler.handle(SystemProcess(subproc=new_subprocess(['rm', '-rf', app_build_dir])))

            self.local_config = None

        return False

    def _downgrade_repo_pkg(self, pkg: ArchPackage, root_password: str, handler: ProcessHandler):
        handler.watcher.change_substatus(self.i18n['arch.downgrade.searching_stored'])
        if not os.path.isdir('/var/cache/pacman/pkg'):
            handler.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                         body=self.i18n['arch.downgrade.repo_pkg.no_versions'],
                                         type_=MessageType.ERROR)
            return False

        available_files = glob.glob("/var/cache/pacman/pkg/{}-*.pkg.tar.*".format(pkg.name))

        if not available_files:
            handler.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                         body=self.i18n['arch.downgrade.repo_pkg.no_versions'],
                                         type_=MessageType.ERROR)
            return False

        reg = re.compile(r'{}-([\w.\-]+)-(x86_64|any|i686).pkg'.format(pkg.name))

        versions, version_files = [], {}
        for file_path in available_files:
            found = reg.findall(os.path.basename(file_path))

            if found:
                ver = found[0][0]
                if ver not in versions and ver < pkg.version:
                    versions.append(ver)
                    version_files[ver] = file_path

        handler.watcher.change_progress(40)
        if not versions:
            handler.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                         body=self.i18n['arch.downgrade.repo_pkg.no_versions'],
                                         type_=MessageType.ERROR)
            return False

        versions.sort(reverse=True)

        self._sync_databases(root_password=root_password, handler=handler)
        handler.watcher.change_progress(50)

        handler.watcher.change_substatus(self.i18n['arch.downgrade.install_older'])

        handler.watcher.change_progress(60)
        if not handler.handle(pacman.install_as_process(pkgpath=version_files[versions[0]],
                                                        root_password=root_password,
                                                        file=True)):
            handler.watcher.show_message(title=self.i18n['arch.downgrade.error'],
                                         body=self.i18n['arch.downgrade.impossible'].format(pkg.name),
                                         type_=MessageType.ERROR)
            return False

        handler.watcher.change_progress(100)
        return True

    def downgrade(self, pkg: ArchPackage, root_password: str, watcher: ProcessWatcher) -> bool:
        if not self._check_action_allowed(pkg, watcher):
            return False

        self.local_config = read_config()

        handler = ProcessHandler(watcher)

        watcher.change_progress(5)

        if pkg.repository == 'aur':
            return self._downgrade_aur_pkg(pkg, root_password, handler)
        else:
            return self._downgrade_repo_pkg(pkg, root_password, handler)

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

    def update(self, pkg: ArchPackage, root_password: str, watcher: ProcessWatcher) -> bool:
        if not self._check_action_allowed(pkg, watcher):
            return False

        self.local_config = read_config()

        try:
            return self.install(pkg=pkg, root_password=root_password, watcher=watcher, skip_optdeps=True)
        finally:
            self.local_config = None

    def _uninstall(self, pkg_name: str, root_password: str, handler: ProcessHandler) -> bool:
        res = handler.handle(SystemProcess(new_root_subprocess(['pacman', '-R', pkg_name, '--noconfirm'], root_password)))

        if res:
            cache_path = ArchPackage.disk_cache_path(pkg_name)
            if os.path.exists(cache_path):
                shutil.rmtree(cache_path)
        return res

    def uninstall(self, pkg: ArchPackage, root_password: str, watcher: ProcessWatcher) -> bool:
        self.local_config = read_config()
        try:
            handler = ProcessHandler(watcher)

            watcher.change_progress(10)
            info = pacman.get_info_dict(pkg.name)
            watcher.change_progress(50)

            if info.get('required by'):
                pkname = bold(pkg.name)
                msg = '{}:<br/><br/>{}<br/><br/>{}'.format(self.i18n['arch.uninstall.required_by'].format(pkname), bold(info['required by']), self.i18n['arch.uninstall.required_by.advice'].format(pkname))
                watcher.show_message(title=self.i18n['error'], body=msg, type_=MessageType.WARNING)
                return False

            uninstalled = self._uninstall(pkg.name, root_password, handler)

            if pkg.repository != 'aur' and self.local_config['clean_cached']:  # cleaning old versions
                watcher.change_substatus(self.i18n['arch.uninstall.clean_cached.substatus'])
                if os.path.isdir('/var/cache/pacman/pkg'):
                    available_files = glob.glob("/var/cache/pacman/pkg/{}-*.pkg.tar.*".format(pkg.name))

                    if available_files and not handler.handle_simple(SimpleProcess(cmd=['rm', '-rf', *available_files],
                                                                                   root_password=root_password)):
                        watcher.show_message(title=self.i18n['error'],
                                             body=self.i18n['arch.uninstall.clean_cached.error'].format(bold(pkg.name)),
                                             type_=MessageType.WARNING)

            watcher.change_progress(100)
            return uninstalled
        finally:
            self.local_config = None

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
        temp_dir = '{}/build_{}'.format(BUILD_DIR, int(time.time()))

        try:
            Path(temp_dir).mkdir(parents=True)
            base_name = pkg.get_base_name()
            run_cmd('git clone ' + URL_GIT.format(base_name), print_error=False, cwd=temp_dir)

            clone_path = '{}/{}'.format(temp_dir, base_name)
            srcinfo_path = '{}/.SRCINFO'.format(clone_path)

            commits = git.list_commits(clone_path)

            if commits:
                srcfields = {'pkgver', 'pkgrel'}
                history, status_idx = [], -1

                for idx, commit in enumerate(commits):
                    with open(srcinfo_path) as f:
                        pkgsrc = aur.map_srcinfo(f.read(), srcfields)

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

    def _install_deps(self, deps: List[Tuple[str, str]], root_password: str, handler: ProcessHandler, change_progress: bool = False) -> str:
        """
        :param pkgs_repos:
        :param root_password:
        :param handler:
        :return: not installed dependency
        """
        progress_increment = int(100 / len(deps))
        progress = 0
        self._update_progress(handler.watcher, 1, change_progress)

        for dep in deps:
            handler.watcher.change_substatus(self.i18n['arch.install.dependency.install'].format(bold('{} ({})'.format(dep[0], dep[1]))))
            if dep[1] == 'aur':
                pkgbase = self.aur_client.get_src_info(dep[0])['pkgbase']
                installed = self._install_from_aur(pkgname=dep[0], pkgbase=pkgbase, maintainer=None, root_password=root_password, handler=handler, dependency=True, change_progress=False)
            else:
                installed = self._install(pkgname=dep[0], maintainer=dep[1], root_password=root_password, handler=handler, install_file=None, repository=dep[1], change_progress=False)

            if not installed:
                return dep[0]

            progress += progress_increment
            self._update_progress(handler.watcher, progress, change_progress)

        self._update_progress(handler.watcher, 100, change_progress)

    def _map_repos(self, pkgnames: Set[str]) -> dict:
        pkg_repos = pacman.get_repositories(pkgnames)  # getting repositories set

        if len(pkgnames) != len(pkg_repos):  # checking if any dep not found in the distro repos are from AUR
            norepos = {p for p in pkgnames if p not in pkg_repos}
            for pkginfo in self.aur_client.get_info(norepos):
                if pkginfo.get('Name') in norepos:
                    pkg_repos[pkginfo['Name']] = 'aur'

        return pkg_repos

    def _pre_download_source(self, project_dir: str, watcher: ProcessWatcher) -> bool:
        if self.context.file_downloader.is_multithreaded():
            with open('{}/.SRCINFO'.format(project_dir)) as f:
                srcinfo = aur.map_srcinfo(f.read())

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
                        args.update({'file_url': fdata[0], 'output_path': None})

                    if not self.context.file_downloader.download(**args):
                        watcher.print('Could not download source file {}'.format(args['file_url']))
                        return False

        return True

    def _should_check_subdeps(self):
        return self.local_config['transitive_checking']

    def _build(self, pkgname: str, base_name: str, maintainer: str, root_password: str, handler: ProcessHandler, build_dir: str, project_dir: str, dependency: bool, skip_optdeps: bool = False, change_progress: bool = True) -> bool:

        self._pre_download_source(project_dir, handler.watcher)

        self._update_progress(handler.watcher, 50, change_progress)

        if not self._handle_deps_and_keys(pkgname, root_password, handler, project_dir, check_subdeps=self._should_check_subdeps()):
            return False

        # building main package
        handler.watcher.change_substatus(self.i18n['arch.building.package'].format(bold(pkgname)))
        pkgbuilt, output = makepkg.make(project_dir, optimize=self.local_config['optimize'], handler=handler)
        self._update_progress(handler.watcher, 65, change_progress)

        if pkgbuilt:
            gen_file = [fname for root, dirs, files in os.walk(build_dir) for fname in files if re.match(r'^{}-.+\.tar\.xz'.format(pkgname), fname)]

            if not gen_file:
                handler.watcher.print('Could not find generated .tar.xz file. Aborting...')
                return False

            install_file = '{}/{}'.format(project_dir, gen_file[0])

            if self._install(pkgname=pkgname, maintainer=maintainer, root_password=root_password, repository='aur', handler=handler,
                             install_file=install_file, pkgdir=project_dir, change_progress=change_progress):

                if dependency or skip_optdeps:
                    return True

                handler.watcher.change_substatus(self.i18n['arch.optdeps.checking'].format(bold(pkgname)))

                if self._install_optdeps(pkgname, root_password, handler, project_dir):
                    return True

        return False

    def _map_known_missing_deps(self, known_deps: Dict[str, str], watcher: ProcessWatcher, check_subdeps: bool = True) -> List[Tuple[str, str]]:
        sorted_deps = []  # it will hold the proper order to install the missing dependencies

        repo_deps, aur_deps = set(), set()

        for dep, repo in known_deps.items():
            if repo == 'aur':
                aur_deps.add(dep)
            else:
                repo_deps.add(dep)

        if check_subdeps:
            for deps in ((repo_deps, 'repo'), (aur_deps, 'aur')):
                if deps[0]:
                    missing_subdeps = self.deps_analyser.get_missing_subdeps_of(deps[0], deps[1])

                    if missing_subdeps:
                        for dep in missing_subdeps:
                            if not dep[1]:
                                message.show_dep_not_found(dep[0], self.i18n, watcher)
                                return

                        for dep in missing_subdeps:
                            sorted_deps.append(dep)

        for dep, repo in known_deps.items():
            if repo != 'aur':
                sorted_deps.append((dep, repo))

        for dep in aur_deps:
            sorted_deps.append((dep, 'aur'))

        return sorted_deps

    def _check_missing_deps(self, pkgname: str, repository: str, srcinfo: dict, watcher: ProcessWatcher) -> Dict[str, str]:
        if repository == 'aur':
            missing = {}

            missing_subdeps = self.deps_analyser.get_missing_subdeps(name=pkgname, repository=repository, srcinfo=srcinfo)

            if missing_subdeps:
                for dep in missing_subdeps:
                    if not dep[1]:
                        message.show_dep_not_found(dep[0], self.i18n, watcher)
                        return

                for dep in missing_subdeps:
                    missing[dep[0]] = dep[1]

            return missing
        else:
            # TODO
            return []

    def _map_unknown_missing_deps(self, deps: List[str], watcher: ProcessWatcher, check_subdeps: bool = True) -> List[Tuple[str, str]]:
        depnames = {RE_SPLIT_VERSION.split(dep)[0] for dep in deps}
        dep_repos = self._map_repos(depnames)

        if len(depnames) != len(dep_repos):  # checking if a dependency could not be found in any repository
            for dep in depnames:
                if dep not in dep_repos:
                    message.show_dep_not_found(dep, self.i18n, watcher)
                    return

        return self._map_known_missing_deps(dep_repos, watcher, check_subdeps)

    def _ask_and_install_missing_deps(self, pkgname: str, root_password: str, missing_deps: List[Tuple[str, str]], handler: ProcessHandler) -> bool:
        handler.watcher.change_substatus(self.i18n['arch.missing_deps_found'].format(bold(pkgname)))

        if not confirmation.request_install_missing_deps(pkgname, missing_deps, handler.watcher, self.i18n):
            handler.watcher.print(self.i18n['action.cancelled'])
            return False

        dep_not_installed = self._install_deps(missing_deps, root_password, handler, change_progress=False)

        if dep_not_installed:
            message.show_dep_not_installed(handler.watcher, pkgname, dep_not_installed, self.i18n)
            return False

        return True

    def _handle_deps_and_keys(self, pkgname: str, root_password: str, handler: ProcessHandler, pkgdir: str, check_subdeps: bool = True) -> bool:
        handler.watcher.change_substatus(self.i18n['arch.checking.deps'].format(bold(pkgname)))

        if not self.local_config['simple_checking']:
            ti = time.time()
            with open('{}/.SRCINFO'.format(pkgdir)) as f:
                srcinfo = aur.map_srcinfo(f.read())

            missing_deps = self._check_missing_deps(pkgname=pkgname, repository='aur', srcinfo=srcinfo, watcher=handler.watcher)
            tf = time.time()

            if missing_deps is None:
                self.logger.info("Took {0:.2f} seconds to verify missing dependencies".format(tf - ti))

                return False  # it means one of the dependencies could not be found
            elif missing_deps and check_subdeps:
                missing_deps = self._map_known_missing_deps(known_deps=missing_deps, watcher=handler.watcher)
                tf = time.time()

                if missing_deps is None:
                    self.logger.info("Took {0:.2f} seconds to verify missing dependencies".format(tf - ti))
                    return False  # it means one of the dependencies could not be found

            self.logger.info("Took {0:.2f} seconds to verify missing dependencies".format(tf - ti))
            if missing_deps:
                if not self._ask_and_install_missing_deps(pkgname=pkgname,
                                                          root_password=root_password,
                                                          missing_deps=missing_deps,
                                                          handler=handler):
                    return False

                # it is necessary to re-check because missing PGP keys are only notified when there are no missing deps
                return self._handle_deps_and_keys(pkgname, root_password, handler, pkgdir, check_subdeps=False)

        ti = time.time()
        check_res = makepkg.check(pkgdir, optimize=self.local_config['optimize'], missing_deps=self.local_config['simple_checking'], handler=handler)

        if check_res:
            if check_res.get('missing_deps'):
                handler.watcher.change_substatus(self.i18n['arch.checking.missing_deps'].format(bold(pkgname)))
                missing_deps = self._map_unknown_missing_deps(check_res['missing_deps'], handler.watcher, check_subdeps=check_subdeps)
                tf = time.time()
                self.logger.info("Took {0:.2f} seconds to verify missing dependencies".format(tf - ti))

                if missing_deps is None:
                    return False

                if not self._ask_and_install_missing_deps(pkgname=pkgname,
                                                          root_password=root_password,
                                                          missing_deps=missing_deps,
                                                          handler=handler):
                    return False

                # it is necessary to re-check because missing PGP keys are only notified when there are no missing deps
                return self._handle_deps_and_keys(pkgname, root_password, handler, pkgdir, check_subdeps=False)

            if check_res.get('gpg_key'):
                if handler.watcher.request_confirmation(title=self.i18n['arch.aur.install.unknown_key.title'],
                                                        body=self.i18n['arch.install.aur.unknown_key.body'].format(bold(pkgname), bold(check_res['gpg_key']))):
                    handler.watcher.change_substatus(self.i18n['arch.aur.install.unknown_key.status'].format(bold(check_res['gpg_key'])))
                    if not handler.handle(gpg.receive_key(check_res['gpg_key'])):
                        handler.watcher.show_message(title=self.i18n['error'],
                                                     body=self.i18n['arch.aur.install.unknown_key.receive_error'].format(bold(check_res['gpg_key'])))
                        return False
                else:
                    handler.watcher.print(self.i18n['action.cancelled'])
                    return False

            if check_res.get('validity_check'):
                body = "<p>{}</p><p>{}</p>".format(self.i18n['arch.aur.install.validity_check.body'].format(bold(pkgname)),
                                                   self.i18n['arch.aur.install.validity_check.proceed'])
                return not handler.watcher.request_confirmation(title=self.i18n['arch.aur.install.validity_check.title'].format('( checksum )'),
                                                                body=body,
                                                                confirmation_label=self.i18n['no'].capitalize(),
                                                                deny_label=self.i18n['yes'].capitalize())

        return True

    def _install_optdeps(self, pkgname: str, root_password: str, handler: ProcessHandler, pkgdir: str) -> bool:
        with open('{}/.SRCINFO'.format(pkgdir)) as f:
            odeps = pkgbuild.read_optdeps_as_dict(f.read(), self.context.is_system_x86_64())

        if not odeps:
            return True

        to_install = {d for d in odeps if not pacman.check_installed(d)}

        if not to_install:
            return True

        pkg_repos = self._map_repos(to_install)

        if pkg_repos:
            final_optdeps = {dep: {'desc': odeps.get(dep), 'repository': pkg_repos.get(dep)} for dep, repository in pkg_repos.items()}

            deps_to_install = confirmation.request_optional_deps(pkgname, final_optdeps, handler.watcher, self.i18n)

            if not deps_to_install:
                return True
            else:
                sorted_deps = []

                if self._should_check_subdeps():
                    missing_deps = self._map_known_missing_deps({d: pkg_repos[d] for d in deps_to_install}, handler.watcher)

                    if missing_deps is None:
                        return True  # because the main package installation was successful

                    if missing_deps:
                        same_as_selected = len(deps_to_install) == len(missing_deps) and deps_to_install == {d[0] for d in missing_deps}

                        if not same_as_selected and not confirmation.request_install_missing_deps(None, missing_deps, handler.watcher, self.i18n):
                            handler.watcher.print(self.i18n['action.cancelled'])
                            return True  # because the main package installation was successful

                        sorted_deps.extend(missing_deps)
                else:
                    aur_deps, repo_deps = [], []

                    for dep in deps_to_install:
                        repository = pkg_repos[dep]

                        if repository == 'aur':
                            aur_deps.append((dep, repository))
                        else:
                            repo_deps.append((dep, repository))

                    sorted_deps.extend(repo_deps)
                    sorted_deps.extend(aur_deps)

                dep_not_installed = self._install_deps(sorted_deps, root_password, handler, change_progress=True)

                if dep_not_installed:
                    message.show_optdep_not_installed(dep_not_installed, handler.watcher, self.i18n)
                    return False

        return True

    def _install(self, pkgname: str, maintainer: str, root_password: str, repository: str, handler: ProcessHandler, install_file: str = None, pkgdir: str = '.', change_progress: bool = True):
        check_install_output = []
        pkgpath = install_file if install_file else pkgname

        handler.watcher.change_substatus(self.i18n['arch.checking.conflicts'].format(bold(pkgname)))

        for check_out in SimpleProcess(['pacman', '-U' if install_file else '-S', pkgpath], root_password=root_password, cwd=pkgdir).instance.stdout:
            check_install_output.append(check_out.decode())

        self._update_progress(handler.watcher, 70, change_progress)
        if check_install_output and 'conflict' in check_install_output[-1]:
            conflicting_apps = [w[0] for w in re.findall(r'((\w|\-|\.)+)\s(and|are)', check_install_output[-1])]
            conflict_msg = ' {} '.format(self.i18n['and']).join([bold(c) for c in conflicting_apps])
            if not handler.watcher.request_confirmation(title=self.i18n['arch.install.conflict.popup.title'],
                                                        body=self.i18n['arch.install.conflict.popup.body'].format(conflict_msg)):
                handler.watcher.print(self.i18n['action.cancelled'])
                return False
            else:  # uninstall conflicts
                self._update_progress(handler.watcher, 75, change_progress)
                to_uninstall = [conflict for conflict in conflicting_apps if conflict != pkgname]

                for conflict in to_uninstall:
                    handler.watcher.change_substatus(self.i18n['arch.uninstalling.conflict'].format(bold(conflict)))

                    if not self._uninstall(pkg_name=conflict, root_password=root_password, handler=handler):
                        handler.watcher.show_message(title=self.i18n['error'],
                                                     body=self.i18n['arch.uninstalling.conflict.fail'].format(bold(conflict)),
                                                     type_=MessageType.ERROR)
                        return False

        handler.watcher.change_substatus(self.i18n['arch.installing.package'].format(bold(pkgname)))
        self._update_progress(handler.watcher, 80, change_progress)
        installed = handler.handle(pacman.install_as_process(pkgpath=pkgpath, root_password=root_password, file=install_file is not None, pkgdir=pkgdir))
        self._update_progress(handler.watcher, 95, change_progress)

        if installed and self.context.disk_cache:
            handler.watcher.change_substatus(self.i18n['status.caching_data'].format(bold(pkgname)))
            if self.context.disk_cache:
                disk.save_several(pkgnames={pkgname}, repo_map={pkgname: repository}, maintainer=maintainer, overwrite=True, categories=self.categories)

            self._update_progress(handler.watcher, 100, change_progress)

        return installed

    def _update_progress(self, watcher: ProcessWatcher, val: int, change_progress: bool):
        if change_progress:
            watcher.change_progress(val)

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

    def _install_from_aur(self, pkgname: str, pkgbase: str, maintainer: str, root_password: str, handler: ProcessHandler, dependency: bool, skip_optdeps: bool = False, change_progress: bool = True) -> bool:
        self._optimize_makepkg(watcher=handler.watcher)

        app_build_dir = '{}/build_{}'.format(BUILD_DIR, int(time.time()))

        try:
            if not os.path.exists(app_build_dir):
                build_dir = handler.handle(SystemProcess(new_subprocess(['mkdir', '-p', app_build_dir])))
                self._update_progress(handler.watcher, 10, change_progress)

                if build_dir:
                    base_name = pkgbase if pkgbase else pkgname
                    file_url = URL_PKG_DOWNLOAD.format(base_name)
                    file_name = file_url.split('/')[-1]
                    handler.watcher.change_substatus('{} {}'.format(self.i18n['arch.downloading.package'], bold(file_name)))
                    download = handler.handle(SystemProcess(new_subprocess(['wget', file_url], cwd=app_build_dir), check_error_output=False))

                    if download:
                        self._update_progress(handler.watcher, 30, change_progress)
                        handler.watcher.change_substatus('{} {}'.format(self.i18n['arch.uncompressing.package'], bold(base_name)))
                        uncompress = handler.handle(SystemProcess(new_subprocess(['tar', 'xvzf', '{}.tar.gz'.format(base_name)], cwd=app_build_dir)))
                        self._update_progress(handler.watcher, 40, change_progress)

                        if uncompress:
                            uncompress_dir = '{}/{}'.format(app_build_dir, base_name)
                            return self._build(pkgname=pkgname,
                                               base_name=base_name,
                                               maintainer=maintainer,
                                               root_password=root_password,
                                               handler=handler,
                                               build_dir=app_build_dir,
                                               project_dir=uncompress_dir,
                                               dependency=dependency,
                                               skip_optdeps=skip_optdeps,
                                               change_progress=change_progress)
        finally:
            if os.path.exists(app_build_dir):
                handler.handle(SystemProcess(new_subprocess(['rm', '-rf', app_build_dir])))

        return False

    def _sync_databases(self, root_password: str, handler: ProcessHandler):
        if database.should_sync(self.local_config, handler, self.logger):
            handler.watcher.change_substatus(self.i18n['arch.sync_databases.substatus'])
            synced, output = handler.handle_simple(pacman.sync_databases(root_password=root_password,
                                                                         force=True))
            if synced:
                database.register_sync(self.logger)
            else:
                self.logger.warning("It was not possible to synchronized the package databases")
                handler.watcher.change_substatus(self.i18n['arch.sync_databases.substatus.error'])

    def _optimize_makepkg(self, watcher: ProcessWatcher):
        if self.local_config['optimize'] and not os.path.exists(CUSTOM_MAKEPKG_FILE):
            watcher.change_substatus(self.i18n['arch.makepkg.optimizing'])
            ArchCompilationOptimizer(self.local_config, self.i18n, self.context.logger).optimize()

    def install(self, pkg: ArchPackage, root_password: str, watcher: ProcessWatcher, skip_optdeps: bool = False) -> bool:
        if not self._check_action_allowed(pkg, watcher):
            return False

        clean_config = False

        if not self.local_config:
            self.local_config = read_config()
            clean_config = True

        handler = ProcessHandler(watcher)

        self._sync_databases(root_password=root_password, handler=handler)

        if pkg.repository == 'aur':
            res = self._install_from_aur(pkg.name, pkg.package_base, pkg.maintainer, root_password, handler, dependency=False, skip_optdeps=skip_optdeps)
        else:
            res = self._install(pkgname=pkg.name, maintainer=pkg.repository, root_password=root_password, handler=handler, install_file=None, repository=pkg.repository, change_progress=False)

        if res:
            if os.path.exists(pkg.get_disk_data_path()):
                with open(pkg.get_disk_data_path()) as f:
                    data = f.read()
                    if data:
                        data = json.loads(data)
                        pkg.fill_cached_data(data)

        if clean_config:
            self.local_config = None

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
            return self.arch_distro and pacman.is_enabled() and self._is_wget_available()
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

            return database.should_sync(arch_config, None, self.logger)

        return action != 'search'

    def _start_category_task(self, task_man: TaskManager):
        task_man.register_task('arch_aur_cats', self.i18n['task.download_categories'].format('AUR'), get_icon_path())
        task_man.update_progress('arch_aur_cats', 50, None)

    def _finish_category_task(self, task_man: TaskManager):
        task_man.update_progress('arch_aur_cats', 100, None)
        task_man.finish_task('arch_aur_cats')

    def prepare(self, task_manager: TaskManager, root_password: str):
        arch_config = read_config(update_file=True)

        if arch_config['aur'] or arch_config['repositories']:
            ArchDiskCacheUpdater(task_manager, arch_config, self.i18n, self.context.logger).start()

        if arch_config['aur']:
            ArchCompilationOptimizer(arch_config, self.i18n, self.context.logger, task_manager).start()

        if arch_config['aur']:
            CategoriesDownloader(id_='AUR', http_client=self.context.http_client, logger=self.context.logger,
                                 manager=self, url_categories_file=URL_CATEGORIES_FILE, disk_cache_dir=CATEGORIES_CACHE_DIR,
                                 categories_path=CATEGORIES_FILE_PATH,
                                 before=lambda: self._start_category_task(task_manager),
                                 after=lambda: self._finish_category_task(task_manager)).start()
            self.index_aur = AURIndexUpdater(self.context)
            self.index_aur.start()

        refresh_mirrors = None
        if arch_config['repositories'] and arch_config['refresh_mirrors_startup'] and mirrors.should_sync(self.logger):
            refresh_mirrors = RefreshMirrors(taskman=task_manager, i18n=self.i18n,
                                             root_password=root_password, logger=self.logger)
            refresh_mirrors.start()

        if refresh_mirrors or database.should_sync(arch_config, None, self.logger):
            SyncDatabases(taskman=task_manager, root_password=root_password, i18n=self.i18n,
                          logger=self.logger, refresh_mirrors=refresh_mirrors).start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        installed = self.read_installed(disk_loader=None, internet_available=internet_available).installed
        return [PackageUpdate(p.name, p.latest_version, self.i18n['gem.arch.type.{}.label'.format(p.get_type())]) for p in installed if p.update]

    def list_warnings(self, internet_available: bool) -> List[str]:
        warnings = []

        if self.arch_distro:
            if not pacman.is_enabled():
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
            subprocess.Popen(pkg.command.split(' '))

    def get_screenshots(self, pkg: SoftwarePackage) -> List[str]:
        pass

    def _gen_bool_selector(self, id_: str, label_key: str, tooltip_key: str, value: bool, max_width: int) -> SingleSelectComponent:
        opts = [InputOption(label=self.i18n['yes'].capitalize(), value=True),
                InputOption(label=self.i18n['no'].capitalize(), value=False)]

        return SingleSelectComponent(label=self.i18n[label_key].capitalize(),
                                     options=opts,
                                     default_option=[o for o in opts if o.value == value][0],
                                     max_per_line=len(opts),
                                     type_=SelectViewType.RADIO,
                                     tooltip=self.i18n[tooltip_key],
                                     max_width=max_width,
                                     id_=id_)

    def get_settings(self, screen_width: int, screen_height: int) -> ViewComponent:
        local_config = read_config()
        max_width = floor(screen_width * 0.15)

        fields = [
            self._gen_bool_selector(id_='repos',
                                    label_key='arch.config.repos',
                                    tooltip_key='arch.config.repos.tip',
                                    value=bool(local_config['repositories']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='aur',
                                    label_key='arch.config.aur',
                                    tooltip_key='arch.config.aur.tip',
                                    value=bool(local_config['aur']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='opts',
                                    label_key='arch.config.optimize',
                                    tooltip_key='arch.config.optimize.tip',
                                    value=bool(local_config['optimize']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='simple_dep_check',
                                    label_key='arch.config.simple_dep_check',
                                    tooltip_key='arch.config.simple_dep_check.tip',
                                    value=bool(local_config['simple_checking']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='trans_dep_check',
                                    label_key='arch.config.trans_dep_check',
                                    tooltip_key='arch.config.trans_dep_check.tip',
                                    value=bool(local_config['transitive_checking']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='sync_dbs',
                                    label_key='arch.config.sync_dbs',
                                    tooltip_key='arch.config.sync_dbs.tip',
                                    value=bool(local_config['sync_databases']),
                                    max_width=max_width),
            self._gen_bool_selector(id_='clean_cached',
                                    label_key='arch.config.clean_cache',
                                    tooltip_key='arch.config.clean_cache.tip',
                                    value=bool(local_config['clean_cached']),
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
                               value=local_config['mirrors_sort_limit'] if isinstance(local_config['mirrors_sort_limit'], int) else '')
        ]

        return PanelComponent([FormComponent(fields, spaces=False)])

    def save_settings(self, component: PanelComponent) -> Tuple[bool, List[str]]:
        config = read_config()

        form_install = component.components[0]
        config['repositories'] = form_install.get_component('repos').get_selected()
        config['aur'] = form_install.get_component('aur').get_selected()
        config['optimize'] = form_install.get_component('opts').get_selected()
        config['transitive_checking'] = form_install.get_component('trans_dep_check').get_selected()
        config['sync_databases'] = form_install.get_component('sync_dbs').get_selected()
        config['simple_checking'] = form_install.get_component('simple_dep_check').get_selected()
        config['clean_cached'] = form_install.get_component('clean_cached').get_selected()
        config['refresh_mirrors_startup'] = form_install.get_component('ref_mirs').get_selected()
        config['mirrors_sort_limit'] = form_install.get_component('mirrors_sort_limit').get_int_value()

        try:
            save_config(config, CONFIG_FILE)
            return True, None
        except:
            return False, [traceback.format_exc()]

    def _fill_repo_pkgs_sort_data(self, pkgs: List[ArchPackage], pkg_deps: Dict[ArchPackage, Set[str]], names_map: Dict[str, ArchPackage]):
        sorting_data = pacman.map_sorting_data([p.name for p in pkgs])

        for p in pkgs:
            data = sorting_data.get(p)

            if data:
                for name in data['provides']:
                    names_map[name] = p

                pkg_deps[p] = data['depends']
            else:
                names_map[p.name] = p
                pkg_deps[p] = None
                self.logger.warning("Could not retrieve the sorting data for package '{}'".format(p))

    def sort_update_order(self, pkgs: List[ArchPackage]) -> List[ArchPackage]:
        aur_pkgs, repo_pkgs = [], []

        for p in pkgs:
            if p.repository == 'aur':
                aur_pkgs.append(p)
            else:
                repo_pkgs.append(p)

        pkg_deps = {}  # maps the package instance and a set with all its dependencies
        names_map = {}  # maps all the package provided names to the package instance

        def _add_info(pkg: ArchPackage):
            try:
                srcinfo = self.aur_client.get_src_info(pkg.name)

                names_map[pkg.name] = pkg
                names = srcinfo.get('pkgname')

                if isinstance(names, list):
                    for n in names:
                        names_map[n] = pkg

                pkg_deps[pkg] = self.aur_client.extract_required_dependencies(srcinfo)
            except:
                pkg_deps[pkg] = None
                self.logger.warning("Could not retrieve dependencies for '{}'".format(pkg.name))
                traceback.print_exc()

        threads = []

        t = Thread(target=self._fill_repo_pkgs_sort_data(repo_pkgs, pkg_deps, names_map))
        for pkg in aur_pkgs:
            t = Thread(target=_add_info, args=(pkg, ), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return self._sort_deps(pkg_deps, names_map)

    @classmethod
    def _sort_deps(cls, pkg_deps: Dict[ArchPackage, Set[str]], names_map: Dict[str, ArchPackage]) -> List[ArchPackage]:
        sorted_names, not_sorted = {}, {}
        pkg_map = {}

        # first adding all with no deps:
        for pkg, deps in pkg_deps.items():
            if not deps:
                sorted_names[pkg.name] = len(sorted_names)
            else:
                not_sorted[pkg.name] = pkg

            pkg_map[pkg.name] = pkg

        # now adding all that depends on another:
        for name, pkg in not_sorted.items():
            cls._add_to_sort(pkg, pkg_deps, sorted_names, not_sorted, names_map)

        position_map = {'{}-{}'.format(i, n): pkg_map[n] for n, i in sorted_names.items()}
        return [position_map[idx] for idx in sorted(position_map)]

    @classmethod
    def _add_to_sort(cls, pkg: ArchPackage, pkg_deps: Dict[ArchPackage, Set[str]],  sorted_names: Dict[str, int], not_sorted: Dict[str, ArchPackage], names_map: Dict[str, ArchPackage]) -> int:
        idx = sorted_names.get(pkg.name)

        if idx is not None:
            return idx
        else:
            idx = len(sorted_names)
            sorted_names[pkg.name] = idx

            for dep in pkg_deps[pkg]:
                dep_idx = sorted_names.get(dep)

                if dep_idx is not None:
                    idx = dep_idx + 1
                else:
                    dep_pkg = names_map.get(dep)

                    if dep_pkg:  # it means the declared dep is mapped differently from the provided packages to update
                        dep_idx = sorted_names.get(dep_pkg.name)

                        if dep_idx is not None:
                            idx = dep_idx + 1
                        else:
                            dep_idx = cls._add_to_sort(dep_pkg, pkg_deps, sorted_names, not_sorted, names_map)
                            idx = dep_idx + 1

                    elif dep in not_sorted:  # it means the dep is one of the packages to sort, but it not sorted yet
                        dep_idx = cls._add_to_sort(not_sorted[dep], pkg_deps, sorted_names, not_sorted, names_map)
                        idx = dep_idx + 1

                sorted_names[pkg.name] = idx

            return sorted_names[pkg.name]

    def _map_and_add_package(self, pkg_data: Tuple[str, str], idx: int, output: dict):
        version = None

        if pkg_data[1] == 'aur':
            try:
                info = self.aur_client.get_src_info(pkg_data[0])

                if info:
                    version = info.get('pkgver')

                    if not version:
                        self.logger.warning("No version declared in SRCINFO of '{}'".format(pkg_data[0]))
                else:
                    self.logger.warning("Could not retrieve the SRCINFO for '{}'".format(pkg_data[0]))
            except:
                self.logger.warning("Could not retrieve the SRCINFO for '{}'".format(pkg_data[0]))
        else:
            version = pacman.get_version_for_not_installed(pkg_data[0])

        output[idx] = ArchPackage(name=pkg_data[0], version=version, latest_version=version, repository=pkg_data[1], i18n=self.i18n)

    def get_update_requirements(self, pkgs: List[ArchPackage], watcher: ProcessWatcher) -> List[ArchPackage]:
        deps = self._map_known_missing_deps({p.get_base_name(): p.repository for p in pkgs}, watcher)

        if deps:  # filtering selected packages
            selected_names = {p.name for p in pkgs}
            deps = [dep for dep in deps if dep[0] not in selected_names]

        if deps:
            map_threads, sorted_pkgs = [], {}

            for idx, dep in enumerate(deps):
                t = Thread(target=self._map_and_add_package, args=(dep, idx, sorted_pkgs), daemon=True)
                t.start()
                map_threads.append(t)

            for t in map_threads:
                t.join()

            return [sorted_pkgs[idx] for idx in sorted(sorted_pkgs)]
        else:
            return []

    def get_custom_actions(self) -> List[CustomSoftwareAction]:
        return self.custom_actions
