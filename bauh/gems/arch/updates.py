import logging
import time
import traceback
from threading import Thread
from typing import Dict, Set, List, Tuple, Iterable, Optional

from pkg_resources import parse_version

from bauh.api.abstract.controller import UpgradeRequirements, UpgradeRequirement
from bauh.api.abstract.handler import ProcessWatcher
from bauh.gems.arch import pacman, sorting
from bauh.gems.arch.aur import AURClient
from bauh.gems.arch.dependencies import DependenciesAnalyser
from bauh.gems.arch.exceptions import PackageNotFoundException
from bauh.gems.arch.model import ArchPackage
from bauh.gems.arch.pacman import RE_DEP_OPERATORS
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
                    if c and c != p and c in context.installed_names:
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

        if root_conflict:
            for dep, source in root_conflict.items():
                if dep not in context.to_remove and (not blacklist or dep not in blacklist):
                    req = ArchPackage(name=dep, installed=True, i18n=self.i18n)
                    reason = "{} '{}'".format(self.i18n['arch.info.conflicts with'].capitalize(), source)
                    context.to_remove[dep] = UpgradeRequirement(req, reason)

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
                    pkg = ArchPackage(name=dep[0], version=data['v'], latest_version=data['v'], repository=dep[1], i18n=self.i18n, package_base=data.get('b', dep[0]))
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

        if context.to_install:
            self.__fill_provided_map(context=context, pkgs=context.to_install, fill_installed=False)

        tf = time.time()
        self.logger.info("It took {0:.2f} seconds to retrieve required upgrade packages".format(tf - ti))
        return True

    def __fill_provided_map(self, context: UpdateRequirementsContext, pkgs: Dict[str, ArchPackage], fill_installed: bool = True):
        if pkgs:
            ti = time.time()
            self.logger.info("Filling provided names")

            if not context.installed_names:
                context.installed_names = pacman.list_installed_names()

            installed_to_ignore = set()

            for pkgname in pkgs:
                pacman.fill_provided_map(pkgname, pkgname, context.provided_map)

                if fill_installed:
                    installed_to_ignore.add(pkgname)

                pdata = context.pkgs_data.get(pkgname)
                if pdata and pdata['p']:
                    pacman.fill_provided_map('{}={}'.format(pkgname, pdata['v']), pkgname, context.provided_map)

                    ver_split = pdata['v'].split('-')

                    if len(ver_split) > 1:
                        pacman.fill_provided_map('{}={}'.format(pkgname, '-'.join(ver_split[0:-1])), pkgname, context.provided_map)

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

    def _map_requirement(self, pkg: ArchPackage, context: UpdateRequirementsContext, installed_sizes: Dict[str, int] = None, to_install: bool = False, to_sync: Set[str] = None) -> UpgradeRequirement:
        requirement = UpgradeRequirement(pkg)

        if pkg.repository != 'aur':
            data = context.pkgs_data[pkg.name]
            requirement.required_size = data['ds']
            requirement.extra_size = data['s']
    
            current_size = installed_sizes.get(pkg.name) if installed_sizes else None

            if current_size is not None and data['s']:
                requirement.extra_size = data['s'] - current_size

            required_by = set()

            if to_install and to_sync and context.pkgs_data:
                names = context.pkgs_data[pkg.name].get('p', {pkg.name})
                to_sync_deps_cache = {}
                for p in to_sync:
                    if p != pkg.name and p in context.pkgs_data:
                        deps = to_sync_deps_cache.get(p)

                        if deps is None:
                            deps = context.pkgs_data[p]['d']

                            if deps is None:
                                deps = set()
                            else:
                                deps = {RE_DEP_OPERATORS.split(d)[0] for d in deps}

                            to_sync_deps_cache[p] = deps

                        if deps:
                            for n in names:
                                if n in deps:
                                    required_by.add(p)
                                    break

                requirement.reason = '{}: {}'.format(self.i18n['arch.info.required by'].capitalize(), ','.join(required_by) if required_by else '?')

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

        self.__fill_provided_map(context=context, pkgs=context.to_update)

        if context.pkgs_data:
            self._fill_conflicts(context)

        try:
            if not self._fill_to_install(context):
                self.logger.info("The operation was cancelled by the user")
                return
        except PackageNotFoundException as e:
            self.logger.error("Package '{}' not found".format(e.name))
            return

        if context.pkgs_data:
            self._fill_dependency_breakage(context)

        self.__update_context_based_on_to_remove(context)

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
            to_sync = {r.pkg.name for r in res.to_upgrade} if res.to_upgrade else {}
            to_sync.update(context.to_install.keys())
            res.to_install = [self._map_requirement(p, context, to_install=True, to_sync=to_sync) for p in context.to_install.values()]

        res.context['data'] = context.pkgs_data
        return res

    def __update_context_based_on_to_remove(self, context: UpdateRequirementsContext):
        if context.to_remove:
            to_remove_provided = {}
            # filtering all package to synchronization from the transaction context
            to_sync = {*(context.to_update.keys() if context.to_update else set()), *(context.to_install.keys() if context.to_install else set())}
            if to_sync:  # checking if any packages to sync on the context rely on the 'to remove' ones
                to_remove_provided.update(pacman.map_provided(remote=False, pkgs=context.to_remove.keys()))
                to_remove_from_sync = {}  # will store all packages that should be removed

                for pname in to_sync:
                    if pname in context.pkgs_data:
                        deps = context.pkgs_data[pname].get('d')

                        if deps:
                            required = set()

                            for pkg in context.to_remove:
                                for provided in to_remove_provided[pkg]:
                                    if provided in deps:
                                        required.add(pkg)
                                        break

                            if required:
                                to_remove_from_sync[pname] = required
                    else:
                        self.logger.warning("Conflict resolution: package '{}' marked to synchronization has no data loaded")

                if to_remove_from_sync:  # removing all these packages and their dependents from the context
                    self._add_to_remove(to_sync, to_remove_from_sync, context)

            # checking if the installed packages that are not in the transaction context rely on the current packages to be removed:
            current_to_remove = {*context.to_remove.keys()}
            required_by_installed = self.deps_analyser.map_all_required_by(current_to_remove, {*to_sync})

            if required_by_installed:
                # updating provided context:
                provided_not_mapped = set()
                for pkg in current_to_remove.difference({*to_remove_provided.keys()}):
                    if pkg not in context.pkgs_data:
                        provided_not_mapped.add(pkg)
                    else:
                        provided = context.pkgs_data[pkg].get('p')
                        if provided:
                            to_remove_provided[pkg] = provided
                        else:
                            provided_not_mapped.add(pkg)

                if provided_not_mapped:
                    to_remove_provided.update(pacman.map_provided(remote=False, pkgs=provided_not_mapped))

                deps_no_data = {dep for dep in required_by_installed if dep in context.pkgs_data}
                deps_nodata_deps = pacman.map_required_dependencies(*deps_no_data) if deps_no_data else {}

                reverse_to_remove_provided = {p: name for name, provided in to_remove_provided.items() for p in provided}

                for pkg in required_by_installed:
                    if pkg not in context.to_remove:
                        if pkg in context.pkgs_data:
                            dep_deps = context.pkgs_data[pkg].get('d')
                        else:
                            dep_deps = deps_nodata_deps.get(pkg)

                        if dep_deps:
                            source = ', '.join((reverse_to_remove_provided[d] for d in dep_deps if d in reverse_to_remove_provided))
                            reason = "{} '{}'".format(self.i18n['arch.info.depends on'].capitalize(), source if source else '?')
                            context.to_remove[pkg] = UpgradeRequirement(pkg=ArchPackage(name=pkg,
                                                                                        installed=True,
                                                                                        i18n=self.i18n),
                                                                        reason=reason)

            for name in context.to_remove:  # upgrading lists
                if name in context.pkgs_data:
                    del context.pkgs_data[name]

                if name in context.aur_to_update:
                    del context.aur_to_update[name]

                if name in context.repo_to_update:
                    del context.repo_to_update[name]

            removed_size = pacman.get_installed_size([*context.to_remove.keys()])

            if removed_size:
                for name, size in removed_size.items():
                    if size is not None:
                        req = context.to_remove.get(name)
                        if req:
                            req.extra_size = size

    def _add_to_remove(self, pkgs_to_sync: Set[str], names: Dict[str, Set[str]], context: UpdateRequirementsContext, to_ignore: Set[str] = None):
        blacklist = to_ignore if to_ignore else set()
        blacklist.update(names)

        dependents = {}
        for pname in pkgs_to_sync:
            if pname not in blacklist:
                data = context.pkgs_data.get(pname)

                if data:
                    deps = data.get('d')

                    if deps:
                        for n in names:
                            if n in deps:
                                all_deps = dependents.get(n, set())
                                all_deps.update(pname)
                                dependents[n] = all_deps

                else:
                    self.logger.warning("Package '{}' to sync could not be removed from the transaction context because its data was not loaded")

        for n in names:
            if n in context.pkgs_data:
                if n not in context.to_remove:
                    depends_on = names.get(n)
                    if depends_on:
                        reason = "{} '{}'".format(self.i18n['arch.info.depends on'].capitalize(), ', '.join(depends_on))
                    else:
                        reason = '?'

                    context.to_remove[n] = UpgradeRequirement(pkg=ArchPackage(name=n,
                                                                              installed=True,
                                                                              i18n=self.i18n),
                                                              reason=reason)

                all_deps = dependents.get(n)

                if all_deps:
                    self._add_to_remove(pkgs_to_sync, {dep: {n} for dep in all_deps}, context, blacklist)
            else:
                self.logger.warning("Package '{}' could not be removed from the transaction context because its data was not loaded")

    def _fill_dependency_breakage(self, context: UpdateRequirementsContext):
        if bool(context.arch_config['check_dependency_breakage']) and (context.to_update or context.to_install):
            ti = time.time()
            self.logger.info("Begin: checking dependency breakage")

            required_by = pacman.map_required_by(context.to_update.keys()) if context.to_update else {}

            if context.to_install:
                required_by.update(pacman.map_required_by(context.to_install.keys(), remote=True))

            reqs_not_in_transaction = set()
            reqs_in_transaction = set()

            transaction_pkgs = {*context.to_update.keys(), *context.to_install.keys()}

            for reqs in required_by.values():
                for r in reqs:
                    if r in transaction_pkgs:
                        reqs_in_transaction.add(r)
                    elif r in context.installed_names:
                        reqs_not_in_transaction.add(r)

            if not reqs_not_in_transaction and not reqs_in_transaction:
                return

            provided_versions = {}

            for p in context.provided_map:
                pkg_split = p.split('=')

                if len(pkg_split) > 1:
                    versions = provided_versions.get(pkg_split[0])

                    if versions is None:
                        versions = set()
                        provided_versions[pkg_split[0]] = versions

                    versions.add(pkg_split[1])

            if not provided_versions:
                return

            cannot_upgrade = set()

            for pkg, deps in pacman.map_required_dependencies(*reqs_not_in_transaction).items():
                self._add_dependency_breakage(pkgname=pkg,
                                              pkgdeps=deps,
                                              provided_versions=provided_versions,
                                              cannot_upgrade=cannot_upgrade,
                                              context=context)

            for pkg in reqs_in_transaction:
                data = context.pkgs_data[pkg]

                if data and data['d']:
                    self._add_dependency_breakage(pkgname=pkg,
                                                  pkgdeps=data['d'],
                                                  provided_versions=provided_versions,
                                                  cannot_upgrade=cannot_upgrade,
                                                  context=context)

            if cannot_upgrade:
                cannot_upgrade.update(self._add_dependents_as_cannot_upgrade(context=context,
                                                                             names=cannot_upgrade,
                                                                             pkgs_available={*context.to_update.values(), *context.to_install.values()}))

                for p in cannot_upgrade:
                    if p in context.to_update:
                        del context.to_update[p]

                    if p in context.repo_to_update:
                        del context.repo_to_update[p]

                    if p in context.aur_to_update:
                        del context.aur_to_update[p]

                    if p in context.pkgs_data:
                        del context.pkgs_data[p]

                    if p in context.to_install:
                        del context.to_install[p]

                    if p in context.repo_to_install:
                        del context.repo_to_install[p]

                    if p in context.aur_to_install:
                        del context.aur_to_install[p]

            tf = time.time()
            self.logger.info("End: checking dependency breakage. Time: {0:.2f} seconds".format(tf - ti))

    def _add_dependents_as_cannot_upgrade(self, context: UpdateRequirementsContext, names: Iterable[str], pkgs_available: Set[ArchPackage], already_removed: Optional[Set[str]] = None, iteration_level: int = 0) -> Set[str]:
        removed = set() if already_removed is None else already_removed
        removed.update(names)

        available = {p for p in pkgs_available if p.name not in removed}
        to_remove = set()

        if available:
            for pkg in available:
                if pkg.name not in removed:
                    data = context.pkgs_data.get(pkg.name)

                    if data and data['d']:
                        for dep in data['d']:
                            dep_providers = context.provided_map.get(dep)

                            if dep_providers:
                                for p in dep_providers:
                                    if p in names:
                                        to_remove.add(pkg.name)

                                        if pkg.name not in context.cannot_upgrade:
                                            reason = "{} {}".format(self.i18n['arch.info.depends on'].capitalize(), p)
                                            context.cannot_upgrade[pkg.name] = UpgradeRequirement(pkg=pkg,
                                                                                                  reason=reason,
                                                                                                  sorting_priority=iteration_level - 1)

                                        break

            if to_remove:
                removed.update(to_remove)
                self._add_dependents_as_cannot_upgrade(context=context, names=to_remove, pkgs_available=available,
                                                       already_removed=to_remove, iteration_level=iteration_level-1)

        return to_remove

    def _add_dependency_breakage(self, pkgname: str, pkgdeps: Optional[Set[str]], provided_versions: Dict[str, Set[str]], cannot_upgrade: Set[str], context: UpdateRequirementsContext):
        if pkgdeps:
            for dep in pkgdeps:
                dep_split = RE_DEP_OPERATORS.split(dep)

                if len(dep_split) > 1 and dep_split[1]:
                    real_providers = context.provided_map.get(dep_split[0])

                    if real_providers:
                        versions = provided_versions.get(dep_split[0])

                        if versions:
                            op = ''.join(RE_DEP_OPERATORS.findall(dep))

                            if op == '=':
                                op = '=='

                            version_match = False

                            for v in versions:
                                try:
                                    provided_version, required_version = parse_version(v), parse_version(dep_split[1])

                                    if eval('provided_version {} required_version'.format(op)):
                                        version_match = True
                                        break
                                except:
                                    self.logger.error("Error when comparing versions {} (provided) and {} (required)".format(v, dep_split[1]))
                                    traceback.print_exc()

                            if not version_match:
                                for pname in real_providers:
                                    if pname not in cannot_upgrade:
                                        provider = context.to_update.get(pname)
                                        if provider:
                                            cannot_upgrade.add(pname)
                                            reason = self.i18n['arch.sync.dep_breakage.reason'].format(pkgname, dep)
                                            context.cannot_upgrade[pname] = UpgradeRequirement(pkg=provider,
                                                                                               reason=reason)
