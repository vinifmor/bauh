import logging
import time
import traceback
from threading import Thread
from typing import Dict, Set, List, Iterable, Tuple

from bauh.api.abstract.controller import UpdateRequirements, UpdateRequirement
from bauh.api.abstract.handler import ProcessWatcher
from bauh.gems.arch import pacman
from bauh.gems.arch.aur import AURClient
from bauh.gems.arch.depedencies import DependenciesAnalyser
from bauh.gems.arch.model import ArchPackage
from bauh.view.util.translation import I18n


class UpdateRequirementsContext:

    def __init__(self, to_update: Dict[str, ArchPackage], repo_to_update: Dict[str, ArchPackage],
                 aur_to_update: Dict[str, ArchPackage], repo_to_install: Dict[str, ArchPackage],
                 aur_to_install: Dict[str, ArchPackage], to_install: Dict[str, ArchPackage],
                 pkgs_data: Dict[str, dict], cannot_update: Dict[str, UpdateRequirement],
                 to_remove: Dict[str, UpdateRequirement], installed_names: Set[str], root_password: str):
        self.to_update = to_update
        self.repo_to_update = repo_to_update
        self.aur_to_update = aur_to_update
        self.repo_to_install = repo_to_install
        self.aur_to_install = aur_to_install
        self.pkgs_data = pkgs_data
        self.cannot_update = cannot_update
        self.root_password = root_password
        self.installed_names = installed_names
        self.to_remove = to_remove
        self.to_install = to_install


class UpdatesSummarizer:

    def __init__(self, aur_client: AURClient, i18n: I18n, logger: logging.Logger, deps_analyser: DependenciesAnalyser, watcher: ProcessWatcher):
        self.aur_client = aur_client
        self.i18n = i18n
        self.logger = logger
        self.watcher = watcher
        self.deps_analyser = deps_analyser

    def _fill_aur_pkg_update_data(self, pkg: ArchPackage, output: dict):
        srcinfo = self.aur_client.get_src_info(pkg.get_base_name())

        if srcinfo:
            output[pkg.name] = {'c': srcinfo.get('conflicts'), 's': None, 'p': srcinfo.get('provides'), 'r': 'aur'}
        else:
            output[pkg.name] = {'c': None, 's': None, 'p': None, 'r': 'aur'}

    def _handle_conflict_both_to_install(self, pkg1: str, pkg2: str, context: UpdateRequirementsContext):
        for src_pkg in {p for p, data in context.pkgs_data.items() if
                        data['d'] and pkg1 in data['d'] or pkg2 in data['d']}:
            if src_pkg not in context.cannot_update:
                reason = self.i18n['arch.update_summary.to_install.dep_conflict'].format("'{}'".format(pkg1),
                                                                                         "'{}'".format(pkg2))
                context.cannot_update[src_pkg] = UpdateRequirement(context.to_update[src_pkg], reason)

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

        if to_update not in context.cannot_update:
            srcs_str = ', '.join(("'{}'".format(p) for p in to_install_srcs))
            reason = self.i18n['arch.update_summary.to_update.conflicts_dep'].format("'{}'".format(to_install),
                                                                                     srcs_str)
            context.cannot_update[to_install] = UpdateRequirement(context.to_update[to_update], reason)

        if to_update in context.to_update:
            del context.to_update[to_update]

        for src_pkg in to_install_srcs:
            src_to_install = src_pkg in context.to_install
            pkg = context.to_install[src_pkg] if src_to_install else context.to_update[src_pkg]
            if src_pkg not in context.cannot_update:
                reason = self.i18n['arch.update_summary.to_update.dep_conflicts'].format("'{}'".format(to_install),
                                                                                         "'{}'".format(to_update))
                context.cannot_update[src_pkg] = UpdateRequirement(pkg, reason)

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
        if pkg1 not in context.cannot_update:
            reason = "{} '{}'".format(self.i18n['arch.info.conflicts with'].capitalize(), pkg2)
            context.cannot_update[pkg1] = UpdateRequirement(pkg=context.to_update[pkg1], reason=reason)

        if pkg2 not in context.cannot_update:
            reason = "{} '{}'".format(self.i18n['arch.info.conflicts with'].capitalize(), pkg1)
            context.cannot_update[pkg2] = UpdateRequirement(pkg=context.to_update[pkg2], reason=reason)

        for p in (pkg1, pkg2):
            if p in context.to_update:
                del context.to_update[p]

                if p in context.repo_to_update:
                    del context.repo_to_update[p]
                else:
                    del context.aur_to_update[p]

    def _filter_and_map_conflicts(self, context: UpdateRequirementsContext) -> Dict[str, str]:
        # provided_map = pacman.map_provided()  # TODO move to context
        # all_provided = provided_map.keys()  # TODO move to context

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

            for pkg1, pkg2 in mutual_conflicts.items():  # removing conflicting packages from the packages selected to update
                for p in (pkg1, pkg2):
                    for c in context.pkgs_data[p]['c']:
                        # source = provided_map[c]
                        if c in root_conflict:
                            del root_conflict[c]

                    if p in context.pkgs_data:
                        del context.pkgs_data[p]

        return root_conflict

    def _fill_conflicts(self, context: UpdateRequirementsContext, blacklist: Set[str] = None):
        self.logger.info("Checking conflicts")

        root_conflict = self._filter_and_map_conflicts(context)

        sub_conflict = pacman.get_dependencies_to_remove(root_conflict.keys(), context.root_password) if root_conflict else None

        to_remove_map = {}
        if sub_conflict:
            for dep, source in sub_conflict.items():
                if dep not in to_remove_map and (not blacklist or dep not in blacklist):
                    pkg = ArchPackage(name=dep, installed=True, i18n=self.i18n)
                    to_remove_map[dep] = pkg
                    reason = "{} '{}'".format(self.i18n['arch.info.depends on'].capitalize(), source)
                    context.to_remove[dep] = UpdateRequirement(pkg, reason)

        if root_conflict:
            for dep, source in root_conflict.items():
                if dep not in to_remove_map and (not blacklist or dep not in blacklist):
                    pkg = ArchPackage(name=dep, installed=True, i18n=self.i18n)
                    to_remove_map[dep] = pkg
                    reason = "{} '{}'".format(self.i18n['arch.info.conflicts with'].capitalize(), source)
                    context.to_remove[dep] = UpdateRequirement(pkg, reason)

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
                        pkg = to_remove_map.get(name)
                        if pkg:
                            pkg.size = size

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

    def _sort_update_order(self, pkgs: Dict[str, ArchPackage]) -> List[ArchPackage]:
        aur_pkgs, repo_pkgs = [], []

        for n, p in pkgs.items():
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

        for pkg in aur_pkgs:
            t = Thread(target=_add_info, args=(pkg, ), daemon=True)
            t.start()
            threads.append(t)

        self._fill_repo_pkgs_sort_data(repo_pkgs, pkg_deps, names_map)

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

    def _get_update_required_packages(self, pkgs: Iterable[ArchPackage]) -> List[ArchPackage]:
        ti = time.time()
        required = []
        deps = self.deps_analyser.map_known_missing_deps({p.get_base_name(): p.repository for p in pkgs}, self.watcher)

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

            required.extend([sorted_pkgs[idx] for idx in sorted(sorted_pkgs)])

        tf = time.time()
        self.logger.info("It took {0:.2f} seconds to retrieve required upgrade packages".format(tf - ti))
        return required

    def summarize(self, pkgs: List[ArchPackage], sort: bool, root_password: str) -> UpdateRequirements:
        res = UpdateRequirements(None, [], None, [])

        installed_names = pacman.list_installed_names()
        context = UpdateRequirementsContext({}, {}, {}, {}, {}, {}, {}, {}, {}, installed_names, root_password)

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

        context.pkgs_data.update(pacman.map_updates_required_data(context.repo_to_update.keys()))
        context.pkgs_data.update(aur_data)

        if context.pkgs_data:
            self._fill_conflicts(context)

        to_install = self._get_update_required_packages(context.to_update.values())

        if to_install:
            aur_to_install_data = {}
            all_to_install_data = {}

            aur_threads = []
            for pkg in to_install:
                context.to_install[pkg.name] = pkg
                if pkg.repository == 'aur':
                    context.aur_to_install[pkg.name] = pkg
                    t = Thread(target=self._fill_aur_pkg_update_data, args=(pkg, aur_to_install_data), daemon=True)
                    t.start()
                    aur_threads.append(t)
                else:
                    context.repo_to_install[pkg.name] = pkg

            for t in aur_threads:
                t.join()

            if context.repo_to_install:
                all_to_install_data.update(pacman.map_updates_required_data(context.repo_to_install.keys()))

            all_to_install_data.update(aur_to_install_data)

            if all_to_install_data:
                context.pkgs_data.update(all_to_install_data)
                self._fill_conflicts(context, {d.pkg.name for d in res.to_remove})

        all_repo_pkgs = {**context.repo_to_update, **context.repo_to_install}
        if all_repo_pkgs:  # filling sizes
            names, installed, new = [], [], []

            for p in all_repo_pkgs.values():
                names.append(p.name)

                if p.installed:
                    installed.append(p.name)
                else:
                    new.append(p.name)

            if context.pkgs_data:
                for p in new:
                    pkg = all_repo_pkgs[p]
                    pkg.size = context.pkgs_data[p]['s']

                if installed:
                    installed_size = pacman.get_installed_size(installed)

                    for p in installed:
                        pkg = all_repo_pkgs[p]
                        pkg.size = installed_size[p]
                        update_size = context.pkgs_data[p]['s']

                        if pkg.size is None:
                            pkg.size = update_size
                        elif update_size is not None:
                            pkg.size = update_size - pkg.size

        if context.to_update:
            if sort:
                res.to_update = self._sort_update_order(context.to_update)
            else:
                res.to_update = [p for p in context.to_update.values()]

        if context.to_remove:
            res.to_remove = [p for p in context.to_remove.values()]

        if context.cannot_update:
            res.cannot_update = [p for p in context.cannot_update.keys()]

        if context.to_install:
            res.to_install = [UpdateRequirement(p) for p in to_install if p.name in context.to_install]

        return res