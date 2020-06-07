import logging
import time
from threading import Thread
from typing import Dict, Set, List, Tuple, Iterable

from bauh.api.abstract.controller import UpgradeRequirements, UpgradeRequirement
from bauh.api.abstract.handler import ProcessWatcher
from bauh.gems.arch import pacman, sorting
from bauh.gems.arch.aur import AURClient
from bauh.gems.arch.dependencies import DependenciesAnalyser
from bauh.gems.arch.exceptions import PackageNotFoundException
from bauh.gems.arch.model import ArchPackage
from bauh.view.util.translation import I18n


class UpdateRequirementsContext:

    def __init__(self, to_update: Dict[str, ArchPackage], repo_to_update: Dict[str, ArchPackage],
                 aur_to_update: Dict[str, ArchPackage], repo_to_install: Dict[str, ArchPackage],
                 aur_to_install: Dict[str, ArchPackage], to_install: Dict[str, ArchPackage],
                 pkgs_data: Dict[str, dict], cannot_upgrade: Dict[str, UpgradeRequirement],
                 to_remove: Dict[str, UpgradeRequirement], installed_names: Set[str], provided_map: Dict[str, Set[str]],
                 aur_index: Set[str], arch_config: dict, remote_provided_map: Dict[str, Set[str]], remote_repo_map: Dict[str, str],
                 root_password: str):
        self.to_update = to_update
        self.repo_to_update = repo_to_update
        self.aur_to_update = aur_to_update
        self.repo_to_install = repo_to_install
        self.aur_to_install = aur_to_install
        self.pkgs_data = pkgs_data
        self.cannot_upgrade = cannot_upgrade
        self.root_password = root_password
        self.installed_names = installed_names
        self.provided_map = provided_map
        self.to_remove = to_remove
        self.to_install = to_install
        self.aur_index = aur_index
        self.arch_config = arch_config
        self.remote_provided_map = remote_provided_map
        self.remote_repo_map = remote_repo_map


class UpdatesSummarizer:

    def __init__(self, aur_client: AURClient, i18n: I18n, logger: logging.Logger, deps_analyser: DependenciesAnalyser, watcher: ProcessWatcher):
        self.aur_client = aur_client
        self.i18n = i18n
        self.logger = logger
        self.watcher = watcher
        self.deps_analyser = deps_analyser

    def _fill_aur_pkg_update_data(self, pkg: ArchPackage, output: dict):
        output[pkg.name] = self.aur_client.map_update_data(pkg.get_base_name(), pkg.latest_version)

    def _handle_conflict_both_to_install(self, pkg1: str, pkg2: str, context: UpdateRequirementsContext):
        for src_pkg in {p for p, data in context.pkgs_data.items() if
                        data['d'] and pkg1 in data['d'] or pkg2 in data['d']}:
            if src_pkg not in context.cannot_upgrade:
                reason = self.i18n['arch.update_summary.to_install.dep_conflict'].format("'{}'".format(pkg1),
                                                                                         "'{}'".format(pkg2))
                context.cannot_upgrade[src_pkg] = UpgradeRequirement(context.to_update[src_pkg], reason)

            del context.to_update[src_pkg]

            if src_pkg in context.repo_to_update:
                del context.repo_to_update[src_pkg]
            else:
                del context.aur_to_update[src_pkg]

            del context.pkgs_data[src_pkg]

        for p in (pkg1, pkg2):
            if p in context.to_install:
                del context.to_install[p]

                if p in context.repo_to_install:
                    del context.repo_to_install[p]
                else:
                    del context.aur_to_install[p]

    def _handle_conflict_to_update_and_to_install(self, pkg1: str, pkg2: str, pkg1_to_install: bool, context: UpdateRequirementsContext):
        to_install, to_update = (pkg1, pkg2) if pkg1_to_install else (pkg2, pkg1)
        to_install_srcs = {p for p, data in context.pkgs_data.items() if data['d'] and to_install in data['d']}

        if to_update not in context.cannot_upgrade:
            srcs_str = ', '.join(("'{}'".format(p) for p in to_install_srcs))
            reason = self.i18n['arch.update_summary.to_update.conflicts_dep'].format("'{}'".format(to_install),
                                                                                     srcs_str)
            context.cannot_upgrade[to_install] = UpgradeRequirement(context.to_update[to_update], reason)

        if to_update in context.to_update:
            del context.to_update[to_update]

        for src_pkg in to_install_srcs:
            src_to_install = src_pkg in context.to_install
            pkg = context.to_install[src_pkg] if src_to_install else context.to_update[src_pkg]
            if src_pkg not in context.cannot_upgrade:
                reason = self.i18n['arch.update_summary.to_update.dep_conflicts'].format("'{}'".format(to_install),
                                                                                         "'{}'".format(to_update))
                context.cannot_upgrade[src_pkg] = UpgradeRequirement(pkg, reason)

            if src_to_install:
                del context.to_install[src_pkg]

                if src_pkg in context.repo_to_install:
                    del context.repo_to_install[src_pkg]
                else:
                    del context.aur_to_install[src_pkg]
            else:
                del context.to_update[src_pkg]

                if src_pkg in context.repo_to_update:
                    del context.repo_to_update[src_pkg]
                else:
                    del context.aur_to_update[src_pkg]

            del context.pkgs_data[src_pkg]

        if to_install in context.to_install:
            del context.to_install[to_install]

    def _handle_conflict_both_to_update(self, pkg1: str, pkg2: str, context: UpdateRequirementsContext):
        if pkg1 not in context.cannot_upgrade:
            reason = "{} '{}'".format(self.i18n['arch.info.conflicts with'].capitalize(), pkg2)
            context.cannot_upgrade[pkg1] = UpgradeRequirement(pkg=context.to_update[pkg1], reason=reason)

        if pkg2 not in context.cannot_upgrade:
            reason = "{} '{}'".format(self.i18n['arch.info.conflicts with'].capitalize(), pkg1)
            context.cannot_upgrade[pkg2] = UpgradeRequirement(pkg=context.to_update[pkg2], reason=reason)

        for p in (pkg1, pkg2):
            if p in context.to_update:
                del context.to_update[p]

                if p in context.repo_to_update:
                    del context.repo_to_update[p]
                else:
                    del context.aur_to_update[p]

    def _filter_and_map_conflicts(self, context: UpdateRequirementsContext) -> Dict[str, str]:
        root_conflict = {}
        mutual_conflicts = {}

        for p, data in context.pkgs_data.items():
            if data['c']:
                for c in data['c']:
                    if c and c in context.installed_names:
                        # source = provided_map[c]
                        root_conflict[c] = p

                        if (p, c) in root_conflict.items():
                            mutual_conflicts[c] = p

        if mutual_conflicts:
            for pkg1, pkg2 in mutual_conflicts.items():
                pkg1_to_install = pkg1 in context.to_install
                pkg2_to_install = pkg2 in context.to_install

                if pkg1_to_install and pkg2_to_install:  # remove both from to install and mark their source packages as 'cannot_update'
                    self._handle_conflict_both_to_install(pkg1, pkg2, context)
                elif (pkg1_to_install and not pkg2_to_install) or (not pkg1_to_install and pkg2_to_install):
                    self._handle_conflict_to_update_and_to_install(pkg1, pkg2, pkg1_to_install, context)
                else:
                    self._handle_conflict_both_to_update(pkg1, pkg2, context)  # adding both to the 'cannot update' list

            for pkg1, pkg2 in mutual_conflicts.items():  # removing conflicting packages from the packages selected to upgrade
                for p in (pkg1, pkg2):
                    if p in context.pkgs_data:
                        if context.pkgs_data[p].get('c'):
                            for c in context.pkgs_data[p]['c']:
                                # source = provided_map[c]
                                if c in root_conflict:
                                    del root_conflict[c]

                        del context.pkgs_data[p]

        return root_conflict

    def _fill_conflicts(self, context: UpdateRequirementsContext, blacklist: Iterable[str] = None):
        self.logger.info("Checking conflicts")

        root_conflict = self._filter_and_map_conflicts(context)

        sub_conflict = pacman.get_dependencies_to_remove(root_conflict.keys(), context.root_password) if root_conflict else None

        to_remove_map = {}
        if sub_conflict:
            for dep, source in sub_conflict.items():
                if dep not in to_remove_map and (not blacklist or dep not in blacklist):
                    req = ArchPackage(name=dep, installed=True, i18n=self.i18n)
                    to_remove_map[dep] = req
                    reason = "{} '{}'".format(self.i18n['arch.info.depends on'].capitalize(), source)
                    context.to_remove[dep] = UpgradeRequirement(req, reason)

        if root_conflict:
            for dep, source in root_conflict.items():
                if dep not in to_remove_map and (not blacklist or dep not in blacklist):
                    req = ArchPackage(name=dep, installed=True, i18n=self.i18n)
                    to_remove_map[dep] = req
                    reason = "{} '{}'".format(self.i18n['arch.info.conflicts with'].capitalize(), source)
                    context.to_remove[dep] = UpgradeRequirement(req, reason)

        if to_remove_map:
            for name in to_remove_map.keys():  # upgrading lists
                if name in context.pkgs_data:
                    del context.pkgs_data[name]

                if name in context.aur_to_update:
                    del context.aur_to_update[name]

                if name in context.repo_to_update:
                    del context.repo_to_update[name]

            removed_size = pacman.get_installed_size([*to_remove_map.keys()])

            if removed_size:
                for name, size in removed_size.items():
                    if size is not None:
                        req = context.to_remove.get(name)
                        if req:
                            req.extra_size = size

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

    def _fill_to_install(self, context: UpdateRequirementsContext) -> bool:
        ti = time.time()
        self.logger.info("Discovering updates missing packages")
        deps_data, deps_checked = {}, set()
        deps = self.deps_analyser.map_missing_deps(pkgs_data=context.pkgs_data,
                                                   provided_map=context.provided_map,
                                                   aur_index=context.aur_index,
                                                   deps_checked=deps_checked,
                                                   sort=True,
                                                   deps_data=deps_data,
                                                   remote_provided_map=context.remote_provided_map,
                                                   remote_repo_map=context.remote_repo_map,
                                                   watcher=self.watcher,
                                                   automatch_providers=context.arch_config['automatch_providers'])

        if deps is None:
            tf = time.time()
            self.logger.info("It took {0:.2f} seconds to retrieve required upgrade packages".format(tf - ti))
            return False  # the user called the process off

        if deps:  # filtering selected packages
            selected_names = {p for p in context.to_update}
            deps = [dep for dep in deps if dep[0] not in selected_names]

            if deps:
                sorted_pkgs = {}
                aur_to_install_data = {}
                all_to_install_data = {}

                for idx, dep in enumerate(deps):
                    data = deps_data[dep[0]]
                    pkg = ArchPackage(name=dep[0], version=data['v'], latest_version=data['v'], repository=dep[1], i18n=self.i18n)
                    sorted_pkgs[idx] = pkg
                    context.to_install[dep[0]] = pkg

                    if pkg.repository == 'aur':
                        context.aur_to_install[pkg.name] = pkg
                        aur_to_install_data[pkg.name] = data
                    else:
                        context.repo_to_install[pkg.name] = pkg

                if context.repo_to_install:
                    all_to_install_data.update(pacman.map_updates_data(context.repo_to_install.keys()))

                if aur_to_install_data:
                    all_to_install_data.update(aur_to_install_data)

                if all_to_install_data:
                    context.pkgs_data.update(all_to_install_data)
                    self._fill_conflicts(context, context.to_remove.keys())

        tf = time.time()
        self.logger.info("It took {0:.2f} seconds to retrieve required upgrade packages".format(tf - ti))
        return True

    def __fill_provided_map(self, context: UpdateRequirementsContext):
        ti = time.time()
        self.logger.info("Filling provided names")
        context.installed_names = pacman.list_installed_names()
        installed_to_ignore = set()

        for pkgname in context.to_update:
            pacman.fill_provided_map(pkgname, pkgname, context.provided_map)
            installed_to_ignore.add(pkgname)

            pdata = context.pkgs_data.get(pkgname)
            if pdata and pdata['p']:
                pacman.fill_provided_map('{}={}'.format(pkgname, pdata['v']), pkgname, context.provided_map)
                for p in pdata['p']:
                    pacman.fill_provided_map(p, pkgname, context.provided_map)
                    split_provided = p.split('=')

                    if len(split_provided) > 1 and split_provided[0] != p:
                        pacman.fill_provided_map(split_provided[0], pkgname, context.provided_map)

        if installed_to_ignore:  # filling the provided names of the installed
            installed_to_query = context.installed_names.difference(installed_to_ignore)

            if installed_to_query:
                context.provided_map.update(pacman.map_provided(remote=False, pkgs=installed_to_query))

        tf = time.time()
        self.logger.info("Filling provided names took {0:.2f} seconds".format(tf - ti))

    def __fill_aur_index(self, context: UpdateRequirementsContext):
        if context.arch_config['aur']:
            self.logger.info("Loading AUR index")
            names = self.aur_client.read_index()

            if names:
                context.aur_index.update(names)
                self.logger.info("AUR index loaded on the context")

    def _map_requirement(self, pkg: ArchPackage, context: UpdateRequirementsContext, installed_sizes: Dict[str, int] = None) -> UpgradeRequirement:
        requirement = UpgradeRequirement(pkg)

        if pkg.repository != 'aur':
            data = context.pkgs_data[pkg.name]
            requirement.required_size = data['ds']
            requirement.extra_size = data['s']
    
            current_size = installed_sizes.get(pkg.name) if installed_sizes else None

            if current_size is not None and data['s']:
                requirement.extra_size = data['s'] - current_size

        return requirement

    def summarize(self, pkgs: List[ArchPackage], root_password: str, arch_config: dict) -> UpgradeRequirements:
        res = UpgradeRequirements([], [], [], [])

        remote_provided_map = pacman.map_provided(remote=True)
        remote_repo_map = pacman.map_repositories()
        context = UpdateRequirementsContext(to_update={}, repo_to_update={}, aur_to_update={}, repo_to_install={},
                                            aur_to_install={}, to_install={}, pkgs_data={}, cannot_upgrade={},
                                            to_remove={}, installed_names=set(), provided_map={}, aur_index=set(),
                                            arch_config=arch_config, root_password=root_password,
                                            remote_provided_map=remote_provided_map, remote_repo_map=remote_repo_map)
        self.__fill_aur_index(context)

        aur_data = {}
        aur_srcinfo_threads = []
        for p in pkgs:
            context.to_update[p.name] = p
            if p.repository == 'aur':
                context.aur_to_update[p.name] = p
                t = Thread(target=self._fill_aur_pkg_update_data, args=(p, aur_data), daemon=True)
                t.start()
                aur_srcinfo_threads.append(t)
            else:
                context.repo_to_update[p.name] = p

        if context.aur_to_update:
            for t in aur_srcinfo_threads:
                t.join()

        self.logger.info("Filling updates data")

        if context.repo_to_update:
            context.pkgs_data.update(pacman.map_updates_data(context.repo_to_update.keys()))

        if aur_data:
            context.pkgs_data.update(aur_data)

        self.__fill_provided_map(context)

        if context.pkgs_data:
            self._fill_conflicts(context)

        try:
            if not self._fill_to_install(context):
                self.logger.info("The operation was cancelled by the user")
                return
        except PackageNotFoundException as e:
            self.logger.error("Package '{}' not found".format(e.name))
            return

        if context.to_update:
            installed_sizes = pacman.get_installed_size(list(context.to_update.keys()))

            sorted_pkgs = []

            if context.repo_to_update:  # only sorting by name ( pacman already knows the best order to perform the upgrade )
                sorted_pkgs.extend(context.repo_to_update.values())
                sorted_pkgs.sort(key=lambda pkg: pkg.name)

            if context.aur_to_update:  # adding AUR packages in the end
                sorted_aur = sorting.sort(context.aur_to_update.keys(), context.pkgs_data, context.provided_map)

                for aur_pkg in sorted_aur:
                    sorted_pkgs.append(context.aur_to_update[aur_pkg[0]])

            res.to_upgrade = [self._map_requirement(pkg, context, installed_sizes) for pkg in sorted_pkgs]

        if context.to_remove:
            res.to_remove = [p for p in context.to_remove.values()]

        if context.cannot_upgrade:
            res.cannot_upgrade = [d for d in context.cannot_upgrade.values()]

        if context.to_install:
            res.to_install = [self._map_requirement(p, context) for p in context.to_install.values()]

        return res
